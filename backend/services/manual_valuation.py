from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from backend.schemas.responses import ManualValuationRequest

try:
    from backend.services.dynamic_valuation import compute_intrinsic_value as _compute_iv
except Exception:  # pragma: no cover – fallback if yfinance absent
    def _compute_iv(mean, median, p10, p90, std):  # type: ignore[misc]
        v_scenario = 0.20 * p10 + 0.60 * median + 0.20 * p90
        denom = mean + std
        alpha = 0.0 if denom == 0 else float(1 - (std / denom))
        risk_adjustment = alpha * mean
        iv = 0.30 * median + 0.30 * mean + 0.30 * v_scenario + 0.10 * risk_adjustment
        return float(iv), float(alpha), float(v_scenario)


CRORE_DIVISOR = 1e7
MANUAL_UNIT = "INR Crores"

SECTOR_DEFAULTS = {
    "financials": {
        "growth": 0.07,
        "beta": 0.95,
        "market_volatility": 0.16,
        "macro_score": 0.55,
        "cost_of_debt": 0.08,
        "ev_ebitda": 8.0,
        "pe": 13.0,
        "pb": 2.8,
    },
    "technology": {
        "growth": 0.11,
        "beta": 1.20,
        "market_volatility": 0.26,
        "macro_score": 0.50,
        "cost_of_debt": 0.07,
        "ev_ebitda": 16.0,
        "pe": 24.0,
        "pb": 5.0,
    },
    "industrial": {
        "growth": 0.07,
        "beta": 1.05,
        "market_volatility": 0.20,
        "macro_score": 0.50,
        "cost_of_debt": 0.08,
        "ev_ebitda": 10.0,
        "pe": 16.0,
        "pb": 2.2,
    },
    "default": {
        "growth": 0.08,
        "beta": 1.00,
        "market_volatility": 0.20,
        "macro_score": 0.50,
        "cost_of_debt": 0.08,
        "ev_ebitda": 11.0,
        "pe": 18.0,
        "pb": 2.5,
    },
}

COUNTRY_RF = {
    "india": 0.07,
    "united states": 0.045,
    "usa": 0.045,
    "us": 0.045,
    "uk": 0.04,
    "united kingdom": 0.04,
}

SECTOR_BENCHMARKS = {
    "financials": {"pb": (2.0, 4.0), "pe": (10.0, 18.0)},
    "technology": {"ev_ebitda": (10.0, 20.0), "pe": (18.0, 35.0)},
    "industrial": {"ev_ebitda": (6.0, 12.0), "pe": (12.0, 22.0)},
    "default": {"ev_ebitda": (8.0, 14.0), "pe": (14.0, 24.0)},
}

MONETARY_FIELDS = (
    "revenue",
    "ebitda",
    "net_income",
    "debt",
    "equity",
    "cash",
    "operating_cf",
    "capex",
)


def _normalize_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def _normalize_score_inverse(value: float, cutoff: float) -> float:
    if cutoff <= 0:
        return 0.0
    return float(np.clip(1 - (value / cutoff), 0.0, 1.0))


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if abs(denominator) > 1e-9 else 0.0


def _to_crores(value: float) -> float:
    if abs(value) > 1e9:
        return float(value / CRORE_DIVISOR)
    return float(value)


def _normalize_manual_inputs(inp: ManualValuationRequest) -> dict:
    raw = {
        "company_name": inp.company_name,
        "sector": inp.sector,
        "country": inp.country,
        "revenue": float(inp.revenue),
        "ebitda": float(inp.ebitda),
        "net_income": float(inp.net_income),
        "debt": float(inp.debt),
        "equity": float(inp.equity),
        "cash": float(inp.cash),
        "operating_cf": float(inp.operating_cf),
        "capex": float(inp.capex),
    }
    conversion_applied = any(abs(raw[field]) > 1e9 for field in MONETARY_FIELDS)
    normalized = dict(raw)
    for field in MONETARY_FIELDS:
        normalized[field] = float(raw[field] / CRORE_DIVISOR) if conversion_applied else _to_crores(raw[field])
    normalized["unit"] = MANUAL_UNIT
    normalized["conversion_applied"] = conversion_applied
    return normalized


def _collect_manual_warnings(data: dict) -> list[str]:
    warnings: list[str] = []
    revenue = float(data["revenue"])
    ebitda = float(data["ebitda"])
    net_income = float(data["net_income"])
    debt = float(data["debt"])
    equity = float(data["equity"])
    operating_cf = float(data["operating_cf"])
    capex = float(data["capex"])

    if revenue <= 0:
        warnings.append("Revenue should be greater than 0 for stable valuation estimates.")
    if ebitda > revenue:
        warnings.append("EBITDA is above Revenue; check operating assumptions.")
    if net_income > revenue:
        warnings.append("Net Income is above Revenue; verify profitability inputs.")
    if debt > (100 * revenue):
        warnings.append("Debt exceeds 100x Revenue; leverage is likely unrealistic.")
    if _safe_div(debt, max(equity, 1.0)) > 3.0:
        warnings.append("Debt/Equity is above 3x; capital structure risk is elevated.")

    ocf_abs = abs(operating_cf)
    if ocf_abs > 0 and capex > (2.5 * ocf_abs):
        warnings.append("CapEx is high versus Operating Cash Flow.")
    if ocf_abs <= 0 and capex > (0.5 * revenue):
        warnings.append("CapEx looks high for the given Revenue/Operating CF profile.")
    if (operating_cf - capex) < 0:
        warnings.append("Free cash flow is negative based on OCF - CapEx.")
    return warnings


