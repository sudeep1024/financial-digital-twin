from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.services import research_engine
from backend.services.internal_universe import get_profile
from backend.utils.loader import resolve_data_path


def _write_csv(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


def build_company_pipeline(ticker: str, market: str = "NSE") -> dict:
    profile = get_profile(ticker=ticker, market=market)
    report = research_engine.build_internal_full_report(ticker=ticker, market=market)
    digital_twin = research_engine.build_internal_digital_twin(ticker=ticker, market=market)

    out_dir = resolve_data_path(f"data/company_pipelines/{profile['ticker']}")
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_files: list[str] = []

    fcf_path = out_dir / "final_forecast_fcf.csv"
    _write_csv(
        fcf_path,
        [
            {
                "Year": row["year"],
                "FCF_Mean": row["fcf_mean"],
                "FCF_Upper": row["fcf_upper"],
                "FCF_Lower": row["fcf_lower"],
            }
            for row in report["fcf_forecast"]
        ],
    )
    generated_files.append(str(fcf_path))

    wacc_path = out_dir / "dynamic_wacc_path.csv"
    _write_csv(
        wacc_path,
        [
            {
                "year": row["year"],
                "wacc": row["wacc"],
                "base_wacc": report["dynamic_wacc"]["base_wacc"],
            }
            for row in report["dynamic_wacc"]["time_varying_wacc"]
        ],
    )
    generated_files.append(str(wacc_path))

    dcf_path = out_dir / "dcf_valuation.csv"
    _write_csv(dcf_path, [report["dcf"]])
    generated_files.append(str(dcf_path))

    mc_path = out_dir / "monte_carlo_summary.csv"
    _write_csv(
        mc_path,
        [
            {
                "iterations": report["monte_carlo"]["iterations"],
                "mean": report["monte_carlo"]["mean"],
                "std_dev": report["monte_carlo"]["std_dev"],
                "p10": report["monte_carlo"]["p10"],
                "p50": report["monte_carlo"]["p50"],
                "p90": report["monte_carlo"]["p90"],
                "probability_undervalued": report["monte_carlo"]["probability_undervalued"],
            }
        ],
    )
    generated_files.append(str(mc_path))

    risk_path = out_dir / "risk_summary.csv"
    _write_csv(risk_path, report["risk_summary"])
    generated_files.append(str(risk_path))

    multiples_path = out_dir / "multiples_valuation.csv"
    _write_csv(multiples_path, [report["multiples"]])
    generated_files.append(str(multiples_path))

    confidence_path = out_dir / "confidence_score.csv"
    _write_csv(
        confidence_path,
        [
            {
                "confidence_score": report["confidence"]["confidence_score"],
                **report["confidence"]["components"],
            }
        ],
    )
    generated_files.append(str(confidence_path))

    summary_path = out_dir / "valuation_summary.csv"
    _write_csv(summary_path, [report["summary"]])
    generated_files.append(str(summary_path))

    twin_path = out_dir / "digital_twin.json"
    twin_path.write_text(json.dumps(digital_twin, indent=2, default=str), encoding="utf-8")
    generated_files.append(str(twin_path))

    metadata_path = out_dir / "pipeline_metadata.json"
    metadata = {
        "ticker": profile["ticker"],
        "market": profile["market"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "internal",
        "reproducibility_tag": f"{profile['ticker']}::internal::v1",
        "source_files": [
            "data/final_forecast_fcf.csv",
            "data/wacc_hdfc.csv",
            "data/dcf_hdfc.csv",
            "data/peer_ev_ebitda.csv",
            "data/peer_group_hdfc.csv",
            "data/fundamentals/*.csv",
            "data/prices/*.csv",
            "data/macro_factors.csv",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    generated_files.append(str(metadata_path))

    return {
        "ticker": profile["ticker"],
        "market": profile["market"],
        "output_dir": str(out_dir),
        "generated_files": generated_files,
        "generated_at": datetime.now(timezone.utc),
        "reproducibility_tag": metadata["reproducibility_tag"],
    }

