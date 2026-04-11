from __future__ import annotations

import numpy as np

from backend.utils.loader import load_csv


def _build_histogram(values: np.ndarray, bins: int = 40) -> list[dict]:
    counts, edges = np.histogram(values, bins=bins)
    histogram = []
    for i, count in enumerate(counts):
        histogram.append(
            {
                "bin_start": float(edges[i]),
                "bin_end": float(edges[i + 1]),
                "count": int(count),
            }
        )
    return histogram


def get_monte_carlo_results(base_value: float | None = None) -> dict:
    df = load_csv("data/monte_carlo_valuation.csv", required_columns=["valuation"])
    valuations = df["valuation"].to_numpy(dtype=float)

    iterations = int(len(valuations))
    if iterations < 1000:
        raise ValueError(
            f"Monte Carlo sample size is too small ({iterations}). Expected at least 1000 simulations."
        )

    mean_value = float(np.mean(valuations))
    std_value = float(np.std(valuations, ddof=1))
    p10 = float(np.quantile(valuations, 0.10))
    p50 = float(np.quantile(valuations, 0.50))
    p90 = float(np.quantile(valuations, 0.90))

    probability_undervalued = None
    if base_value is not None:
        probability_undervalued = float(np.mean(valuations > base_value))

    return {
        "iterations": iterations,
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