def _sector_key(sector: str) -> str:
    s = (sector or "").strip().lower()
    if any(k in s for k in ["bank", "financial", "insurance"]):
        return "financials"
    if any(k in s for k in ["tech", "software", "semiconductor"]):
        return "technology"
    if any(k in s for k in ["industrial", "manufact", "auto", "energy"]):
        return "industrial"
    return "default"


def _defaults_for(sector: str, country: str) -> dict:
    key = _sector_key(sector)
    base = dict(SECTOR_DEFAULTS[key])
    base["risk_free_rate"] = COUNTRY_RF.get((country or "").strip().lower(), 0.055)
    base["market_risk_premium"] = 0.055
    base["tax_rate"] = 0.25
    return base


def _compute_dcf_with_path(fcf_values: np.ndarray, wacc_path: np.ndarray, terminal_growth: float) -> dict:
    wacc_path = np.clip(wacc_path.astype(float), terminal_growth + 0.005, 0.50)
    discount_factors = np.cumprod(1 + wacc_path)
    pv_forecast = float(np.sum(fcf_values / discount_factors))

    terminal_wacc = float(max(wacc_path[-1], terminal_growth + 0.005))
    terminal_fcf = float(max(fcf_values[-1], 1.0))
    terminal_value = float((terminal_fcf * (1 + terminal_growth)) / (terminal_wacc - terminal_growth))
    pv_terminal_value = float(terminal_value / discount_factors[-1])
    enterprise_value = float(pv_forecast + pv_terminal_value)
    return {
        "pv_forecast": pv_forecast,
        "terminal_value": terminal_value,
        "pv_terminal_value": pv_terminal_value,
        "enterprise_value": enterprise_value,
    }


def _build_dynamic_wacc(base_wacc_input: float, volatility: float, macro_score: float, leverage_change: float, years: list[str]):
    alpha = 0.35
    beta_macro = 0.55
    gamma = 0.40

    base_equation_wacc = base_wacc_input * (
        1 + alpha * volatility + beta_macro * macro_score + gamma * leverage_change
    )
    base_equation_wacc = float(np.clip(base_equation_wacc, 0.045, 0.25))

    scenario_defs = [
        {"scenario": "bull", "weight": 0.20, "vol_adj": -0.03, "macro_adj": -0.12, "lev_adj": -0.02},
        {"scenario": "base", "weight": 0.60, "vol_adj": 0.0, "macro_adj": 0.0, "lev_adj": 0.0},
        {"scenario": "bear", "weight": 0.20, "vol_adj": 0.05, "macro_adj": 0.12, "lev_adj": 0.02},
    ]

    horizon = max(1, len(years))
    weighted_path = np.zeros(horizon, dtype=float)
    scenarios: list[dict] = []
    for sc in scenario_defs:
        vol_s = float(np.clip(volatility + sc["vol_adj"], 0.05, 0.9))
        macro_s = float(np.clip(macro_score + sc["macro_adj"], 0.0, 1.5))
        lev_s = leverage_change + sc["lev_adj"]
        initial_wacc = base_wacc_input * (1 + alpha * vol_s + beta_macro * macro_s + gamma * lev_s)
        initial_wacc = float(np.clip(initial_wacc, 0.045, 0.30))

        path = []
        denom = max(horizon - 1, 1)
        for t in range(horizon):
            decay = 1 - (t / denom)
            reversion = (base_equation_wacc - initial_wacc) * (t / denom) * 0.40
            wacc_t = float(np.clip(initial_wacc + reversion + 0.005 * decay * (1 if sc["scenario"] == "bear" else -1 if sc["scenario"] == "bull" else 0), 0.04, 0.30))
            path.append(wacc_t)

        weighted_path += sc["weight"] * np.array(path, dtype=float)
        scenarios.append(
            {
                "scenario": sc["scenario"],
                "weight": sc["weight"],
                "initial_wacc": initial_wacc,
                "path": path,
            }
        )

    time_wacc = [{"year": str(years[i]), "wacc": float(weighted_path[i])} for i in range(horizon)]
    return {
        "base_wacc": float(weighted_path[0]),
        "formula": "WACC_t = base_wacc * (1 + alpha*volatility + beta_macro*macro_score + gamma*leverage_change)",
        "parameters": {"alpha": alpha, "beta_macro": beta_macro, "gamma": gamma},
        "inputs": {
            "base_wacc_input": float(base_wacc_input),
            "volatility": float(volatility),
            "macro_score": float(macro_score),
            "leverage_change": float(leverage_change),
        },
        "decomposition": {
            "multiplicative_factor": float(1 + alpha * volatility + beta_macro * macro_score + gamma * leverage_change),
            "volatility_contribution": float(alpha * volatility),
            "macro_contribution": float(beta_macro * macro_score),
            "leverage_contribution": float(gamma * leverage_change),
            "base_equation_wacc": float(base_equation_wacc),
        },
        "beta": 1.0,
        "market_volatility": float(volatility),
        "macro_score": float(macro_score),
        "leverage_ratio": float(max(leverage_change, 0.0)),
        "scenarios": scenarios,
        "time_varying_wacc": time_wacc,
    }


