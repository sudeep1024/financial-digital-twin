from __future__ import annotations

import numpy as np

from backend.utils.loader import DataLoadError, load_csv


def _pick_target_ticker(df, target_ticker: str | None) -> str:
    if target_ticker:
        upper_candidates = {str(t).upper(): str(t) for t in df["ticker"].astype(str).tolist()}
        requested = target_ticker.upper()
        if requested in upper_candidates:
            return upper_candidates[requested]
        raise ValueError(f"Ticker '{target_ticker}' not found in peer EV/EBITDA dataset.")
    return str(df.iloc[0]["ticker"])


def _compute_pe_metrics(target_ticker: str) -> tuple[float | None, float | None]:
    try:
        peer_group = load_csv(
            "data/peer_group_hdfc.csv",
            required_columns=["ticker", "price_to_earnings", "market_cap"],
        )
    except DataLoadError:
        return None, None

    peer_group = peer_group.dropna(subset=["price_to_earnings", "market_cap"]).copy()
    if peer_group.empty:
        return None, None

    if target_ticker not in set(peer_group["ticker"].astype(str)):
        return None, None

    peers_only = peer_group[peer_group["ticker"] != target_ticker]
    if peers_only.empty:
        peers_only = peer_group

    median_pe = float(np.median(peers_only["price_to_earnings"].to_numpy(dtype=float)))

    target_row = peer_group[peer_group["ticker"] == target_ticker].iloc[0]
    target_pe = float(target_row["price_to_earnings"])
    target_market_cap = float(target_row["market_cap"])
    if target_pe <= 0:
        return median_pe, None

    target_earnings = target_market_cap / target_pe
    implied_value_pe = median_pe * target_earnings
    return median_pe, float(implied_value_pe)


def get_multiples(target_ticker: str | None = None) -> dict:
    df = load_csv(
        "data/peer_ev_ebitda.csv",
        required_columns=["ticker", "market_cap", "total_debt", "cash", "ebitda", "ev_ebitda"],
    ).copy()

    target = _pick_target_ticker(df, target_ticker)
    target_row = df[df["ticker"] == target].iloc[0]

    peers_only = df[df["ticker"] != target]
    if peers_only.empty:
        peers_only = df

    ev_ebitdas = peers_only["ev_ebitda"].dropna().to_numpy(dtype=float)
    if len(ev_ebitdas) == 0:
        raise ValueError("No valid peer EV/EBITDA values found.")

    median_ev_ebitda = float(np.median(ev_ebitdas))
    target_ebitda = float(target_row["ebitda"])
    implied_enterprise_value = median_ev_ebitda * target_ebitda
    implied_equity_from_ev = implied_enterprise_value + float(target_row["cash"]) - float(target_row["total_debt"])

    median_pe, implied_value_pe = _compute_pe_metrics(target_ticker=target)

    return {
        "target_ticker": target,
        "peer_count": int(len(peers_only)),
        "median_ev_ebitda": median_ev_ebitda,
        "implied_enterprise_value_ev_ebitda": float(implied_enterprise_value),
        "implied_value_ev_ebitda": float(implied_equity_from_ev),
        "median_pe": median_pe,
        "implied_value_pe": implied_value_pe,
    }
