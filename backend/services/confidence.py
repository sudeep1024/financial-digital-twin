from __future__ import annotations

import numpy as np

from backend.services.dcf import compute_dcf_value, get_dcf
from backend.services.monte_carlo import get_monte_carlo_results
from backend.services.multiples import get_multiples
from backend.utils.loader import load_csv


def _to_score_from_ratio(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    normalized = min(max(value, 0.0), cap) / cap
    return float(1 - normalized)


def _wacc_sensitivity_score(wacc: float, terminal_growth_rate: float) -> tuple[float, float]:
    fcf_df = load_csv("data/final_forecast_fcf.csv", required_columns=["FCF_Mean"])
    fcf_values = fcf_df["FCF_Mean"].to_numpy(dtype=float)

    shock = 0.01
    wacc_down = max(terminal_growth_rate + 0.001, wacc - shock)
    wacc_up = wacc + shock

    dcf_down = compute_dcf_value(fcf_values, wacc_down, terminal_growth_rate)["enterprise_value"]
    dcf_up = compute_dcf_value(fcf_values, wacc_up, terminal_growth_rate)["enterprise_value"]
    base = compute_dcf_value(fcf_values, wacc, terminal_growth_rate)["enterprise_value"]

    if base == 0:
        return 0.0, 1.0

    sensitivity_spread = abs(dcf_down - dcf_up) / abs(base)
    score = _to_score_from_ratio(sensitivity_spread, cap=1.0)
    return float(score), float(sensitivity_spread)


def get_confidence_score() -> dict:
    dcf_data = get_dcf()
    dcf_value = float(dcf_data["enterprise_value"])
    wacc = float(dcf_data["wacc"])
    terminal_growth_rate = float(dcf_data["terminal_growth_rate"])

    mc_data = get_monte_carlo_results(base_value=dcf_value)
    mean_val = float(mc_data["mean"])
    std_val = float(mc_data["std_dev"])
    cv = (std_val / abs(mean_val)) if mean_val != 0 else 1.0

    multiples_data = get_multiples(target_ticker=dcf_data["ticker"])
    multiples_value = float(multiples_data["implied_value_ev_ebitda"])

    deviation = (
        abs(dcf_value - multiples_value) / max(abs(dcf_value), abs(multiples_value))
        if max(abs(dcf_value), abs(multiples_value)) > 0
        else 1.0
    )
    probability_undervalued = float(mc_data["probability_undervalued"] or 0.0)

    dispersion_score = _to_score_from_ratio(cv, cap=0.60)
    alignment_score = _to_score_from_ratio(deviation, cap=0.60)
    probability_score = float(np.clip(probability_undervalued, 0.0, 1.0))
    wacc_sensitivity_score, sensitivity_spread = _wacc_sensitivity_score(
        wacc=wacc, terminal_growth_rate=terminal_growth_rate
    )

    final_score = (
        (0.30 * dispersion_score)
        + (0.25 * alignment_score)
        + (0.25 * probability_score)
        + (0.20 * wacc_sensitivity_score)
    )

    return {
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
        },
    }