def _forecast_fcf(
    base_fcf: float,
    base_growth: float,
    volatility: float,
    ebitda_margin: float,
    net_margin: float,
    sector_key: str,
    years: int = 5,
) -> list[dict]:
    sector_terminal_growth = {
        "financials": 0.055,
        "technology": 0.070,
        "industrial": 0.050,
        "default": 0.052,
    }
    target_growth = sector_terminal_growth.get(sector_key, 0.052)
    margin_support = float(np.clip((0.60 * ebitda_margin + 0.40 * net_margin) - 0.12, -0.04, 0.05))
    start_growth = float(np.clip(base_growth + margin_support, 0.01, 0.20))

    current_year = datetime.now(timezone.utc).year
    rows = []
    running_fcf = float(max(base_fcf, 1.0))

    for i in range(1, years + 1):
        mean_reversion = target_growth + (start_growth - target_growth) * np.exp(-0.55 * (i - 1))
        cycle_adj = 0.004 * np.cos(i)
        growth_t = float(np.clip(mean_reversion + cycle_adj, 0.005, 0.22))

        running_fcf = float(max(running_fcf * (1 + growth_t), 1.0))
        spread = float(np.clip(0.10 + (0.02 * i) + (0.25 * volatility), 0.12, 0.45))

        rows.append(
            {
                "year": str(current_year + i),
                "fcf_mean": float(running_fcf),
                "fcf_upper": float(running_fcf * (1 + spread)),
                "fcf_lower": float(max(running_fcf * (1 - spread), 1.0)),
            }
        )
    return rows


def _derive_manual_drivers(data: dict, default_growth: float, default_volatility: float, sector_key: str) -> dict:
    revenue = float(data["revenue"])
    ebitda = float(data["ebitda"])
    net_income = float(data["net_income"])
    operating_cf = float(data["operating_cf"])
    capex = float(data["capex"])

    ebitda_margin = float(np.clip(_safe_div(ebitda, revenue), -0.5, 1.0))
    net_margin = float(np.clip(_safe_div(net_income, revenue), -0.5, 0.8))
    cf_margin = float(np.clip(_safe_div(operating_cf, revenue), -0.5, 0.9))
    capex_intensity = float(np.clip(_safe_div(capex, revenue), 0.0, 0.7))

    direct_fcf = float(operating_cf - capex)
    profitability_fcf = float(revenue * np.clip((0.35 * ebitda_margin) + (0.65 * net_margin), 0.01, 0.30))
    fcf0 = float(max((0.65 * direct_fcf) + (0.35 * profitability_fcf), 1.0))

    sector_growth_floor = {
        "financials": 0.05,
        "technology": 0.07,
        "industrial": 0.045,
        "default": 0.05,
    }
    profitability_score = (0.55 * ebitda_margin) + (0.45 * net_margin)
    growth_adjustment = float(np.clip((profitability_score - 0.12) * 0.30, -0.05, 0.07))
    growth = float(np.clip(default_growth + growth_adjustment, sector_growth_floor.get(sector_key, 0.05), 0.20))

    volatility_adjustment = float(np.clip(((0.18 - ebitda_margin) * 0.65) + (capex_intensity * 0.45), -0.08, 0.20))
    volatility = float(np.clip(default_volatility * (1 + volatility_adjustment), 0.08, 0.42))

    return {
        "fcf0": fcf0,
        "direct_fcf": direct_fcf,
        "profitability_fcf": profitability_fcf,
        "growth": growth,
        "volatility": volatility,
        "ebitda_margin": ebitda_margin,
        "net_margin": net_margin,
        "cf_margin": cf_margin,
        "capex_intensity": capex_intensity,
    }


def _run_mc(forecast: list[dict], dynamic_wacc: dict, terminal_growth: float, base_value: float) -> dict:
    rng = np.random.default_rng(7)
    iterations = 1000
    means = np.array([row["fcf_mean"] for row in forecast], dtype=float)
    uppers = np.array([row["fcf_upper"] for row in forecast], dtype=float)
    lowers = np.array([row["fcf_lower"] for row in forecast], dtype=float)
    stds = np.maximum((uppers - lowers) / 3.29, np.maximum(np.abs(means) * 0.04, 1.0))
    horizon = len(means)

    fcf_samples = rng.normal(means[None, :], stds[None, :], size=(iterations, horizon))
    fcf_samples = np.clip(fcf_samples, 1.0, None)

    probs = np.array([s["weight"] for s in dynamic_wacc["scenarios"]], dtype=float)
    probs = probs / probs.sum()
    paths = np.array([np.array(s["path"], dtype=float) for s in dynamic_wacc["scenarios"]], dtype=float)
    idx = rng.choice(len(dynamic_wacc["scenarios"]), size=iterations, p=probs)
    wacc_paths = paths[idx] + rng.normal(0, 0.0045, size=(iterations, horizon))
    wacc_paths = np.clip(wacc_paths, terminal_growth + 0.005, 0.40)

    discount = np.cumprod(1 + wacc_paths, axis=1)
    pv_fcf = np.sum(fcf_samples / discount, axis=1)
    terminal_fcf = fcf_samples[:, -1]
    terminal_wacc = wacc_paths[:, -1]
    terminal_val = (terminal_fcf * (1 + terminal_growth)) / (terminal_wacc - terminal_growth)
    pv_terminal = terminal_val / discount[:, -1]
    vals = (pv_fcf + pv_terminal)
    vals = vals[np.isfinite(vals)]

    if len(vals) < 500:
        raise ValueError("Monte Carlo sample quality is insufficient for manual mode.")

    counts, edges = np.histogram(vals, bins=40)
    histogram = [{"bin_start": float(edges[i]), "bin_end": float(edges[i + 1]), "count": int(counts[i])} for i in range(len(counts))]
    return {
        "iterations": int(len(vals)),
        "mean": float(np.mean(vals)),
        "std_dev": float(np.std(vals, ddof=1)),
        "p10": float(np.quantile(vals, 0.10)),
        "p50": float(np.quantile(vals, 0.50)),
        "p90": float(np.quantile(vals, 0.90)),
        "min": float(np.min(vals)),
        "max": float(np.max(vals)),
        "probability_undervalued": float(np.mean(vals > base_value)),
        "histogram": histogram,
    }


