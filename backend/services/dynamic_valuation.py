from __future__ import annotations

import copy
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from backend.services.dcf import compute_dcf_value


REPORT_TTL_SECONDS = 15 * 60
_REPORT_CACHE: dict[str, tuple[float, dict]] = {}


MARKET_SUFFIX = {
    "NSE": ".NS",
    "BSE": ".BO",
    "NASDAQ": "",
    "NYSE": "",
    "LSE": ".L",
}

RISK_FREE_RATE = {
    "NSE": 0.070,
    "BSE": 0.070,
    "NASDAQ": 0.045,
    "NYSE": 0.045,
    "LSE": 0.040,
}

TERMINAL_GROWTH = {
    "NSE": 0.040,
    "BSE": 0.040,
    "NASDAQ": 0.025,
    "NYSE": 0.025,
    "LSE": 0.020,
}


# ---------------------------------------------------------------------------
# Hybrid Intrinsic Value formula
# IV = w1*median + w2*mean + w3*scenario_value + w4*risk_adjustment
# ---------------------------------------------------------------------------

def compute_intrinsic_value(mean: float, median: float, p10: float, p90: float, std: float) -> tuple[float, float, float]:
    """Compute Hybrid Intrinsic Value.

    Returns (iv, alpha, v_scenario).
    """
    v_scenario = 0.20 * p10 + 0.60 * median + 0.20 * p90

    denom = mean + std
    alpha = 0.0 if denom == 0 else float(1 - (std / denom))
    risk_adjustment = alpha * mean

    w1, w2, w3, w4 = 0.30, 0.30, 0.30, 0.10
    iv = (
        w1 * median
        + w2 * mean
        + w3 * v_scenario
        + w4 * risk_adjustment
    )
    return float(iv), float(alpha), float(v_scenario)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _normalize_ticker(ticker: str, market: str) -> str:
    ticker = ticker.upper().strip()
    market = market.upper().strip()
    if "." in ticker:
        return ticker
    suffix = MARKET_SUFFIX.get(market, "")
    return f"{ticker}{suffix}"


def _sort_series_by_date_desc(series: pd.Series) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce").dropna()
    if out.empty:
        return out
    try:
        out = out.sort_index(ascending=False)
    except Exception:
        pass
    return out


def _sort_series_by_date_asc(series: pd.Series) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce").dropna()
    if out.empty:
        return out
    try:
        out = out.sort_index(ascending=True)
    except Exception:
        pass
    return out


def _row_latest(df: pd.DataFrame, row_names: list[str]) -> float | None:
    if df is None or df.empty:
        return None
    for row in row_names:
        if row in df.index:
            s = _sort_series_by_date_desc(df.loc[row])
            if not s.empty:
                return _safe_float(s.iloc[0], default=0.0)
    return None


def _extract_fcf_series(cashflow_df: pd.DataFrame) -> pd.Series:
    if cashflow_df is None or cashflow_df.empty:
        return pd.Series(dtype=float)

    if "Free Cash Flow" in cashflow_df.index:
        fcf = _sort_series_by_date_asc(cashflow_df.loc["Free Cash Flow"])
        if not fcf.empty:
            return fcf

    if "Operating Cash Flow" in cashflow_df.index and "Capital Expenditure" in cashflow_df.index:
        ocf = _sort_series_by_date_asc(cashflow_df.loc["Operating Cash Flow"])
        capex = _sort_series_by_date_asc(cashflow_df.loc["Capital Expenditure"])
        merged = pd.concat([ocf, capex], axis=1, join="inner")
        if not merged.empty:
            fcf = merged.iloc[:, 0] + merged.iloc[:, 1]
            fcf = pd.to_numeric(fcf, errors="coerce").dropna()
            if not fcf.empty:
                return fcf

    return pd.Series(dtype=float)


