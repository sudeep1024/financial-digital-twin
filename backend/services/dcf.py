from __future__ import annotations

import numpy as np

from backend.utils.loader import load_csv


def compute_dcf_value(fcf_values: np.ndarray, wacc: float, terminal_growth_rate: float) -> dict:
    years = np.arange(1, len(fcf_values) + 1)
    discounted_fcf = fcf_values / np.power(1 + wacc, years)
    pv_forecast = float(np.sum(discounted_fcf))

    terminal_fcf = float(fcf_values[-1])
    terminal_value = (terminal_fcf * (1 + terminal_growth_rate)) / (wacc - terminal_growth_rate)
    pv_terminal_value = terminal_value / ((1 + wacc) ** len(fcf_values))

    enterprise_value = pv_forecast + pv_terminal_value
    return {
        "pv_forecast": pv_forecast,
        "terminal_value": float(terminal_value),
        "pv_terminal_value": float(pv_terminal_value),
        "enterprise_value": float(enterprise_value),
    }


def get_dcf() -> dict:
    dcf_df = load_csv(
        "data/dcf_hdfc.csv",
        required_columns=["ticker", "enterprise_value", "wacc", "terminal_growth_rate"],
    )
    wacc_df = load_csv("data/wacc_hdfc.csv", required_columns=["wacc"])
    forecast_df = load_csv("data/final_forecast_fcf.csv", required_columns=["FCF_Mean"])

    row = dcf_df.iloc[0]
    ticker = str(row["ticker"])
    wacc = float(wacc_df.iloc[0]["wacc"])
    terminal_growth_rate = float(row["terminal_growth_rate"])
    fcf_values = forecast_df["FCF_Mean"].to_numpy(dtype=float)

    if len(fcf_values) == 0:
        raise ValueError("No forecasted FCF values available for DCF calculation.")
    if wacc <= terminal_growth_rate:
        raise ValueError(
            f"Invalid DCF assumptions: WACC ({wacc:.4f}) must be greater than terminal growth ({terminal_growth_rate:.4f})."
        )

    calculated = compute_dcf_value(fcf_values=fcf_values, wacc=wacc, terminal_growth_rate=terminal_growth_rate)
    stored_ev = float(row["enterprise_value"])
    delta_pct = (
        abs(calculated["enterprise_value"] - stored_ev) / abs(stored_ev)
        if stored_ev != 0
        else 0.0
    )

    return {
        "ticker": ticker,
        "enterprise_value": calculated["enterprise_value"],
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth_rate,
        "pv_forecast": calculated["pv_forecast"],
        "terminal_value": calculated["terminal_value"],
        "pv_terminal_value": calculated["pv_terminal_value"],
        "stored_enterprise_value": stored_ev,
        "reconciliation_error_pct": float(delta_pct),
    }
