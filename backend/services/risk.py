from __future__ import annotations

from backend.services.dcf import get_dcf
from backend.services.monte_carlo import get_monte_carlo_results
from backend.utils.loader import load_csv


def get_risk_summary() -> list[dict]:
    # Ensure required file is present in pipeline artifacts
    load_csv("data/risk_summary_hdfc.csv", required_columns=["metric", "value"])

    dcf_data = get_dcf()
    mc_data = get_monte_carlo_results(base_value=dcf_data["enterprise_value"])

    base_dcf = float(dcf_data["enterprise_value"])
    p10 = float(mc_data["p10"])
    p50 = float(mc_data["p50"])
    p90 = float(mc_data["p90"])
    probability_undervalued = float(mc_data["probability_undervalued"] or 0.0)
    probability_overvalued = float(1 - probability_undervalued)

    upside_to_p90 = ((p90 / base_dcf) - 1) * 100 if base_dcf else 0.0
    downside_to_p10 = ((p10 / base_dcf) - 1) * 100 if base_dcf else 0.0

    return [
        {"metric": "Base DCF Value", "value": base_dcf},
        {"metric": "P10 (Bear Case)", "value": p10},
        {"metric": "P50 (Median)", "value": p50},
        {"metric": "P90 (Bull Case)", "value": p90},
        {"metric": "Upside to P90 (%)", "value": upside_to_p90},
        {"metric": "Downside to P10 (%)", "value": downside_to_p10},
        {"metric": "Probability Undervalued", "value": probability_undervalued},
        {"metric": "Probability Overvalued", "value": probability_overvalued},
    ]
