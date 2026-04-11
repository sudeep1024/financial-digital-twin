from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from backend.services.internal_universe import get_profile
from backend.utils.loader import DataLoadError, load_csv, resolve_data_path


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        out = float(value)
        if np.isnan(out) or np.isinf(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def _normalize_score_inverse(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return float(1 - np.clip(value, 0.0, cap) / cap)


def _normalize_score(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    clipped = float(np.clip(value, floor, ceiling))
    return float((clipped - floor) / (ceiling - floor))


def _load_price_close_series(path: str, close_column: str = "Close") -> pd.Series:
    csv_path = resolve_data_path(path)
    if not csv_path.exists():
        raise DataLoadError(f"Price file not found: {csv_path}")

    df = pd.read_csv(csv_path, skiprows=[1, 2])
    date_column = "Date" if "Date" in df.columns else "Price"
    if date_column not in df.columns or close_column not in df.columns:
        raise DataLoadError(f"Unexpected price file format for {csv_path.name}.")

    df = df[df[date_column].astype(str) != "Date"].copy()
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    df[close_column] = pd.to_numeric(df[close_column], errors="coerce")
    df = df.dropna(subset=[date_column, close_column]).sort_values(date_column)
    if df.empty:
        raise DataLoadError(f"No valid closing prices in {csv_path.name}.")
    return pd.Series(df[close_column].to_numpy(dtype=float), index=df[date_column])


def _estimate_beta_from_prices(stock_price_file: str, market_price_file: str) -> dict:
    stock_close = _load_price_close_series(stock_price_file)
    market_close = _load_price_close_series(market_price_file)

    stock_ret = stock_close.pct_change().dropna()
    market_ret = market_close.pct_change().dropna()
    merged = pd.concat([stock_ret.rename("stock"), market_ret.rename("market")], axis=1, join="inner").dropna()
    if len(merged) < 120:
        raise ValueError("Insufficient overlapping price history for regression-based beta estimation.")

    x = merged["market"].to_numpy(dtype=float).reshape(-1, 1)
    y = merged["stock"].to_numpy(dtype=float)
    reg = LinearRegression()
    reg.fit(x, y)

    beta_reg = float(reg.coef_[0])
    alpha_reg = float(reg.intercept_)

    window = min(252, len(merged))
    rolling = merged.iloc[-window:]
    variance = float(np.var(rolling["market"], ddof=1))
    if variance <= 0:
        beta_t = beta_reg
    else:
        beta_t = float(np.cov(rolling["stock"], rolling["market"], ddof=1)[0, 1] / variance)

    market_volatility = float(rolling["market"].std(ddof=1) * np.sqrt(252))
    return {
        "beta_regression": beta_reg,
        "alpha_regression": alpha_reg,
        "beta_t": float(np.clip(beta_t, 0.2, 3.0)),
        "market_volatility": float(np.clip(market_volatility, 0.05, 0.85)),
    }


def _load_fcf_history() -> pd.Series:
    fcf_clean = load_csv("data/fundamentals/fcf_clean.csv", required_columns=["FCF"]).copy()
    idx = pd.to_datetime(fcf_clean.iloc[:, 0], errors="coerce")
    values = pd.to_numeric(fcf_clean["FCF"], errors="coerce")
    series = pd.Series(values.to_numpy(dtype=float), index=idx).dropna().sort_index()
    if series.empty:
        raise ValueError("FCF history is empty in fundamentals/fcf_clean.csv.")
    return series


def _ml_forecast_from_history(years: int = 5) -> list[dict]:
    fcf_series = _load_fcf_history()
    if len(fcf_series) < 3:
        raise ValueError("At least 3 historical FCF observations are required for ML forecast fallback.")

    y = fcf_series.to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float).reshape(-1, 1)
    model = LinearRegression()
    model.fit(x, y)

    future_x = np.arange(len(y), len(y) + years, dtype=float).reshape(-1, 1)
    trend_pred = model.predict(future_x)
    residuals = y - model.predict(x)
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else abs(float(y[-1])) * 0.05
    base_year = int(fcf_series.index[-1].year)

    rows: list[dict] = []
    for i in range(years):
        mean_val = max(float(trend_pred[i]), 1.0)
        spread = residual_std * (1 + 0.15 * i)
        rows.append(
            {
                "year": str(base_year + i + 1),
                "fcf_mean": mean_val,
                "fcf_upper": mean_val + 1.96 * spread,
                "fcf_lower": max(mean_val - 1.96 * spread, 1.0),
            }
        )
    return rows


def _load_fcf_forecast() -> tuple[list[dict], float]:
    try:
        df = load_csv(
            "data/final_forecast_fcf.csv",
            required_columns=["Year", "FCF_Mean", "FCF_Upper", "FCF_Lower"],
        ).copy()
        df = df.sort_values("Year")
        if len(df) < 5:
            raise ValueError("Forecast output has less than 5 years.")

        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "year": str(row["Year"])[:10],
                    "fcf_mean": float(row["FCF_Mean"]),
                    "fcf_upper": float(row["FCF_Upper"]),
                    "fcf_lower": float(row["FCF_Lower"]),
                }
            )
        return rows, 1.0
    except Exception:
        return _ml_forecast_from_history(years=5), 0.85