def _estimate_growth_rate(fcf_series: pd.Series, info: dict) -> float:
    if len(fcf_series) >= 2:
        clean = fcf_series.copy()
        min_abs = max(clean.abs().median() * 0.25, 1.0)
        clean = clean.mask(clean.abs() < min_abs, np.nan).dropna()
        if len(clean) >= 2:
            start = abs(_safe_float(clean.iloc[0], default=1.0))
            end = abs(_safe_float(clean.iloc[-1], default=start))
            years = max(1, len(clean) - 1)
            if start > 0:
                cagr = (end / start) ** (1 / years) - 1
                return float(np.clip(cagr, -0.05, 0.18))

    for key in ("revenueGrowth", "earningsGrowth"):
        val = info.get(key)
        if val is not None:
            return float(np.clip(_safe_float(val), -0.05, 0.18))
    return 0.06


def _forecast_fcf(base_fcf: float, growth: float, years: int = 5) -> list[dict]:
    now_year = datetime.now(timezone.utc).year
    rows = []
    for i in range(1, years + 1):
        fcf_mean = base_fcf * ((1 + growth) ** i)
        uncertainty = 0.15 + (0.03 * i)
        fcf_upper = fcf_mean * (1 + uncertainty)
        fcf_lower = max(0.0, fcf_mean * (1 - uncertainty))
        rows.append(
            {
                "year": f"{now_year + i}",
                "fcf_mean": float(fcf_mean),
                "fcf_upper": float(fcf_upper),
                "fcf_lower": float(fcf_lower),
            }
        )
    return rows


def _compute_wacc(info: dict, income_df: pd.DataFrame, market: str, terminal_growth: float) -> tuple[float, dict]:
    market = market.upper().strip()
    rf = RISK_FREE_RATE.get(market, 0.045)
    mrp = 0.055
    beta = _safe_float(info.get("beta"), default=1.0)
    beta = float(np.clip(beta, 0.2, 2.5))
    cost_of_equity = rf + (beta * mrp)

    market_cap = max(_safe_float(info.get("marketCap")), 0.0)
    total_debt = max(_safe_float(info.get("totalDebt")), 0.0)

    interest_expense = _row_latest(income_df, ["Interest Expense"])
    if total_debt > 0 and interest_expense is not None:
        cost_of_debt = abs(_safe_float(interest_expense)) / total_debt
        cost_of_debt = float(np.clip(cost_of_debt, 0.02, 0.18))
    else:
        cost_of_debt = 0.07

    tax_rate = _safe_float(info.get("effectiveTaxRate"), default=0.25)
    if tax_rate <= 0:
        inferred_tax = _row_latest(income_df, ["Tax Rate For Calcs"])
        if inferred_tax is not None:
            tax_rate = _safe_float(inferred_tax, default=0.25)
    tax_rate = float(np.clip(tax_rate, 0.0, 0.40))

    total_capital = market_cap + total_debt
    if total_capital <= 0:
        total_capital = max(market_cap, 1.0)

    wacc = (
        (market_cap / total_capital) * cost_of_equity
        + (total_debt / total_capital) * cost_of_debt * (1 - tax_rate)
    )
    lower_bound = terminal_growth + 0.02
    wacc = float(np.clip(wacc, lower_bound, 0.25))

    return wacc, {
        "beta": beta,
        "risk_free_rate": rf,
        "market_risk_premium": mrp,
        "cost_of_equity": float(cost_of_equity),
        "cost_of_debt": float(cost_of_debt),
        "tax_rate": tax_rate,
    }


def _build_histogram(values: np.ndarray, bins: int = 40) -> list[dict]:
    counts, edges = np.histogram(values, bins=bins)
    result = []
    for i, count in enumerate(counts):
        result.append(
            {
                "bin_start": float(edges[i]),
                "bin_end": float(edges[i + 1]),
                "count": int(count),
            }
        )
    return result