def _confidence(
    dcf_value: float,
    multiples_value: float,
    mc: dict,
    fcf: np.ndarray,
    wacc_path: np.ndarray,
    terminal_growth: float,
    input_quality: float,
    realism_score: float,
) -> dict:
    cv = float(mc["std_dev"] / abs(mc["mean"])) if mc["mean"] else 1.0
    valuation_gap = (
        abs(dcf_value - multiples_value) / max(abs(dcf_value), abs(multiples_value))
        if max(abs(dcf_value), abs(multiples_value)) > 0
        else 1.0
    )
    prob = float(mc.get("probability_undervalued") or 0.0)

    down = _compute_dcf_with_path(fcf, np.clip(wacc_path - 0.01, terminal_growth + 0.001, 0.4), terminal_growth)["enterprise_value"]
    up = _compute_dcf_with_path(fcf, np.clip(wacc_path + 0.01, terminal_growth + 0.001, 0.4), terminal_growth)["enterprise_value"]
    base = _compute_dcf_with_path(fcf, wacc_path, terminal_growth)["enterprise_value"]
    sens = abs(down - up) / abs(base) if base else 1.0

    variance_score = _normalize_score_inverse(cv, 0.65)
    valuation_gap_score = _normalize_score_inverse(valuation_gap, 0.65)
    undervaluation_score = _normalize_score(prob, 0.15, 0.85)
    wacc_sensitivity_score = _normalize_score_inverse(sens, 1.0)
    data_quality_score = float(np.clip(input_quality, 0.0, 1.0))
    realism_quality_score = float(np.clip(realism_score, 0.0, 1.0))

    score = (
        0.20 * variance_score
        + 0.20 * valuation_gap_score
        + 0.18 * undervaluation_score
        + 0.16 * wacc_sensitivity_score
        + 0.16 * data_quality_score
        + 0.10 * realism_quality_score
    )
    return {
        "confidence_score": float(np.clip(score, 0.0, 1.0)),
        "components": {
            "variance_score": float(variance_score),
            "valuation_gap_score": float(valuation_gap_score),
            "undervaluation_score": float(undervaluation_score),
            "wacc_sensitivity_score": float(wacc_sensitivity_score),
            "data_quality_score": float(data_quality_score),
            "realism_score": float(realism_quality_score),
        },
        "explanation": [
            f"Variance score from Monte Carlo dispersion: {variance_score:.2f}.",
            f"Valuation-gap score from DCF vs multiples: {valuation_gap_score:.2f}.",
            f"Undervaluation score from probability spread: {undervaluation_score:.2f}.",
            f"WACC sensitivity score from +/-100 bps path stress: {wacc_sensitivity_score:.2f}.",
            f"Input quality score: {data_quality_score:.2f}; realism score: {realism_quality_score:.2f}.",
        ],
        "raw_inputs": {
            "variance_of_simulation": float(cv),
            "valuation_gap": float(valuation_gap),
            "probability_undervalued": float(prob),
            "wacc_sensitivity": float(sens),
            "data_quality_score": float(data_quality_score),
            "realism_score": float(realism_quality_score),
        },
    }


def _input_quality(data: dict, drivers: dict) -> dict:
    revenue = float(data["revenue"])
    ebitda = float(data["ebitda"])
    net_income = float(data["net_income"])
    debt = float(data["debt"])
    equity = float(data["equity"])
    operating_cf = float(data["operating_cf"])
    capex = float(data["capex"])

    checks = []
    checks.append(1.0 if revenue > 0 else 0.0)
    checks.append(1.0 if ebitda <= revenue else 0.0)
    checks.append(1.0 if net_income <= revenue else 0.0)
    checks.append(1.0 if debt <= (100 * revenue) else 0.0)

    ocf_abs = abs(operating_cf)
    capex_ok = (ocf_abs > 0 and capex <= (2.5 * ocf_abs)) or (ocf_abs <= 0 and capex <= (0.5 * revenue))
    checks.append(1.0 if capex_ok else 0.0)

    ebitda_margin = float(drivers["ebitda_margin"])
    checks.append(1.0 if -0.1 <= ebitda_margin <= 0.6 else 0.5)

    leverage = float(_safe_div(debt, debt + equity))
    checks.append(1.0 if leverage <= 0.85 else 0.6)

    score = float(np.clip(np.mean(checks), 0.0, 1.0))
    return {
        "score": score,
        "components": {
            "field_consistency": float(np.mean(checks[:5])),
            "margin_plausibility": float(checks[5]),
            "leverage_plausibility": float(checks[6]),
            "source_type": 0.85,
        },
    }