def _load_fundamental_statement(path: str) -> pd.DataFrame:
    df = load_csv(path).copy()
    idx = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    df = df.drop(columns=[df.columns[0]])
    df.index = idx
    df = df[~df.index.isna()]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_index(ascending=False)


def _statement_rows(df: pd.DataFrame, metrics: list[str], years: int = 4) -> list[dict]:
    out: list[dict] = []
    for metric in metrics:
        if metric not in df.columns:
            continue
        series = df[metric].dropna()
        if series.empty:
            continue
        values: dict[str, float] = {}
        for idx, val in series.head(years).items():
            values[str(idx.year)] = float(val)
        if values:
            out.append({"metric": metric, "values": values})
    return out


def _load_internal_statements() -> dict:
    income = _load_fundamental_statement("data/fundamentals/income_statement.csv")
    balance = _load_fundamental_statement("data/fundamentals/balance_sheet.csv")
    cashflow = _load_fundamental_statement("data/fundamentals/cashflow_statement.csv")
    return {
        "income_statement": _statement_rows(
            income,
            ["Total Revenue", "Net Income", "Pretax Income", "Tax Provision", "Net Interest Income"],
        ),
        "balance_sheet": _statement_rows(
            balance,
            [
                "Total Assets",
                "Total Liabilities Net Minority Interest",
                "Common Stock Equity",
                "Total Debt",
                "Cash And Cash Equivalents",
            ],
        ),
        "cash_flow": _statement_rows(
            cashflow,
            ["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow", "Financing Cash Flow", "Investing Cash Flow"],
        ),
    }

