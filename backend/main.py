from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.schemas.responses import (
    CompanyStatementsResponse,
    ConfidenceScoreResponse,
    DCFResponse,
    DigitalTwinResponse,
    FCFForecastItem,
    FullReportResponse,
    ManualValuationRequest,
    MonteCarloResponse,
    MultiplesResponse,
    NewsResponse,
    PipelineBuildResponse,
    RiskSummaryItem,
    TickerUniverseResponse,
    ValuationSummaryResponse,
)
from backend.services import internal_universe, manual_valuation, news, pipeline_builder, research_engine, ticker_universe
from backend.utils.loader import DataLoadError


logger = logging.getLogger("financial_digital_twin")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="Financial Digital Twin Engine",
    description="AI-driven probabilistic company valuation engine",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DataLoadError)
async def data_load_error_handler(_, exc: DataLoadError):
    logger.error("Data artifact error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(_, exc: ValueError):
    logger.error("Validation error: %s", exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(ModuleNotFoundError)
async def module_not_found_handler(_, exc: ModuleNotFoundError):
    logger.error("Missing dependency: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": f"Missing dependency '{exc.name}'. Install required package and retry."},
    )


def _demo_service():
    try:
        from backend.services import dynamic_valuation
    except ModuleNotFoundError as exc:
        if exc.name == "yfinance":
            raise ValueError(
                "Demo mode unavailable: 'yfinance' is not installed. "
                "Use Internal mode or install yfinance."
            ) from exc
        raise

    return dynamic_valuation


def _resolve_report_or_404(ticker: str, market: str, mode: str) -> dict:
    mode = mode.lower().strip()
    try:
        if mode == "internal":
            return research_engine.build_internal_full_report(ticker=ticker, market=market)
        if mode == "demo":
            try:
                report = _demo_service().get_full_report(ticker=ticker, market=market)
                report["mode"] = "demo"
            except Exception as exc:
                logger.warning("Demo mode failed for %s/%s: %s", ticker, market, exc)
                try:
                    fallback_report = research_engine.build_internal_full_report(ticker=ticker, market=market)
                    fallback_report["mode"] = "internal"
                    fallback_report.setdefault(
                        "ai_summary",
                        {
                            "signal": "HOLD",
                            "upside_percent": 0.0,
                            "explanation": [],
                            "investment_insight": "",
                        },
                    )
                    fallback_report["ai_summary"].setdefault(
                        "explanation",
                        [],
                    )
                    fallback_report["ai_summary"]["explanation"].append(
                        "Demo mode live fetch failed; report served from internal reproducible pipeline."
                    )
                    return fallback_report
                except Exception as fallback_exc:
                    raise ValueError(
                        "Demo mode unavailable: live data fetch failed and no internal fallback exists "
                        f"for ticker '{ticker}' in market '{market}'. Root cause: {exc}"
                    ) from fallback_exc

            dcf_wacc = float(report.get("dcf", {}).get("wacc", 0.10))
            base_path = [dcf_wacc] * max(1, len(report.get("fcf_forecast", [])))
            report.setdefault(
                "dynamic_wacc",
                {
                    "base_wacc": dcf_wacc,
                    "formula": "WACC_t = base_wacc * (1 + alpha*volatility + beta_macro*macro_score + gamma*leverage_change)",
                    "parameters": {"alpha": 0.0, "beta_macro": 0.0, "gamma": 0.0},
                    "inputs": {
                        "base_wacc_input": dcf_wacc,
                        "volatility": 0.18,
                        "macro_score": 0.5,
                        "leverage_change": 0.0,
                    },
                    "decomposition": {
                        "multiplicative_factor": 1.0,
                        "volatility_contribution": 0.0,
                        "macro_contribution": 0.0,
                        "leverage_contribution": 0.0,
                        "base_equation_wacc": dcf_wacc,
                    },
                    "beta": float(report.get("confidence", {}).get("inputs", {}).get("wacc_beta", 1.0)),
                    "market_volatility": 0.18,
                    "macro_score": 0.5,
                    "leverage_ratio": 0.4,
                    "scenarios": [
                        {"scenario": "base", "weight": 1.0, "initial_wacc": dcf_wacc, "path": base_path},
                    ],
                    "time_varying_wacc": [
                        {"year": str(item.get("year", i + 1))[:4], "wacc": dcf_wacc}
                        for i, item in enumerate(report.get("fcf_forecast", []))
                    ],
                },
            )

            summary = report.get("summary", {})
            blended = float(summary.get("p50", summary.get("dcf_value", 0.0)))
            report.setdefault(
                "triangulation",
                {
                    "sector": "General",
                    "anchor_used": "ev_ebitda",
                    "weights": {"dcf": 0.4, "mc_p50": 0.3, "multiples": 0.3},
                    "blended_value": blended,
                },
            )
            report.setdefault(
                "data_quality",
                {
                    "score": 0.65,
                    "components": {
                        "live_data_completeness": 0.70,
                        "model_input_stability": 0.60,
                    },
                },
            )
            confidence = report.get("confidence", {})
            if isinstance(confidence, dict):
                raw_components = confidence.get("factors", {})
                report["confidence"] = {
                    "confidence_score": float(confidence.get("confidence_score", 0.5)),
                    "components": {
                        "variance_score": float(raw_components.get("dispersion_score", 0.5)),
                        "valuation_gap_score": float(raw_components.get("alignment_score", 0.5)),
                        "undervaluation_score": float(raw_components.get("probability_score", 0.5)),
                        "wacc_sensitivity_score": float(raw_components.get("wacc_sensitivity_score", 0.5)),
                        "data_quality_score": 0.65,
                    },
                    "explanation": [
                        "Demo-mode confidence mapped from legacy scoring components.",
                        "Use internal mode for full reproducible confidence decomposition.",
                    ],
                    "raw_inputs": confidence.get("inputs", {}),
                }

            if isinstance(summary, dict):
                summary.setdefault("sector", "General")
                summary.setdefault("blended_value", blended)
                summary.setdefault("triangulation_weights", {"dcf": 0.4, "mc_p50": 0.3, "multiples": 0.3})

            return report
        raise ValueError("Invalid mode. Supported modes: internal, demo.")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/")
def home():
    return {"status": "ok", "service": "Financial Digital Twin Engine"}


@app.get("/forecast/fcf", response_model=list[FCFForecastItem])
def fcf_forecast(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    return _resolve_report_or_404(ticker=ticker, market=market, mode=mode)["fcf_forecast"]


@app.get("/valuation/dcf", response_model=DCFResponse)
def dcf_valuation(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    return _resolve_report_or_404(ticker=ticker, market=market, mode=mode)["dcf"]


@app.get("/risk/montecarlo", response_model=MonteCarloResponse)
def monte_carlo_risk(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    return _resolve_report_or_404(ticker=ticker, market=market, mode=mode)["monte_carlo"]


@app.get("/valuation/multiples", response_model=MultiplesResponse)
def multiples_valuation(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    return _resolve_report_or_404(ticker=ticker, market=market, mode=mode)["multiples"]


@app.get("/risk/summary", response_model=list[RiskSummaryItem])
def risk_summary(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    return _resolve_report_or_404(ticker=ticker, market=market, mode=mode)["risk_summary"]


@app.get("/valuation/confidence", response_model=ConfidenceScoreResponse)
def valuation_confidence(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    return _resolve_report_or_404(ticker=ticker, market=market, mode=mode)["confidence"]


@app.get("/summary", response_model=ValuationSummaryResponse)
def valuation_summary(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    return _resolve_report_or_404(ticker=ticker, market=market, mode=mode)["summary"]


@app.get("/valuation/full-report", response_model=FullReportResponse)
def full_valuation_report(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    report = _resolve_report_or_404(ticker=ticker, market=market, mode=mode)
    logger.info("Generated %s valuation report for ticker=%s", mode, report["ticker"])
    return report


@app.post("/valuation/manual", response_model=FullReportResponse)
def manual_valuation_report(payload: ManualValuationRequest):
    report = manual_valuation.build_manual_report(payload)
    logger.info("Generated manual valuation report for company=%s", payload.company_name)
    return report


@app.get("/valuation/digital-twin", response_model=DigitalTwinResponse)
def valuation_digital_twin(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    if mode.lower().strip() == "internal":
        return research_engine.build_internal_digital_twin(ticker=ticker, market=market)
    report = _resolve_report_or_404(ticker=ticker, market=market, mode=mode)
    return research_engine.build_digital_twin_from_report(report)


@app.get("/news", response_model=NewsResponse)
def get_nlp_news(ticker: str = Query(default="HDFCBANK.NS", min_length=1)):
    normalized_ticker = ticker.upper().strip()
    return news.get_news_feed(ticker=normalized_ticker)


@app.get("/company/statements", response_model=CompanyStatementsResponse)
def company_statements(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
    mode: str = Query(default="internal", min_length=4),
):
    try:
        if mode.lower().strip() == "internal":
            return research_engine.build_internal_statements(ticker=ticker, market=market)
        if mode.lower().strip() == "demo":
            return _demo_service().get_company_statements(ticker=ticker, market=market)
        raise ValueError("Invalid mode. Supported modes: internal, demo.")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/market/tickers", response_model=TickerUniverseResponse)
def market_tickers(
    market: str = Query(default="NSE", min_length=2),
    query: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=20000),
    mode: str = Query(default="internal", min_length=4),
):
    try:
        if mode.lower().strip() == "internal":
            return internal_universe.search_tickers(market=market, query=query, limit=limit)
        if mode.lower().strip() == "demo":
            return ticker_universe.search_tickers(market=market, query=query, limit=limit)
        raise ValueError("Invalid mode. Supported modes: internal, demo.")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Unable to load ticker universe: {exc}") from exc


@app.post("/pipeline/build", response_model=PipelineBuildResponse)
def build_pipeline(
    ticker: str = Query(default="HDFCBANK", min_length=1),
    market: str = Query(default="NSE", min_length=2),
):
    try:
        return pipeline_builder.build_company_pipeline(ticker=ticker, market=market)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