def _realism_score(data: dict, drivers: dict) -> dict:
    ebitda_margin = float(drivers["ebitda_margin"])
    net_margin = float(drivers["net_margin"])
    debt_to_equity = float(_safe_div(data["debt"], data["equity"]))
    fcf_conversion = float(_safe_div(drivers["direct_fcf"], max(data["ebitda"], 1.0)))
    capex_to_ocf = float(_safe_div(data["capex"], max(abs(data["operating_cf"]), 1.0)))
    consistency_gap = abs(drivers["direct_fcf"] - drivers["profitability_fcf"]) / max(abs(data["revenue"]), 1.0)

    ebitda_score = 1.0 if 0.0 <= ebitda_margin <= 0.45 else (0.65 if -0.05 <= ebitda_margin <= 0.60 else 0.30)
    net_score = 1.0 if -0.05 <= net_margin <= 0.25 else (0.65 if -0.15 <= net_margin <= 0.35 else 0.30)
    leverage_score = 1.0 if debt_to_equity <= 2.5 else (0.65 if debt_to_equity <= 4.0 else 0.25)
    fcf_score = 1.0 if 0.0 <= fcf_conversion <= 1.10 else (0.65 if -0.20 <= fcf_conversion <= 1.40 else 0.30)
    capex_score = 1.0 if capex_to_ocf <= 0.80 else (0.65 if capex_to_ocf <= 1.50 else 0.25)
    consistency_score = float(np.clip(1 - (consistency_gap / 0.35), 0.0, 1.0))

    score = float(
        np.clip(
            np.mean([ebitda_score, net_score, leverage_score, fcf_score, capex_score, consistency_score]),
            0.0,
            1.0,
        )
    )
    return {
        "score": score,
        "components": {
            "ebitda_margin_realism": float(ebitda_score),
            "net_margin_realism": float(net_score),
            "capital_structure_realism": float(leverage_score),
            "fcf_conversion_realism": float(fcf_score),
            "capex_discipline_realism": float(capex_score),
            "cross_metric_consistency": float(consistency_score),
        },
    }


def _compute_multiples(data: dict, defaults: dict, sector_key: str, dcf_value: float) -> tuple[dict, float, str]:
    benchmarks = SECTOR_BENCHMARKS.get(sector_key, SECTOR_BENCHMARKS["default"])
    ev_multiple = float(np.clip(defaults["ev_ebitda"], *benchmarks.get("ev_ebitda", (8.0, 14.0))))
    pe_multiple = float(np.clip(defaults["pe"], *benchmarks.get("pe", (12.0, 24.0))))
    pb_multiple = float(np.clip(defaults["pb"], *SECTOR_BENCHMARKS["financials"]["pb"]))

    implied_enterprise = float(ev_multiple * max(float(data["ebitda"]), 1.0))
    implied_equity_ev = float(implied_enterprise + float(data["cash"]) - float(data["debt"]))
    implied_pe = float(pe_multiple * float(data["net_income"])) if float(data["net_income"]) > 0 else None
    implied_pb = float(pb_multiple * float(data["equity"]))

    if sector_key == "financials":
        selected_anchor = "price_to_book"
        multiples_raw = float(implied_pb)
    else:
        selected_anchor = "blended_ev_ebitda_pe" if implied_pe is not None else "ev_ebitda"
        multiples_raw = float(0.65 * implied_equity_ev + 0.35 * implied_pe) if implied_pe is not None else float(implied_equity_ev)

    if dcf_value > 0:
        multiples_value = float(np.clip(multiples_raw, 0.35 * dcf_value, 2.50 * dcf_value))
    else:
        multiples_value = float(max(multiples_raw, 1.0))

    multiples = {
        "target_ticker": "",
        "peer_count": 1,
        "median_ev_ebitda": float(ev_multiple),
        "implied_enterprise_value_ev_ebitda": float(implied_enterprise),
        "implied_value_ev_ebitda": float(implied_equity_ev),
        "median_price_to_book": float(pb_multiple),
        "implied_value_price_to_book": float(implied_pb),
        "selected_anchor": selected_anchor,
        "median_pe": float(pe_multiple),
        "implied_value_pe": (float(implied_pe) if implied_pe is not None else None),
    }
    return multiples, multiples_value, selected_anchor


def _reliability_label(confidence_score: float) -> str:
    if confidence_score >= 0.75:
        return "High confidence"
    if confidence_score >= 0.50:
        return "Moderate reliability"
    return "Low confidence"