def _load_macro_scenarios() -> pd.DataFrame:
    df = load_csv(
        "data/macro_factors.csv",
        required_columns=[
            "scenario",
            "weight",
            "volatility_multiplier",
            "macro_spread_adjustment",
            "capital_structure_adjustment",
        ],
    ).copy()
    for col in ["weight", "volatility_multiplier", "macro_spread_adjustment", "capital_structure_adjustment"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    if df.empty:
        raise ValueError("Macro factor scenario dataset is empty.")
    weight_sum = float(df["weight"].sum())
    if weight_sum <= 0:
        raise ValueError("Invalid scenario weights in macro_factors.csv.")
    df["weight"] = df["weight"] / weight_sum
    return df


def _compute_dynamic_wacc(profile: dict, forecast_years: list[str]) -> dict:
    wacc_df = load_csv(
        "data/wacc_hdfc.csv",
        required_columns=[
            "ticker",
            "beta",
            "risk_free_rate",
            "market_premium",
            "cost_of_debt",
            "tax_rate",
            "equity_weight",
            "debt_weight",
            "wacc",
        ],
    )
    row = wacc_df.iloc[0]
    beta_dyn = _estimate_beta_from_prices(profile["price_file"], profile["market_price_file"])

    base_wacc_input = float(row["wacc"])
    risk_free_rate = float(row["risk_free_rate"])
    market_premium = float(row["market_premium"])
    cost_of_debt_base = float(row["cost_of_debt"])
    tax_rate_base = float(row["tax_rate"])
    equity_weight_base = float(row["equity_weight"])
    debt_weight_base = float(row["debt_weight"])
    debt_weight = float(row["debt_weight"])
    beta_t = float(beta_dyn["beta_t"])
    market_volatility = float(beta_dyn["market_volatility"])
    cost_of_equity_capm = float(risk_free_rate + (beta_t * market_premium))

    peer_df = load_csv("data/peer_ev_ebitda.csv", required_columns=["ticker", "market_cap", "total_debt"])
    target = peer_df[peer_df["ticker"].astype(str).str.upper() == profile["ticker"]]
    if target.empty:
        leverage_ratio = debt_weight
    else:
        target_row = target.iloc[0]
        market_cap = _safe_float(target_row["market_cap"])
        total_debt = _safe_float(target_row["total_debt"])
        denom = market_cap + total_debt
        leverage_ratio = (total_debt / denom) if denom > 0 else debt_weight
    leverage_change = float(leverage_ratio - debt_weight)

    scenarios_df = _load_macro_scenarios()
    macro_score = float(
        np.clip(
            np.mean(np.abs(scenarios_df["macro_spread_adjustment"].to_numpy(dtype=float))) / 0.02,
            0.0,
            1.2,
        )
    )

    alpha = 0.35
    beta_macro = 0.55
    gamma = 0.40

    # WACC_t = base_wacc * (1 + alpha*volatility + beta_macro*macro_score + gamma*leverage_change)
    base_equation_wacc = base_wacc_input * (
        1 + alpha * market_volatility + beta_macro * macro_score + gamma * leverage_change
    )
    base_equation_wacc = float(np.clip(base_equation_wacc, 0.045, 0.25))

    horizon = max(1, len(forecast_years))
    scenarios: list[dict] = []
    weighted_path = np.zeros(horizon, dtype=float)

    for _, sc in scenarios_df.iterrows():
        volatility_s = market_volatility * float(sc["volatility_multiplier"])
        macro_score_s = float(np.clip(macro_score + float(sc["macro_spread_adjustment"]) / 0.02, 0.0, 1.5))
        leverage_change_s = leverage_change + float(sc["capital_structure_adjustment"])

        initial_wacc = base_wacc_input * (
            1 + alpha * volatility_s + beta_macro * macro_score_s + gamma * leverage_change_s
        )
        initial_wacc = float(np.clip(initial_wacc, 0.045, 0.30))

        path: list[float] = []
        denom = max(horizon - 1, 1)
        for t in range(horizon):
            decay = 1 - (t / denom)
            reversion = (base_equation_wacc - initial_wacc) * (t / denom) * 0.40
            term_adj = float(sc["macro_spread_adjustment"]) * decay
            wacc_t = float(np.clip(initial_wacc + reversion + term_adj, 0.04, 0.30))
            path.append(wacc_t)

        weight = float(sc["weight"])
        weighted_path += weight * np.array(path, dtype=float)
        scenarios.append(
            {
                "scenario": str(sc["scenario"]),
                "weight": weight,
                "initial_wacc": initial_wacc,
                "path": path,
            }
        )

    time_varying_wacc = [
        {"year": str(forecast_years[i]), "wacc": float(weighted_path[i])}
        for i in range(horizon)
    ]

    return {
        "base_wacc": float(weighted_path[0]),
        "formula": "WACC_t = base_wacc * (1 + alpha*volatility + beta_macro*macro_score + gamma*leverage_change)",
        "parameters": {
            "alpha": float(alpha),
            "beta_macro": float(beta_macro),
            "gamma": float(gamma),
        },
        "inputs": {
            "base_wacc_input": float(base_wacc_input),
            "volatility": float(market_volatility),
            "macro_score": float(macro_score),
            "leverage_change": float(leverage_change),
        },
        "decomposition": {
            "multiplicative_factor": float(1 + alpha * market_volatility + beta_macro * macro_score + gamma * leverage_change),
            "volatility_contribution": float(alpha * market_volatility),
            "macro_contribution": float(beta_macro * macro_score),
            "leverage_contribution": float(gamma * leverage_change),
            "base_equation_wacc": float(base_equation_wacc),
        },
        "beta": float(beta_t),
        "market_volatility": float(market_volatility),
        "macro_score": float(macro_score),
        "leverage_ratio": float(leverage_ratio),
        "scenarios": scenarios,
        "time_varying_wacc": time_varying_wacc,
        "wacc_breakdown_inputs": {
            "risk_free_rate": float(risk_free_rate),
            "beta": float(beta_t),
            "market_risk_premium": float(market_premium),
            "cost_of_equity": float(cost_of_equity_capm),
            "cost_of_debt": float(cost_of_debt_base),
            "tax_rate": float(tax_rate_base),
            "equity_weight": float(equity_weight_base),
            "debt_weight": float(debt_weight_base),
            "final_wacc": float(weighted_path[0]),
        },
    }


def _compute_dcf_with_wacc_path(fcf_values: np.ndarray, wacc_path: np.ndarray, terminal_growth_rate: float) -> dict:
    if len(fcf_values) == 0:
        raise ValueError("FCF forecast is empty for DCF valuation.")
    if len(wacc_path) != len(fcf_values):
        raise ValueError("WACC path length must match FCF forecast horizon.")

    wacc_path = np.clip(wacc_path.astype(float), terminal_growth_rate + 0.005, 0.50)
    discount_factors = np.cumprod(1 + wacc_path)
    pv_forecast = float(np.sum(fcf_values / discount_factors))

    terminal_wacc = float(max(wacc_path[-1], terminal_growth_rate + 0.005))
    terminal_fcf = float(fcf_values[-1])
    terminal_value = float((terminal_fcf * (1 + terminal_growth_rate)) / (terminal_wacc - terminal_growth_rate))
    pv_terminal_value = float(terminal_value / discount_factors[-1])
    enterprise_value = float(pv_forecast + pv_terminal_value)

    return {
        "pv_forecast": pv_forecast,
        "terminal_value": terminal_value,
        "pv_terminal_value": pv_terminal_value,
        "enterprise_value": enterprise_value,
        "effective_wacc": float(np.mean(wacc_path)),
    }

def _run_monte_carlo(forecast: list[dict], dynamic_wacc: dict, terminal_growth_rate: float, base_value: float) -> dict:
    rng = np.random.default_rng(42)
    iterations = 1000

    means = np.array([float(row["fcf_mean"]) for row in forecast], dtype=float)
    uppers = np.array([float(row["fcf_upper"]) for row in forecast], dtype=float)
    lowers = np.array([float(row["fcf_lower"]) for row in forecast], dtype=float)
    horizon = len(means)

    stds = np.maximum((uppers - lowers) / 3.29, np.maximum(np.abs(means) * 0.03, 1.0))
    fcf_samples = rng.normal(loc=means[None, :], scale=stds[None, :], size=(iterations, horizon))
    fcf_samples = np.clip(fcf_samples, 1.0, None)

    scenarios = dynamic_wacc["scenarios"]
    probs = np.array([float(s["weight"]) for s in scenarios], dtype=float)
    probs = probs / probs.sum()
    scenario_paths = np.array([np.array(s["path"], dtype=float) for s in scenarios], dtype=float)

    idx = rng.choice(len(scenarios), size=iterations, p=probs)
    sampled_wacc_paths = scenario_paths[idx]
    sampled_wacc_paths = sampled_wacc_paths + rng.normal(loc=0.0, scale=0.0045, size=sampled_wacc_paths.shape)
    sampled_wacc_paths = np.clip(sampled_wacc_paths, terminal_growth_rate + 0.005, 0.40)

    discount = np.cumprod(1 + sampled_wacc_paths, axis=1)
    pv_forecast = np.sum(fcf_samples / discount, axis=1)
    terminal_fcf = fcf_samples[:, -1]
    terminal_wacc = sampled_wacc_paths[:, -1]
    terminal_value = (terminal_fcf * (1 + terminal_growth_rate)) / (terminal_wacc - terminal_growth_rate)
    pv_terminal = terminal_value / discount[:, -1]
    valuations = pv_forecast + pv_terminal
    valuations = valuations[np.isfinite(valuations)]

    if len(valuations) < 1000:
        raise ValueError("Monte Carlo valid sample count dropped below 1,000.")

    counts, edges = np.histogram(valuations, bins=40)
    histogram = [
        {"bin_start": float(edges[i]), "bin_end": float(edges[i + 1]), "count": int(counts[i])}
        for i in range(len(counts))
    ]

    return {
        "iterations": int(len(valuations)),
        "mean": float(np.mean(valuations)),
        "std_dev": float(np.std(valuations, ddof=1)),
        "p10": float(np.quantile(valuations, 0.10)),
        "p50": float(np.quantile(valuations, 0.50)),
        "p90": float(np.quantile(valuations, 0.90)),
        "min": float(np.min(valuations)),
        "max": float(np.max(valuations)),
        "probability_undervalued": float(np.mean(valuations > base_value)),
        "histogram": histogram,
    }


def _compute_multiples(profile: dict) -> dict:
    ev_df = load_csv(
        "data/peer_ev_ebitda.csv",
        required_columns=["ticker", "market_cap", "total_debt", "cash", "ebitda", "ev_ebitda"],
    ).copy()
    pb_df = load_csv(
        "data/peer_group_hdfc.csv",
        required_columns=["ticker", "price_to_book", "price_to_earnings", "market_cap"],
    ).copy()

    target = profile["ticker"]
    target_ev = ev_df[ev_df["ticker"].astype(str).str.upper() == target]
    if target_ev.empty:
        raise ValueError(f"Ticker '{target}' missing in peer_ev_ebitda.csv.")
    target_ev_row = target_ev.iloc[0]
    target_market_cap = float(target_ev_row["market_cap"])

    peers_ev = ev_df[ev_df["ticker"].astype(str).str.upper() != target]
    if peers_ev.empty:
        peers_ev = ev_df
    median_ev_ebitda = float(np.median(peers_ev["ev_ebitda"].dropna().to_numpy(dtype=float)))
    implied_enterprise = median_ev_ebitda * float(target_ev_row["ebitda"])
    implied_value_ev = implied_enterprise + float(target_ev_row["cash"]) - float(target_ev_row["total_debt"])

    target_pb = pb_df[pb_df["ticker"].astype(str).str.upper() == target]
    median_pb = None
    implied_value_pb = None
    median_pe = None
    implied_value_pe = None
    if not target_pb.empty:
        peers_pb = pb_df[pb_df["ticker"].astype(str).str.upper() != target]
        if peers_pb.empty:
            peers_pb = pb_df

        median_pb = float(np.median(peers_pb["price_to_book"].dropna().to_numpy(dtype=float)))
        median_pe = float(np.median(peers_pb["price_to_earnings"].dropna().to_numpy(dtype=float)))

        target_row = target_pb.iloc[0]
        target_market_cap = float(target_row["market_cap"])
        target_price_to_book = _safe_float(target_row["price_to_book"], default=0.0)
        target_price_to_earnings = _safe_float(target_row["price_to_earnings"], default=0.0)

        if target_price_to_book > 0:
            book_value = target_market_cap / target_price_to_book
            implied_value_pb = median_pb * book_value
        if target_price_to_earnings > 0:
            target_earnings = target_market_cap / target_price_to_earnings
            implied_value_pe = median_pe * target_earnings

    selected_anchor = "ev_ebitda"
    if profile["sector"].lower() in {"financials", "banks", "banking"} and implied_value_pb is not None:
        selected_anchor = "price_to_book"

    return {
        "target_ticker": target,
        "target_market_cap": float(target_market_cap),
        "peer_count": int(len(peers_ev)),
        "median_ev_ebitda": float(median_ev_ebitda),
        "implied_enterprise_value_ev_ebitda": float(implied_enterprise),
        "implied_value_ev_ebitda": float(implied_value_ev),
        "median_price_to_book": (float(median_pb) if median_pb is not None else None),
        "implied_value_price_to_book": (float(implied_value_pb) if implied_value_pb is not None else None),
        "selected_anchor": selected_anchor,
        "median_pe": (float(median_pe) if median_pe is not None else None),
        "implied_value_pe": (float(implied_value_pe) if implied_value_pe is not None else None),
    }


def _triangulation_weights_for_sector(sector: str, volatility: float, confidence_score: float) -> dict[str, float]:
    sector_l = (sector or "").lower()
    if sector_l in {"financials", "banks", "banking"}:
        base = {"dcf": 0.34, "mc_p50": 0.18, "multiples": 0.48}
    elif sector_l in {"technology", "tech"}:
        base = {"dcf": 0.52, "mc_p50": 0.30, "multiples": 0.18}
    else:
        base = {"dcf": 0.45, "mc_p50": 0.25, "multiples": 0.30}

    vol_norm = _normalize_score(volatility, 0.10, 0.45)
    conf = float(np.clip(confidence_score, 0.0, 1.0))

    dcf = base["dcf"] + (conf - 0.5) * 0.20 - vol_norm * 0.08
    mc = base["mc_p50"] + vol_norm * 0.10 + (0.5 - conf) * 0.05
    multiples = base["multiples"] + (0.55 - conf) * 0.05 - vol_norm * 0.02

    raw = np.array([dcf, mc, multiples], dtype=float)
    raw = np.clip(raw, 0.10, None)
    raw = raw / raw.sum()
    return {"dcf": float(raw[0]), "mc_p50": float(raw[1]), "multiples": float(raw[2])}


def _compute_data_quality_score(dcf_data: dict, forecast_quality: float) -> dict:
    required_files = [
        "data/fundamentals/income_statement.csv",
        "data/fundamentals/balance_sheet.csv",
        "data/fundamentals/cashflow_statement.csv",
        "data/final_forecast_fcf.csv",
        "data/wacc_hdfc.csv",
        "data/peer_ev_ebitda.csv",
        "data/peer_group_hdfc.csv",
    ]
    exists_ratio = float(np.mean([1.0 if resolve_data_path(path).exists() else 0.0 for path in required_files]))

    forecast_df = load_csv("data/final_forecast_fcf.csv")
    non_null_ratio = float(forecast_df.notna().mean().mean())
    latest_year = pd.to_datetime(forecast_df["Year"], errors="coerce").dt.year.max()
    if np.isnan(latest_year):
        recency_score = 0.6
    else:
        year_gap = max(0, datetime.now(timezone.utc).year - int(latest_year))
        recency_score = float(np.clip(1 - year_gap / 6, 0.0, 1.0))

    reconciliation_error = abs(float(dcf_data.get("reconciliation_error_pct", 0.0)))
    consistency_score = _normalize_score_inverse(reconciliation_error, cap=0.35)

    final = (
        0.25 * exists_ratio
        + 0.25 * non_null_ratio
        + 0.20 * recency_score
        + 0.20 * consistency_score
        + 0.10 * forecast_quality
    )
    return {
        "score": float(np.clip(final, 0.0, 1.0)),
        "components": {
            "file_coverage": float(exists_ratio),
            "non_null_ratio": float(non_null_ratio),
            "recency_score": float(recency_score),
            "consistency_score": float(consistency_score),
            "forecast_quality": float(forecast_quality),
        },
    }

def _compute_confidence(
    dcf_value: float,
    multiples_value: float,
    monte_carlo: dict,
    forecast_values: np.ndarray,
    wacc_path: np.ndarray,
    terminal_growth_rate: float,
    data_quality_score: float,
) -> dict:
    mean_val = float(monte_carlo["mean"])
    std_val = float(monte_carlo["std_dev"])
    cv = (std_val / abs(mean_val)) if mean_val != 0 else 1.0
    valuation_gap = (
        abs(dcf_value - multiples_value) / max(abs(dcf_value), abs(multiples_value))
        if max(abs(dcf_value), abs(multiples_value)) > 0
        else 1.0
    )
    probability_undervalued = float(monte_carlo.get("probability_undervalued") or 0.0)

    wacc_path_down = np.clip(wacc_path - 0.01, terminal_growth_rate + 0.001, 0.40)
    wacc_path_up = np.clip(wacc_path + 0.01, terminal_growth_rate + 0.001, 0.40)
    dcf_down = _compute_dcf_with_wacc_path(forecast_values, wacc_path_down, terminal_growth_rate)["enterprise_value"]
    dcf_up = _compute_dcf_with_wacc_path(forecast_values, wacc_path_up, terminal_growth_rate)["enterprise_value"]
    base = _compute_dcf_with_wacc_path(forecast_values, wacc_path, terminal_growth_rate)["enterprise_value"]
    wacc_sensitivity = abs(dcf_down - dcf_up) / abs(base) if base else 1.0

    variance_score = _normalize_score_inverse(cv, cap=0.65)
    valuation_gap_score = _normalize_score_inverse(valuation_gap, cap=0.65)
    undervaluation_score = _normalize_score(probability_undervalued, 0.15, 0.85)
    wacc_sensitivity_score = _normalize_score_inverse(wacc_sensitivity, cap=1.0)
    quality_score = float(np.clip(data_quality_score, 0.0, 1.0))

    confidence_score = (
        0.22 * variance_score
        + 0.22 * valuation_gap_score
        + 0.20 * undervaluation_score
        + 0.18 * wacc_sensitivity_score
        + 0.18 * quality_score
    )

    explanation = [
        f"Variance score {variance_score:.2f} from simulation dispersion (CV={cv:.3f}).",
        f"Valuation gap score {valuation_gap_score:.2f} from DCF vs multiples deviation ({valuation_gap:.3f}).",
        f"Undervaluation score {undervaluation_score:.2f} from probability undervalued ({probability_undervalued:.2%}).",
        f"WACC sensitivity score {wacc_sensitivity_score:.2f} from +/-100 bps path stress ({wacc_sensitivity:.3f}).",
        f"Data quality score {quality_score:.2f} from artifact coverage and consistency checks.",
    ]

    return {
        "confidence_score": float(np.clip(confidence_score, 0.0, 1.0)),
        "components": {
            "variance_score": float(variance_score),
            "valuation_gap_score": float(valuation_gap_score),
            "undervaluation_score": float(undervaluation_score),
            "wacc_sensitivity_score": float(wacc_sensitivity_score),
            "data_quality_score": float(quality_score),
        },
        "explanation": explanation,
        "raw_inputs": {
            "variance_of_simulation": float(cv),
            "valuation_gap": float(valuation_gap),
            "probability_undervalued": float(probability_undervalued),
            "wacc_sensitivity": float(wacc_sensitivity),
            "data_quality_score": float(quality_score),
        },
    }


def _build_ai_summary(summary: dict, confidence: dict, triangulation: dict) -> dict:
    confidence_score = float(confidence["confidence_score"])
    upside = float(summary["upside_to_p50_pct"])
    if confidence_score >= 0.67 and upside > 6:
        signal = "BUY"
    elif confidence_score <= 0.35 and upside < 0:
        signal = "SELL"
    else:
        signal = "HOLD"

    drivers = (
        f"Growth input {summary.get('forecast_growth_rate_pct', 0.0):.2f}%, "
        f"base WACC {summary['dynamic_wacc_base']:.2%}, and leverage ratio {summary.get('leverage_ratio', 0.0):.2f} "
        "are the key valuation drivers."
    )
    multiples_text = (
        "Multiples valuation derived using peer median EV/EBITDA "
        f"{summary.get('median_ev_ebitda', 0.0):.2f}"
    )
    if summary.get("median_price_to_book") is not None:
        multiples_text += f" and P/B {summary['median_price_to_book']:.2f}."
    else:
        multiples_text += "."

    explanation = [
        "Dynamic WACC state equation used for discount-rate path construction.",
        f"Monte Carlo simulation with {int(summary.get('monte_carlo_iterations', 0))} runs: "
        f"P10 {summary['p10']:,.0f}, P50 {summary['p50']:,.0f}, P90 {summary['p90']:,.0f}.",
        drivers,
        multiples_text,
        "Final valuation combines DCF, Monte Carlo median, and multiples with adaptive weights "
        f"{triangulation['weights']}.",
        f"Confidence score {confidence_score:.2f} integrates variance, valuation gap, undervaluation, WACC sensitivity, and data quality.",
    ]

    if signal == "BUY":
        insight = "Probability-weighted valuation and confidence support accumulation."
    elif signal == "SELL":
        insight = "Distribution and confidence indicate unfavorable risk-adjusted entry."
    else:
        insight = "Valuation is balanced; wait for stronger dislocation or confidence improvement."

    return {
        "signal": signal,
        "upside_percent": float(upside),
        "explanation": explanation,
        "investment_insight": insight,
    }


def _estimate_forecast_growth_rate_pct(forecast: list[dict]) -> float:
    means = np.array([float(row["fcf_mean"]) for row in forecast], dtype=float)
    if len(means) < 2:
        return 0.0
    prev = np.maximum(np.abs(means[:-1]), 1.0)
    growth = (means[1:] / prev) - 1
    return float(np.mean(growth) * 100)


def _estimate_growth_volatility(forecast: list[dict]) -> float:
    means = np.array([float(row["fcf_mean"]) for row in forecast], dtype=float)
    uppers = np.array([float(row["fcf_upper"]) for row in forecast], dtype=float)
    lowers = np.array([float(row["fcf_lower"]) for row in forecast], dtype=float)
    if len(means) == 0:
        return 0.0
    stds = np.maximum((uppers - lowers) / 3.29, np.maximum(np.abs(means) * 0.03, 1.0))
    rel_std = stds / np.maximum(np.abs(means), 1.0)
    return float(np.mean(rel_std))


def _reliability_label(confidence_score: float) -> str:
    if confidence_score >= 0.70:
        return "High confidence"
    if confidence_score >= 0.45:
        return "Moderate reliability"
    return "Low confidence"


def _build_digital_twin_from_report(report: dict) -> dict:
    return {
        "ticker": report["ticker"],
        "generated_at": report["generated_at"],
        "mode": report["mode"],
        "digital_twin": {
            "fcf_model": {
                "method": "artifact_forecast_with_ml_fallback",
                "horizon_years": len(report["fcf_forecast"]),
                "forecast": report["fcf_forecast"],
            },
            "wacc_model": {
                "formula": report["dynamic_wacc"]["formula"],
                "parameters": report["dynamic_wacc"]["parameters"],
                "inputs": report["dynamic_wacc"]["inputs"],
                "decomposition": report["dynamic_wacc"]["decomposition"],
                "scenarios": report["dynamic_wacc"]["scenarios"],
                "time_varying_wacc": report["dynamic_wacc"]["time_varying_wacc"],
            },
            "risk_engine": {
                "iterations": report["monte_carlo"]["iterations"],
                "distribution": {
                    "p10": report["monte_carlo"]["p10"],
                    "p50": report["monte_carlo"]["p50"],
                    "p90": report["monte_carlo"]["p90"],
                    "mean": report["monte_carlo"]["mean"],
                    "std_dev": report["monte_carlo"]["std_dev"],
                },
                "probability_undervalued": report["monte_carlo"]["probability_undervalued"],
            },
            "valuation_engine": {
                "dcf_value": report["summary"]["dcf_value"],
                "multiples_value": report["summary"]["multiples_value"],
                "blended_value": report["summary"]["blended_value"],
                "triangulation_weights": report["triangulation"]["weights"],
                "confidence_score": report["confidence"]["confidence_score"],
            },
        },
    }

def build_internal_full_report(ticker: str, market: str) -> dict:
    profile = get_profile(ticker=ticker, market=market)
    if not profile["full_pipeline_available"]:
        raise ValueError(
            f"Ticker '{profile['ticker']}' exists in internal universe but does not have full reproducible pipeline artifacts."
        )

    forecast, forecast_quality = _load_fcf_forecast()
    forecast_years = [str(row["year"])[:4] for row in forecast]
    dynamic_wacc = _compute_dynamic_wacc(profile=profile, forecast_years=forecast_years)

    terminal_growth_rate = 0.04 if profile["market"] in {"NSE", "BSE"} else 0.025
    forecast_values = np.array([float(row["fcf_mean"]) for row in forecast], dtype=float)
    wacc_path = np.array([float(item["wacc"]) for item in dynamic_wacc["time_varying_wacc"]], dtype=float)

    dcf_calc = _compute_dcf_with_wacc_path(
        fcf_values=forecast_values,
        wacc_path=wacc_path,
        terminal_growth_rate=terminal_growth_rate,
    )

    dcf_stored = load_csv("data/dcf_hdfc.csv", required_columns=["enterprise_value"]).iloc[0]
    stored_ev = float(dcf_stored["enterprise_value"])
    dcf_data = {
        "ticker": profile["ticker"],
        "enterprise_value": float(dcf_calc["enterprise_value"]),
        "wacc": float(dynamic_wacc["base_wacc"]),
        "terminal_growth_rate": float(terminal_growth_rate),
        "pv_forecast": float(dcf_calc["pv_forecast"]),
        "terminal_value": float(dcf_calc["terminal_value"]),
        "pv_terminal_value": float(dcf_calc["pv_terminal_value"]),
        "stored_enterprise_value": float(stored_ev),
        "reconciliation_error_pct": float(abs(dcf_calc["enterprise_value"] - stored_ev) / abs(stored_ev)),
    }

    monte_carlo = _run_monte_carlo(
        forecast=forecast,
        dynamic_wacc=dynamic_wacc,
        terminal_growth_rate=terminal_growth_rate,
        base_value=float(dcf_data["enterprise_value"]),
    )

    multiples = _compute_multiples(profile)
    multiples_anchor_value = float(multiples["implied_value_ev_ebitda"])
    if multiples["selected_anchor"] == "price_to_book" and multiples["implied_value_price_to_book"] is not None:
        multiples_anchor_value = float(multiples["implied_value_price_to_book"])

    data_quality = _compute_data_quality_score(dcf_data=dcf_data, forecast_quality=forecast_quality)
    confidence = _compute_confidence(
        dcf_value=float(dcf_data["enterprise_value"]),
        multiples_value=float(multiples_anchor_value),
        monte_carlo=monte_carlo,
        forecast_values=forecast_values,
        wacc_path=wacc_path,
        terminal_growth_rate=float(terminal_growth_rate),
        data_quality_score=float(data_quality["score"]),
    )

    weights = _triangulation_weights_for_sector(
        sector=profile["sector"],
        volatility=float(dynamic_wacc["market_volatility"]),
        confidence_score=float(confidence["confidence_score"]),
    )
    blended_value = (
        weights["dcf"] * float(dcf_data["enterprise_value"])
        + weights["mc_p50"] * float(monte_carlo["p50"])
        + weights["multiples"] * float(multiples_anchor_value)
    )
    triangulation = {
        "sector": profile["sector"],
        "anchor_used": str(multiples["selected_anchor"]),
        "weights": {k: float(v) for k, v in weights.items()},
        "blended_value": float(blended_value),
    }

    dcf_value = float(dcf_data["enterprise_value"])
    p10 = float(monte_carlo["p10"])
    p50 = float(monte_carlo["p50"])
    p90 = float(monte_carlo["p90"])
    probability_undervalued = float(monte_carlo["probability_undervalued"] or 0.0)

    summary = {
        "ticker": profile["ticker"],
        "sector": profile["sector"],
        "dcf_value": dcf_value,
        "multiples_value": float(multiples_anchor_value),
        "blended_value": float(blended_value),
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "probability_undervalued": probability_undervalued,
        "confidence_score": float(confidence["confidence_score"]),
        "upside_to_p50_pct": float(((p50 / dcf_value) - 1) * 100 if dcf_value else 0.0),
        "upside_to_p90_pct": float(((p90 / dcf_value) - 1) * 100 if dcf_value else 0.0),
        "downside_to_p10_pct": float(((p10 / dcf_value) - 1) * 100 if dcf_value else 0.0),
        "triangulation_weights": {k: float(v) for k, v in weights.items()},
        "dynamic_wacc_base": float(dynamic_wacc["base_wacc"]),
        "forecast_growth_rate_pct": float(_estimate_forecast_growth_rate_pct(forecast)),
        "leverage_ratio": float(dynamic_wacc["leverage_ratio"]),
        "median_ev_ebitda": float(multiples["median_ev_ebitda"]),
        "median_price_to_book": multiples.get("median_price_to_book"),
        "monte_carlo_iterations": int(monte_carlo["iterations"]),
        "unit": "INR",
    }

    risk_summary = [
        {"metric": "Base DCF Value", "value": dcf_value},
        {"metric": "P10 (Bear Case)", "value": p10},
        {"metric": "P50 (Median)", "value": p50},
        {"metric": "P90 (Bull Case)", "value": p90},
        {"metric": "Blended Triangulated Value", "value": float(blended_value)},
        {"metric": "Upside to P90 (%)", "value": summary["upside_to_p90_pct"]},
        {"metric": "Downside to P10 (%)", "value": summary["downside_to_p10_pct"]},
        {"metric": "Probability Undervalued", "value": probability_undervalued},
    ]

    dcf_multiples_deviation_pct = float(
        abs(dcf_value - float(multiples_anchor_value)) / max(abs(dcf_value), abs(float(multiples_anchor_value)), 1.0) * 100
    )
    variance_ratio = float(
        float(monte_carlo["std_dev"]) / max(abs(float(monte_carlo["mean"])), 1.0)
    )
    reliability_label = _reliability_label(float(confidence["confidence_score"]))

    model_inputs = {
        "dcf_inputs": {
            "forecast_growth_rate_pct": float(summary["forecast_growth_rate_pct"]),
            "terminal_growth_rate_pct": float(terminal_growth_rate * 100),
            "forecast_horizon_years": int(len(forecast)),
        },
        "wacc_breakdown": {
            **dynamic_wacc.get("wacc_breakdown_inputs", {}),
        },
        "monte_carlo_inputs": {
            "simulations": int(monte_carlo["iterations"]),
            "growth_volatility": float(_estimate_growth_volatility(forecast)),
            "wacc_volatility": 0.0045,
            "distribution_assumptions": "FCF ~ Normal(mean_t, sigma_t), WACC path ~ Scenario mixture + Gaussian noise",
        },
    }

    validation_diagnostics = {
        "dcf_multiples_deviation_pct": float(dcf_multiples_deviation_pct),
        "monte_carlo_variance_ratio": float(variance_ratio),
        "probability_undervalued": float(probability_undervalued),
        "confidence_breakdown": {k: float(v) for k, v in confidence["components"].items()},
        "reliability_label": reliability_label,
        "warnings": [],
    }

    market_value = multiples.get("target_market_cap")
    comparison_metrics = {
        "model_value": float(blended_value),
        "market_value": (float(market_value) if market_value is not None else None),
        "error_pct": (
            float(abs(float(blended_value) - float(market_value)) / max(abs(float(market_value)), 1.0) * 100)
            if market_value is not None
            else None
        ),
        "label": "Unavailable",
    }
    if comparison_metrics["error_pct"] is not None:
        diff = float(blended_value) - float(market_value)
        if abs(diff) / max(abs(float(market_value)), 1.0) <= 0.10:
            comparison_metrics["label"] = "Fair"
        elif diff > 0:
            comparison_metrics["label"] = "Undervalued"
        else:
            comparison_metrics["label"] = "Overvalued"

    performance_metrics = {
        "absolute_error_pct": comparison_metrics["error_pct"],
        "stability_variance_ratio": float(variance_ratio),
        "wacc_sensitivity_pct": float(confidence["raw_inputs"]["wacc_sensitivity"] * 100),
        "scenario_spread": float(p90 - p10),
    }

    statements = _load_internal_statements()
    ai_summary = _build_ai_summary(summary=summary, confidence=confidence, triangulation=triangulation)

    report = {
        "ticker": profile["ticker"],
        "generated_at": datetime.now(timezone.utc),
        "mode": "internal",
        "dcf": dcf_data,
        "dynamic_wacc": dynamic_wacc,
        "monte_carlo": monte_carlo,
        "multiples": multiples,
        "triangulation": triangulation,
        "data_quality": data_quality,
        "fcf_forecast": forecast,
        "risk_summary": risk_summary,
        "confidence": confidence,
        "summary": summary,
        "ai_summary": ai_summary,
        "statements": statements,
        "model_inputs": model_inputs,
        "validation_diagnostics": validation_diagnostics,
        "comparison_metrics": comparison_metrics,
        "performance_metrics": performance_metrics,
    }
    report["digital_twin"] = _build_digital_twin_from_report(report)["digital_twin"]
    return report


def build_internal_statements(ticker: str, market: str) -> dict:
    profile = get_profile(ticker=ticker, market=market)
    if not profile["full_pipeline_available"]:
        raise ValueError(
            f"Ticker '{profile['ticker']}' exists in internal universe but statements artifacts are not configured."
        )
    return {
        "ticker": profile["ticker"],
        "generated_at": datetime.now(timezone.utc),
        "statements": _load_internal_statements(),
    }


def build_internal_digital_twin(ticker: str, market: str) -> dict:
    report = build_internal_full_report(ticker=ticker, market=market)
    return _build_digital_twin_from_report(report)


def build_digital_twin_from_report(report: dict) -> dict:
    return _build_digital_twin_from_report(report)