def _run_monte_carlo(base_fcf: float, growth: float, wacc: float, terminal_growth: float, base_value: float) -> dict:
    rng = np.random.default_rng()
    iterations = 1000
    horizon = 5

    growth_samples = rng.normal(loc=growth, scale=0.03, size=iterations)
    growth_samples = np.clip(growth_samples, -0.20, 0.25)

    wacc_samples = rng.normal(loc=wacc, scale=0.012, size=iterations)
    wacc_samples = np.clip(wacc_samples, terminal_growth + 0.005, 0.35)

    years = np.arange(1, horizon + 1, dtype=float)
    fcf_paths = base_fcf * np.power(1 + growth_samples[:, None], years[None, :])
    discount = np.power(1 + wacc_samples[:, None], years[None, :])
    pv_forecast = (fcf_paths / discount).sum(axis=1)

    terminal_fcf = fcf_paths[:, -1]
    terminal_value = (terminal_fcf * (1 + terminal_growth)) / (wacc_samples - terminal_growth)
    pv_terminal = terminal_value / np.power(1 + wacc_samples, horizon)
    valuations = pv_forecast + pv_terminal
    valuations = valuations[np.isfinite(valuations)]

    if len(valuations) < 1000:
        raise ValueError("Monte Carlo simulation did not generate enough valid samples.")

    mean_value = float(np.mean(valuations))
    std_value = float(np.std(valuations, ddof=1))
    p10 = float(np.quantile(valuations, 0.10))
    p50 = float(np.quantile(valuations, 0.50))
    p90 = float(np.quantile(valuations, 0.90))
    probability_undervalued = float(np.mean(valuations > base_value))

    return {
        "iterations": int(len(valuations)),
        "mean": mean_value,
        "std_dev": std_value,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "min": float(np.min(valuations)),
        "max": float(np.max(valuations)),
        "probability_undervalued": probability_undervalued,
        "histogram": _build_histogram(valuations),
    }


def _statement_rows(df: pd.DataFrame, rows: list[str]) -> list[dict]:
    if df is None or df.empty:
        return []

    out = []
    for metric in rows:
        if metric not in df.index:
            continue
        values = _sort_series_by_date_desc(df.loc[metric])
        if values.empty:
            continue

        row_values: dict[str, float] = {}
        for idx, val in values.iloc[:4].items():
            year_label = str(getattr(idx, "year", str(idx)))
            row_values[year_label] = float(val)

        if row_values:
            out.append({"metric": metric, "values": row_values})
    return out


def _build_statements(income_df: pd.DataFrame, balance_df: pd.DataFrame, cashflow_df: pd.DataFrame) -> dict:
    return {
        "income_statement": _statement_rows(
            income_df,
            [
                "Total Revenue",
                "Operating Income",
                "Pretax Income",
                "Net Income",
                "EBITDA",
                "Tax Provision",
            ],
        ),
        "balance_sheet": _statement_rows(
            balance_df,
            [
                "Total Assets",
                "Total Liabilities Net Minority Interest",
                "Common Stock Equity",
                "Cash And Cash Equivalents",
                "Total Debt",
                "Net Debt",
            ],
        ),
        "cash_flow": _statement_rows(
            cashflow_df,
            [
                "Operating Cash Flow",
                "Capital Expenditure",
                "Free Cash Flow",
                "Investing Cash Flow",
                "Financing Cash Flow",
            ],
        ),
    }