def _build_ai_summary(
    signal: str,
    summary: dict,
    confidence: dict,
    risk_level: str,
    dynamic_wacc: dict,
    multiples: dict,
) -> dict:
    dcf_value = float(summary["dcf_value"])
    multiples_value = float(summary["multiples_value"])
    gap_pct = float(((multiples_value / dcf_value) - 1) * 100 if dcf_value else 0.0)

    relation_text = (
        f"DCF value is {dcf_value:,.2f} Cr and multiples-based value is {multiples_value:,.2f} Cr "
        f"({gap_pct:+.1f}% gap)."
    )
    risk_text = (
        f"Monte Carlo range is P10 {summary['p10']:,.2f} Cr, P50 {summary['p50']:,.2f} Cr, "
        f"P90 {summary['p90']:,.2f} Cr, indicating {risk_level} projection risk."
    )
    confidence_text = (
        f"Confidence score is {confidence['confidence_score']:.2f} ({_reliability_label(float(confidence['confidence_score']))}), "
        "combining valuation consistency, dispersion, WACC sensitivity, and input realism."
    )
    driver_text = (
        f"Key drivers: forecast growth {summary['forecast_growth_rate_pct']:.2f}%, EBITDA margin {summary['ebitda_margin'] * 100:.2f}%, "
        f"net margin {summary['net_margin'] * 100:.2f}%, dynamic WACC base {summary['dynamic_wacc_base'] * 100:.2f}%, "
        f"and leverage (Debt/Equity) {summary['debt_to_equity']:.2f}x."
    )
    model_text = (
        f"Dynamic WACC state equation used with volatility {dynamic_wacc['market_volatility']:.3f}; "
        f"Monte Carlo simulation with {summary['monte_carlo_iterations']} runs."
    )
    triangulation_text = (
        "Final valuation combines DCF, Monte Carlo median, and multiples with adaptive weights "
        f"(DCF {summary['triangulation_weights']['dcf']:.2f}, "
        f"MC {summary['triangulation_weights']['mc_p50']:.2f}, "
        f"Multiples {summary['triangulation_weights']['multiples']:.2f})."
    )
    multiples_text = (
        "Multiples valuation derived using peer median EV/EBITDA of "
        f"{float(multiples.get('median_ev_ebitda', 0.0)):.2f} and P/B of "
        f"{float(multiples.get('median_price_to_book', 0.0)):.2f}."
    )

    if signal == "BUY":
        insight = "Valuation supports accumulation with favorable upside versus modeled risk."
    elif signal == "SELL":
        insight = "Downside risk dominates the expected payoff; de-risking is prudent."
    else:
        insight = "Valuation is close to fair value with a balanced risk-reward profile."

    return {
        "signal": signal,
        "upside_percent": float(summary["upside_to_p50_pct"]),
        "explanation": [relation_text, risk_text, confidence_text, driver_text, model_text, triangulation_text, multiples_text],
        "investment_insight": insight,
    }


def _tri_weights(sector: str, vol: float, conf: float) -> dict[str, float]:
    key = _sector_key(sector)
    if key == "financials":
        base = {"dcf": 0.34, "mc_p50": 0.18, "multiples": 0.48}
    elif key == "technology":
        base = {"dcf": 0.52, "mc_p50": 0.30, "multiples": 0.18}
    else:
        base = {"dcf": 0.45, "mc_p50": 0.25, "multiples": 0.30}

    vol_norm = _normalize_score(vol, 0.10, 0.45)
    dcf = base["dcf"] + (conf - 0.5) * 0.20 - vol_norm * 0.08
    mc = base["mc_p50"] + vol_norm * 0.10 + (0.5 - conf) * 0.05
    mult = base["multiples"] + (0.55 - conf) * 0.05 - vol_norm * 0.02
    arr = np.clip(np.array([dcf, mc, mult], dtype=float), 0.10, None)
    arr = arr / arr.sum()
    return {"dcf": float(arr[0]), "mc_p50": float(arr[1]), "multiples": float(arr[2])}


