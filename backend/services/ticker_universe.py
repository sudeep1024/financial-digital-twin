from __future__ import annotations

import csv
import io
import json
import time
import urllib.parse
import urllib.request


UNIVERSE_TTL_SECONDS = 24 * 60 * 60
_UNIVERSE_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _dedupe(records: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for row in records:
        key = f"{row['market']}::{row['symbol']}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _fetch_nse() -> list[dict]:
    raw = _http_get("https://archives.nseindia.com/content/equities/EQUITY_L.csv")
    reader = csv.DictReader(io.StringIO(raw))
    records = []
    for row in reader:
        symbol = str(row.get("SYMBOL", "")).strip().upper()
        name = str(row.get("NAME OF COMPANY", "")).strip()
        if not symbol or not name:
            continue
        records.append(
            {
                "symbol": symbol,
                "name": name,
                "market": "NSE",
                "yahoo_ticker": f"{symbol}.NS",
            }
        )
    return records


def _fetch_bse() -> list[dict]:
    params = urllib.parse.urlencode({"segment": "Equity", "status": "Active"})
    url = f"https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?{params}"
    raw = _http_get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bseindia.com/corporates/List_Scrips.html",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=60,
    )
    payload = json.loads(raw)
    records = []
    for row in payload:
        symbol = str(row.get("scrip_id", "")).strip().upper()
        name = str(row.get("Issuer_Name") or row.get("Scrip_Name") or "").strip()
        if not symbol or not name:
            continue
        records.append(
            {
                "symbol": symbol,
                "name": name,
                "market": "BSE",
                "yahoo_ticker": f"{symbol}.BO",
            }
        )
    return records


def _fetch_nasdaq_or_nyse(market: str) -> list[dict]:
    if market == "NASDAQ":
        raw = _http_get("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
        reader = csv.DictReader(io.StringIO(raw), delimiter="|")
        rows = [r for r in reader if str(r.get("Test Issue", "")).strip().upper() == "N"]
        records = []
        for row in rows:
            symbol = str(row.get("Symbol", "")).strip().upper()
            name = str(row.get("Security Name", "")).strip()
            if not symbol or not name:
                continue
            records.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "market": "NASDAQ",
                    "yahoo_ticker": symbol,
                }
            )
        return records

    raw = _http_get("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")
    reader = csv.DictReader(io.StringIO(raw), delimiter="|")
    rows = [
        r
        for r in reader
        if str(r.get("Test Issue", "")).strip().upper() == "N"
        and str(r.get("Exchange", "")).strip().upper() == "N"
    ]
    records = []
    for row in rows:
        symbol = str(row.get("ACT Symbol", "")).strip().upper()
        name = str(row.get("Security Name", "")).strip()
        if not symbol or not name:
            continue
        records.append(
            {
                "symbol": symbol,
                "name": name,
                "market": "NYSE",
                "yahoo_ticker": symbol,
            }
        )
    return records


def _load_market_universe(market: str) -> list[dict]:
    market = market.upper().strip()
    now = time.time()
    cached = _UNIVERSE_CACHE.get(market)
    if cached and (now - cached[0]) < UNIVERSE_TTL_SECONDS:
        return cached[1]

    if market == "NSE":
        records = _fetch_nse()
    elif market == "BSE":
        records = _fetch_bse()
    elif market in {"NASDAQ", "NYSE"}:
        records = _fetch_nasdaq_or_nyse(market)
    else:
        records = []

    records = _dedupe(records)
    records.sort(key=lambda item: item["symbol"])
    _UNIVERSE_CACHE[market] = (now, records)
    return records


def search_tickers(market: str, query: str = "", limit: int = 100) -> dict:
    market = market.upper().strip()
    query = query.strip().upper()
    limit = max(1, min(limit, 20000))

    all_records = _load_market_universe(market)
    if not query:
        filtered = all_records
    else:
        filtered = [
            row
            for row in all_records
            if row["symbol"].startswith(query) or query in row["name"].upper()
        ]

    tickers = filtered[:limit]
    return {
        "market": market,
        "total": len(filtered),
        "returned": len(tickers),
        "query": query,
        "tickers": tickers,
    }