def _to_score_from_ratio(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    normalized = min(max(value, 0.0), cap) / cap
    return float(1 - normalized)


def _build_ai_summary(summary: dict, dcf_data: dict, mc_data: dict, multiples_data: dict, confidence_data: dict) -> dict:
    confidence_score = float(confidence_data["confidence_score"])
    upside = float(summary["upside_to_p50_pct"])

    if confidence_score >= 0.65 and upside > 5:
        signal = "BUY"
    elif confidence_score <= 0.35 and upside < 0:
        signal = "SELL"
    else:
        signal = "HOLD"

    explanation = [
        f"DCF intrinsic value is {dcf_data['enterprise_value']:,.0f} using WACC {dcf_data['wacc']:.2%}.",
        f"Monte Carlo distribution range: P10 {mc_data['p10']:,.0f}, P50 {mc_data['p50']:,.0f}, P90 {mc_data['p90']:,.0f}.",
        f"Relative multiple model implies equity value near {multiples_data['implied_value_ev_ebitda']:,.0f}.",
        f"Confidence score is {confidence_score:.2f} with undervaluation probability {summary['probability_undervalued']:.2%}.",
    ]

    if signal == "BUY":
        insight = "Valuation spread and confidence support accumulation with risk monitoring."
    elif signal == "SELL":
        insight = "Risk-adjusted valuation appears unfavorable versus the intrinsic distribution."
    else:
        insight = "Signal is balanced; wait for better valuation dislocation or stronger confidence."

    return {
        "signal": signal,
        "upside_percent": float(upside),
        "explanation": explanation,
        "investment_insight": insight,
    }


def _build_report(ticker: str, market: str) -> dict:
    market = market.upper().strip()
    full_ticker = _normalize_ticker(ticker=ticker, market=market)

    tk = yf.Ticker(full_ticker)
    info = tk.info or {}
    if not info:
        raise ValueError(f"Unable to load market data for ticker '{full_ticker}'.")

    cashflow_df = tk.cashflow
    income_df = tk.financials
    balance_df = tk.balance_sheet
    if cashflow_df is None or cashflow_df.empty:
        raise ValueError(f"Cash flow statements are unavailable for ticker '{full_ticker}'.")

    fcf_series = _extract_fcf_series(cashflow_df)
    if fcf_series.empty:
        raise ValueError(f"Unable to derive Free Cash Flow history for ticker '{full_ticker}'.")

    market_cap = max(_safe_float(info.get("marketCap")), 0.0)
    total_debt = max(_safe_float(info.get("totalDebt")), 0.0)
    total_cash = max(_safe_float(info.get("totalCash")), 0.0)
    enterprise_value_stored = _safe_float(info.get("enterpriseValue"))
    ebitda = _safe_float(info.get("ebitda"))
    net_income = _safe_float(info.get("netIncomeToCommon"))

    latest_fcf = _safe_float(fcf_series.iloc[-1], default=0.0)
    if latest_fcf <= 0:
        fallback_from_info = _safe_float(info.get("freeCashflow"), default=0.0)
        latest_fcf = fallback_from_info if fallback_from_info > 0 else max(market_cap * 0.01, 1_000_000.0)

    growth = _estimate_growth_rate(fcf_series=fcf_series, info=info)
    terminal_growth = TERMINAL_GROWTH.get(market, 0.025)
    wacc, wacc_inputs = _compute_wacc(
        info=info,
        income_df=income_df,
        market=market,
        terminal_growth=terminal_growth,
    )

    forecast = _forecast_fcf(base_fcf=latest_fcf, growth=growth, years=5)
    fcf_values = np.array([row["fcf_mean"] for row in forecast], dtype=float)
    dcf_calc = compute_dcf_value(
        fcf_values=fcf_values,
        wacc=wacc,
        terminal_growth_rate=terminal_growth,
    )

    dcf_enterprise = float(dcf_calc["enterprise_value"])
    reconciliation_error = 0.0
    if enterprise_value_stored > 0:
        reconciliation_error = abs(dcf_enterprise - enterprise_value_stored) / enterprise_value_stored

    dcf_data = {
        "ticker": full_ticker,
        "enterprise_value": dcf_enterprise,
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth,
        "pv_forecast": float(dcf_calc["pv_forecast"]),
        "terminal_value": float(dcf_calc["terminal_value"]),
        "pv_terminal_value": float(dcf_calc["pv_terminal_value"]),
        "stored_enterprise_value": float(enterprise_value_stored),
        "reconciliation_error_pct": float(reconciliation_error),
    }

    mc_data = _run_monte_carlo(
        base_fcf=latest_fcf,
        growth=growth,
        wacc=wacc,
        terminal_growth=terminal_growth,
        base_value=dcf_enterprise,
    )

    median_ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), default=0.0)
    if median_ev_ebitda <= 0 and ebitda > 0 and enterprise_value_stored > 0:
        median_ev_ebitda = enterprise_value_stored / ebitda
    if median_ev_ebitda <= 0:
        median_ev_ebitda = 10.0

    implied_enterprise = dcf_enterprise
    if ebitda > 0:
        implied_enterprise = median_ev_ebitda * ebitda

    implied_equity_ev = implied_enterprise + total_cash - total_debt
    if implied_equity_ev <= 0:
        implied_equity_ev = market_cap if market_cap > 0 else dcf_enterprise

    median_pe = _safe_float(info.get("trailingPE"), default=0.0)
    if median_pe <= 0:
        median_pe = _safe_float(info.get("forwardPE"), default=0.0)
    if median_pe <= 0:
        median_pe = 18.0

    implied_value_pe = (median_pe * net_income) if net_income > 0 else None

    peer_count = 1
    sector_key = info.get("sectorKey")
    if sector_key:
        try:
            peer_df = yf.Sector(sector_key).top_companies
            if hasattr(peer_df, "shape"):
                peer_count = int(peer_df.shape[0])
        except Exception:
            peer_count = 1

    multiples_data = {
        "target_ticker": full_ticker,
        "peer_count": int(max(peer_count, 1)),
        "median_ev_ebitda": float(median_ev_ebitda),
        "implied_enterprise_value_ev_ebitda": float(implied_enterprise),
        "implied_value_ev_ebitda": float(implied_equity_ev),
        "median_pe": float(median_pe),
        "implied_value_pe": (float(implied_value_pe) if implied_value_pe is not None else None),
    }

    dcf_value = float(dcf_data["enterprise_value"])
    p10 = float(mc_data["p10"])
    p50 = float(mc_data["p50"])
    p90 = float(mc_data["p90"])
    multiples_value = float(multiples_data["implied_value_ev_ebitda"])

    # --- Hybrid Intrinsic Value ---
    mc_mean = float(mc_data["mean"])
    mc_std = float(mc_data["std_dev"])
    iv, risk_alpha, v_scenario = compute_intrinsic_value(
        mean=mc_mean, median=p50, p10=p10, p90=p90, std=mc_std
    )

    upside_to_p50_pct = ((p50 / dcf_value) - 1) * 100 if dcf_value else 0.0
    upside_to_p90_pct = ((p90 / dcf_value) - 1) * 100 if dcf_value else 0.0
    downside_to_p10_pct = ((p10 / dcf_value) - 1) * 100 if dcf_value else 0.0
    probability_undervalued = float(mc_data["probability_undervalued"] or 0.0)

    cv = (float(mc_data["std_dev"]) / abs(float(mc_data["mean"]))) if float(mc_data["mean"]) != 0 else 1.0
    deviation = (
        abs(dcf_value - multiples_value) / max(abs(dcf_value), abs(multiples_value))
        if max(abs(dcf_value), abs(multiples_value)) > 0
        else 1.0
    )

    wacc_down = max(terminal_growth + 0.001, wacc - 0.01)
    wacc_up = wacc + 0.01
    dcf_down = compute_dcf_value(fcf_values=fcf_values, wacc=wacc_down, terminal_growth_rate=terminal_growth)[
        "enterprise_value"
    ]
    dcf_up = compute_dcf_value(fcf_values=fcf_values, wacc=wacc_up, terminal_growth_rate=terminal_growth)[
        "enterprise_value"
    ]
    sensitivity_spread = abs(dcf_down - dcf_up) / abs(dcf_value) if dcf_value else 1.0

    dispersion_score = _to_score_from_ratio(cv, cap=0.60)
    alignment_score = _to_score_from_ratio(deviation, cap=0.60)
    probability_score = float(np.clip(probability_undervalued, 0.0, 1.0))
    wacc_sensitivity_score = _to_score_from_ratio(sensitivity_spread, cap=1.0)

    final_score = (
        (0.30 * dispersion_score)
        + (0.25 * alignment_score)
        + (0.25 * probability_score)
        + (0.20 * wacc_sensitivity_score)
    )

    confidence_data = {
        "confidence_score": float(np.clip(final_score, 0, 1)),
        "factors": {
            "dispersion_score": float(dispersion_score),
            "alignment_score": float(alignment_score),
            "probability_score": float(probability_score),
            "wacc_sensitivity_score": float(wacc_sensitivity_score),
        },
        "inputs": {
            "coefficient_of_variation": float(cv),
            "dcf_multiples_deviation": float(deviation),
            "probability_undervalued": float(probability_undervalued),
            "wacc_sensitivity_spread": float(sensitivity_spread),
            "wacc_beta": float(wacc_inputs["beta"]),
        },
    }

    summary = {
        "ticker": full_ticker,
        "dcf_value": dcf_value,
        "multiples_value": multiples_value,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "probability_undervalued": probability_undervalued,
        "confidence_score": float(confidence_data["confidence_score"]),
        "upside_to_p50_pct": float(upside_to_p50_pct),
        "upside_to_p90_pct": float(upside_to_p90_pct),
        "downside_to_p10_pct": float(downside_to_p10_pct),
        # --- Hybrid IV (new keys, backward-compatible) ---
        "intrinsic_value": float(iv),
        "mean": float(mc_mean),
        "median": float(p50),
        "scenario_value": float(v_scenario),
        "risk_alpha": float(risk_alpha),
    }

    risk_data = [
        {"metric": "Base DCF Value", "value": dcf_value},
        {"metric": "P10 (Bear Case)", "value": p10},
        {"metric": "P50 (Median)", "value": p50},
        {"metric": "P90 (Bull Case)", "value": p90},
        {"metric": "Upside to P90 (%)", "value": upside_to_p90_pct},
        {"metric": "Downside to P10 (%)", "value": downside_to_p10_pct},
        {"metric": "Probability Undervalued", "value": probability_undervalued},
        {"metric": "Probability Overvalued", "value": float(1 - probability_undervalued)},
    ]

    statements = _build_statements(
        income_df=income_df,
        balance_df=balance_df,
        cashflow_df=cashflow_df,
    )

    ai_summary = _build_ai_summary(
        summary=summary,
        dcf_data=dcf_data,
        mc_data=mc_data,
        multiples_data=multiples_data,
        confidence_data=confidence_data,
    )

    return {
        "ticker": full_ticker,
        "generated_at": datetime.now(timezone.utc),
        "dcf": dcf_data,
        "monte_carlo": mc_data,
        "multiples": multiples_data,
        "fcf_forecast": forecast,
        "risk_summary": risk_data,
        "confidence": confidence_data,
        "summary": summary,
        "ai_summary": ai_summary,
        "statements": statements,
    }


def get_full_report(ticker: str, market: str = "NSE") -> dict:
    full_ticker = _normalize_ticker(ticker=ticker, market=market)
    cache_key = f"{market.upper().strip()}::{full_ticker}"
    now = time.time()

    cached = _REPORT_CACHE.get(cache_key)
    if cached and (now - cached[0]) < REPORT_TTL_SECONDS:
        return copy.deepcopy(cached[1])

    report = _build_report(ticker=ticker, market=market)
    _REPORT_CACHE[cache_key] = (now, report)
    return copy.deepcopy(report)


def get_company_statements(ticker: str, market: str = "NSE") -> dict:
    report = get_full_report(ticker=ticker, market=market)
    return {
        "ticker": report["ticker"],
        "generated_at": report["generated_at"],
        "statements": report["statements"],
    }