def build_manual_report(inp: ManualValuationRequest) -> dict:
    normalized = _normalize_manual_inputs(inp)
    validation_warnings = _collect_manual_warnings(normalized)

    defaults = _defaults_for(normalized["sector"], normalized["country"])
    sector_key = _sector_key(normalized["sector"])
    ticker = f"{normalized['company_name'].upper().replace(' ', '_')}_MANUAL"

    drivers = _derive_manual_drivers(
        data=normalized,
        default_growth=float(defaults["growth"]),
        default_volatility=float(defaults["market_volatility"]),
        sector_key=sector_key,
    )
    forecast = _forecast_fcf(
        base_fcf=float(drivers["fcf0"]),
        base_growth=float(drivers["growth"]),
        volatility=float(drivers["volatility"]),
        ebitda_margin=float(drivers["ebitda_margin"]),
        net_margin=float(drivers["net_margin"]),
        sector_key=sector_key,
        years=5,
    )
    years = [row["year"] for row in forecast]

    debt = float(normalized["debt"])
    equity = float(normalized["equity"])
    total_capital = max(debt + equity, 1e-9)
    debt_weight = debt / total_capital
    equity_weight = equity / total_capital

    cost_of_equity = defaults["risk_free_rate"] + defaults["beta"] * defaults["market_risk_premium"]
    cost_of_debt = defaults["cost_of_debt"]
    tax_rate = defaults["tax_rate"]
    base_wacc_input = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))

    leverage_change = debt_weight - 0.35
    dynamic_wacc = _build_dynamic_wacc(
        base_wacc_input=float(base_wacc_input),
        volatility=float(drivers["volatility"]),
        macro_score=float(defaults["macro_score"]),
        leverage_change=float(leverage_change),
        years=years,
    )
    terminal_growth = 0.04 if (normalized["country"] or "").strip().lower() in {"india"} else 0.025
    fcf_values = np.array([row["fcf_mean"] for row in forecast], dtype=float)
    wacc_path = np.array([row["wacc"] for row in dynamic_wacc["time_varying_wacc"]], dtype=float)

    dcf_calc = _compute_dcf_with_path(fcf_values, wacc_path, terminal_growth)
    dcf_value = float(dcf_calc["enterprise_value"])

    mc = _run_mc(forecast, dynamic_wacc, terminal_growth, dcf_value)

    # --- Hybrid Intrinsic Value ---
    mc_mean = float(mc["mean"])
    mc_std = float(mc["std_dev"])
    iv, risk_alpha, v_scenario = _compute_iv(
        mean=mc_mean,
        median=float(mc["p50"]),
        p10=float(mc["p10"]),
        p90=float(mc["p90"]),
        std=mc_std,
    )

    multiples, multiples_value, selected_anchor = _compute_multiples(
        data=normalized,
        defaults=defaults,
        sector_key=sector_key,
        dcf_value=dcf_value,
    )

    quality = _input_quality(normalized, drivers)
    realism = _realism_score(normalized, drivers)
    confidence = _confidence(
        dcf_value=dcf_value,
        multiples_value=multiples_value,
        mc=mc,
        fcf=fcf_values,
        wacc_path=wacc_path,
        terminal_growth=terminal_growth,
        input_quality=quality["score"],
        realism_score=realism["score"],
    )

    weights = _tri_weights(normalized["sector"], dynamic_wacc["market_volatility"], confidence["confidence_score"])
    blended_value = (
        weights["dcf"] * dcf_value
        + weights["mc_p50"] * float(mc["p50"])
        + weights["multiples"] * multiples_value
    )

    summary = {
        "ticker": ticker,
        "sector": normalized["sector"],
        "dcf_value": dcf_value,
        "multiples_value": multiples_value,
        "blended_value": float(blended_value),
        "p10": float(mc["p10"]),
        "p50": float(mc["p50"]),
        "p90": float(mc["p90"]),
        "probability_undervalued": float(mc["probability_undervalued"]),
        "confidence_score": float(confidence["confidence_score"]),
        "upside_to_p50_pct": float(((float(mc["p50"]) / dcf_value) - 1) * 100 if dcf_value else 0.0),
        "upside_to_p90_pct": float(((float(mc["p90"]) / dcf_value) - 1) * 100 if dcf_value else 0.0),
        "downside_to_p10_pct": float(((float(mc["p10"]) / dcf_value) - 1) * 100 if dcf_value else 0.0),
        "triangulation_weights": weights,
        "dynamic_wacc_base": float(dynamic_wacc["base_wacc"]),
        "unit": MANUAL_UNIT,
        "input_quality_score": float(quality["score"]),
        "realism_score": float(realism["score"]),
        "forecast_growth_rate_pct": float(drivers["growth"] * 100.0),
        "ebitda_margin": float(drivers["ebitda_margin"]),
        "net_margin": float(drivers["net_margin"]),
        "debt_to_equity": float(_safe_div(normalized["debt"], normalized["equity"])),
        "monte_carlo_iterations": int(mc["iterations"]),
        # --- Hybrid IV (new keys, backward-compatible) ---
        "intrinsic_value": float(iv),
        "mean": float(mc_mean),
        "median": float(mc["p50"]),
        "scenario_value": float(v_scenario),
        "risk_alpha": float(risk_alpha),
    }

    signal = "HOLD"
    if confidence["confidence_score"] >= 0.67 and summary["upside_to_p50_pct"] > 6:
        signal = "BUY"
    elif confidence["confidence_score"] <= 0.35 and summary["upside_to_p50_pct"] < 0:
        signal = "SELL"

    range_width = float(_safe_div(summary["p90"] - summary["p10"], max(summary["p50"], 1.0)))
    risk_level = "high" if range_width > 1.0 else "moderate" if range_width > 0.55 else "low"
    ai_summary = _build_ai_summary(
        signal=signal,
        summary=summary,
        confidence=confidence,
        risk_level=risk_level,
        dynamic_wacc=dynamic_wacc,
        multiples=multiples,
    )

    current_year = str(datetime.now(timezone.utc).year)
    statements = {
        "income_statement": [
            {"metric": "Revenue", "values": {current_year: float(normalized["revenue"])}},
            {"metric": "EBITDA", "values": {current_year: float(normalized["ebitda"])}},
            {"metric": "Net Income", "values": {current_year: float(normalized["net_income"])}},
        ],
        "balance_sheet": [
            {"metric": "Debt", "values": {current_year: float(normalized["debt"])}},
            {"metric": "Equity", "values": {current_year: float(normalized["equity"])}},
            {"metric": "Cash", "values": {current_year: float(normalized["cash"])}},
        ],
        "cash_flow": [
            {"metric": "Operating Cash Flow", "values": {current_year: float(normalized["operating_cf"])}},
            {"metric": "Capital Expenditure", "values": {current_year: float(normalized["capex"])}},
            {"metric": "Free Cash Flow", "values": {current_year: float(drivers["fcf0"])}},
        ],
    }

    risk_summary = [
        {"metric": "Base DCF Value", "value": dcf_value},
        {"metric": "P10 (Bear Case)", "value": float(mc["p10"])},
        {"metric": "P50 (Median)", "value": float(mc["p50"])},
        {"metric": "P90 (Bull Case)", "value": float(mc["p90"])},
        {"metric": "Blended Triangulated Value", "value": float(blended_value)},
        {"metric": "Upside to P90 (%)", "value": float(summary["upside_to_p90_pct"])},
        {"metric": "Downside to P10 (%)", "value": float(summary["downside_to_p10_pct"])},
        {"metric": "Probability Undervalued", "value": float(mc["probability_undervalued"])},
        {"metric": "Input Quality Score", "value": float(quality["score"])},
    ]

    manual_input_summary = {
        "unit": MANUAL_UNIT,
        "revenue": float(normalized["revenue"]),
        "ebitda_margin": float(drivers["ebitda_margin"]),
        "net_margin": float(drivers["net_margin"]),
        "free_cash_flow": float(drivers["fcf0"]),
        "debt_to_equity": float(_safe_div(normalized["debt"], normalized["equity"])),
        "input_quality_score": float(quality["score"]),
        "realism_score": float(realism["score"]),
        "conversion_applied": bool(normalized["conversion_applied"]),
    }
    confidence_components = confidence.get("components", {})
    variance_ratio = float(_safe_div(mc["std_dev"], max(abs(mc["mean"]), 1e-9)))
    dcf_multiples_deviation_pct = float(_safe_div(abs(dcf_value - multiples_value), max(abs(dcf_value), 1e-9)) * 100.0)

    model_inputs = {
        "dcf_inputs": {
            "forecast_growth_rate_pct": float(drivers["growth"] * 100.0),
            "terminal_growth_rate_pct": float(terminal_growth * 100.0),
            "forecast_horizon_years": int(len(forecast)),
        },
        "wacc_breakdown": {
            "risk_free_rate": float(defaults["risk_free_rate"]),
            "beta": float(defaults["beta"]),
            "market_risk_premium": float(defaults["market_risk_premium"]),
            "cost_of_equity": float(cost_of_equity),
            "cost_of_debt": float(cost_of_debt),
            "tax_rate": float(tax_rate),
            "equity_weight": float(equity_weight),
            "debt_weight": float(debt_weight),
            "final_wacc": float(dynamic_wacc["base_wacc"]),
        },
        "monte_carlo_inputs": {
            "simulations": int(mc["iterations"]),
            "growth_volatility": float(drivers["volatility"]),
            "wacc_volatility": float(np.std(wacc_path, ddof=1) if len(wacc_path) > 1 else 0.0),
            "distribution_assumptions": "FCF normal distribution and scenario-weighted dynamic WACC perturbations",
        },
    }

    validation_diagnostics = {
        "dcf_multiples_deviation_pct": dcf_multiples_deviation_pct,
        "monte_carlo_variance_ratio": variance_ratio,
        "probability_undervalued": float(mc["probability_undervalued"]),
        "confidence_breakdown": {
            "variance_score": float(confidence_components.get("variance_score", 0.0)),
            "valuation_gap_score": float(confidence_components.get("valuation_gap_score", 0.0)),
            "undervaluation_score": float(confidence_components.get("undervaluation_score", 0.0)),
            "wacc_sensitivity_score": float(confidence_components.get("wacc_sensitivity_score", 0.0)),
            "data_quality_score": float(confidence_components.get("data_quality_score", 0.0)),
        },
        "reliability_label": _reliability_label(float(confidence["confidence_score"])),
        "warnings": validation_warnings,
    }

    comparison_metrics = {
        "model_value": float(blended_value),
        "market_value": None,
        "error_pct": None,
        "label": "No Market Benchmark",
    }

    performance_metrics = {
        "absolute_error_pct": None,
        "stability_variance_ratio": variance_ratio,
        "wacc_sensitivity_pct": float(confidence.get("raw_inputs", {}).get("wacc_sensitivity", 0.0) * 100.0),
        "scenario_spread": float(summary["p90"] - summary["p10"]),
    }

    multiples["target_ticker"] = ticker

    report = {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc),
        "mode": "manual",
        "dcf": {
            "ticker": ticker,
            "enterprise_value": dcf_value,
            "wacc": float(dynamic_wacc["base_wacc"]),
            "terminal_growth_rate": float(terminal_growth),
            "pv_forecast": float(dcf_calc["pv_forecast"]),
            "terminal_value": float(dcf_calc["terminal_value"]),
            "pv_terminal_value": float(dcf_calc["pv_terminal_value"]),
            "stored_enterprise_value": dcf_value,
            "reconciliation_error_pct": 0.0,
        },
        "dynamic_wacc": dynamic_wacc,
        "monte_carlo": mc,
        "multiples": multiples,
        "triangulation": {
            "sector": normalized["sector"],
            "anchor_used": selected_anchor,
            "weights": weights,
            "blended_value": float(blended_value),
        },
        "data_quality": {
            "score": float((0.60 * quality["score"]) + (0.40 * realism["score"])),
            "components": {
                **quality["components"],
                **realism["components"],
            },
        },
        "fcf_forecast": forecast,
        "risk_summary": risk_summary,
        "confidence": confidence,
        "summary": summary,
        "ai_summary": ai_summary,
        "statements": statements,
        "manual_input_summary": manual_input_summary,
        "model_inputs": model_inputs,
        "validation_diagnostics": validation_diagnostics,
        "comparison_metrics": comparison_metrics,
        "performance_metrics": performance_metrics,
    }

    report["digital_twin"] = {
        "fcf_model": {"method": "manual_input_profitability_adjusted", "forecast": forecast},
        "wacc_model": {
            "formula": dynamic_wacc["formula"],
            "parameters": dynamic_wacc["parameters"],
            "time_varying_wacc": dynamic_wacc["time_varying_wacc"],
        },
        "risk_engine": {
            "iterations": mc["iterations"],
            "distribution": {"p10": mc["p10"], "p50": mc["p50"], "p90": mc["p90"]},
        },
        "valuation_engine": {
            "dcf_value": dcf_value,
            "multiples_value": multiples_value,
            "blended_value": float(blended_value),
            "confidence_score": float(confidence["confidence_score"]),
            "realism_score": float(realism["score"]),
        },
    }
    return report
