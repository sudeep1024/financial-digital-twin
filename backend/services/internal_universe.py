from __future__ import annotations

from backend.utils.loader import load_csv


def _normalize_symbol(ticker_or_symbol: str, market: str) -> tuple[str, str]:
    raw = ticker_or_symbol.upper().strip()
    market = market.upper().strip()
    if "." in raw:
        if raw.endswith(".NS"):
            return raw, "NSE"
        if raw.endswith(".BO"):
            return raw, "BSE"
        return raw, market

    if market == "NSE":
        return f"{raw}.NS", market
    if market == "BSE":
        return f"{raw}.BO", market
    return raw, market


def load_ticker_profiles() -> list[dict]:
    df = load_csv(
        "data/ticker_profiles.csv",
        required_columns=["ticker", "symbol", "market", "name", "sector", "full_pipeline_available"],
    ).copy()

    profiles: list[dict] = []
    for _, row in df.iterrows():
        profiles.append(
            {
                "ticker": str(row["ticker"]).strip().upper(),
                "symbol": str(row["symbol"]).strip().upper(),
                "market": str(row["market"]).strip().upper(),
                "name": str(row["name"]).strip(),
                "sector": str(row["sector"]).strip(),
                "full_pipeline_available": bool(int(row["full_pipeline_available"])),
                "price_file": str(row.get("price_file", "") or "").strip(),
                "market_price_file": str(row.get("market_price_file", "") or "").strip(),
            }
        )
    return profiles


def get_profile(ticker: str, market: str) -> dict:
    normalized, normalized_market = _normalize_symbol(ticker, market)
    profiles = load_ticker_profiles()
    for profile in profiles:
        if (
            profile["ticker"] == normalized
            or (profile["symbol"] == ticker.upper().strip() and profile["market"] == normalized_market)
        ):
            return profile

    raise ValueError(
        f"Ticker '{ticker}' is not configured in internal reproducible dataset for market '{market.upper()}'."
    )


def search_tickers(market: str, query: str = "", limit: int = 200) -> dict:
    market = market.upper().strip()
    query_u = query.upper().strip()
    limit = max(1, min(int(limit), 5000))

    profiles = [p for p in load_ticker_profiles() if p["market"] == market and p["full_pipeline_available"]]
    if query_u:
        profiles = [
            p
            for p in profiles
            if p["symbol"].startswith(query_u) or query_u in p["name"].upper() or p["ticker"].startswith(query_u)
        ]

    profiles = sorted(profiles, key=lambda x: x["symbol"])
    tickers = [
        {
            "symbol": p["symbol"],
            "name": p["name"],
            "market": p["market"],
            "yahoo_ticker": p["ticker"],
        }
        for p in profiles[:limit]
    ]

    return {
        "market": market,
        "total": len(profiles),
        "returned": len(tickers),
        "query": query_u,
        "tickers": tickers,
    }
