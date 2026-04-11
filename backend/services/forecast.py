from __future__ import annotations

from backend.utils.loader import load_csv


def get_fcf_forecast() -> list[dict]:
    df = load_csv(
        "data/final_forecast_fcf.csv",
        required_columns=["Year", "FCF_Mean", "FCF_Upper", "FCF_Lower"],
    ).copy()

    df["Year"] = df["Year"].astype(str)
    df = df.sort_values("Year")

    forecasts = []
    for _, row in df.iterrows():
        forecasts.append(
            {
                "year": row["Year"],
                "fcf_mean": float(row["FCF_Mean"]),
                "fcf_upper": float(row["FCF_Upper"]),
                "fcf_lower": float(row["FCF_Lower"]),
            }
        )
    return forecasts
