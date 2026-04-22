from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FCFForecastItem(BaseModel):
    year: str
    fcf_mean: float
    fcf_upper: float
    fcf_lower: float


class DCFResponse(BaseModel):
    ticker: str
    enterprise_value: float
    wacc: float
    terminal_growth_rate: float
    pv_forecast: float
    terminal_value: float
    pv_terminal_value: float
    stored_enterprise_value: float
    reconciliation_error_pct: float


class HistogramBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class MonteCarloResponse(BaseModel):
    iterations: int
    mean: float
    std_dev: float
    p10: float
    p50: float
    p90: float
    min: float
    max: float
    probability_undervalued: Optional[float] = None
    histogram: List[HistogramBin]


class DCFModelInputs(BaseModel):
    forecast_growth_rate_pct: float
    terminal_growth_rate_pct: float
    forecast_horizon_years: int


class WACCBreakdown(BaseModel):
    risk_free_rate: float
    beta: float
    market_risk_premium: float
    cost_of_equity: float
    cost_of_debt: float
    tax_rate: float
    equity_weight: float
    debt_weight: float
    final_wacc: float


class MonteCarloInputs(BaseModel):
    simulations: int
    growth_volatility: float
    wacc_volatility: float
    distribution_assumptions: str


class ModelInputsPanel(BaseModel):
    dcf_inputs: DCFModelInputs
    wacc_breakdown: WACCBreakdown
    monte_carlo_inputs: MonteCarloInputs


class ValidationDiagnostics(BaseModel):
    dcf_multiples_deviation_pct: float
    monte_carlo_variance_ratio: float
    probability_undervalued: float
    confidence_breakdown: Dict[str, float] = Field(default_factory=dict)
    reliability_label: str
    warnings: List[str] = Field(default_factory=list)


class ComparisonMetrics(BaseModel):
    model_value: float
    market_value: Optional[float] = None
    error_pct: Optional[float] = None
    label: str


class PerformanceMetrics(BaseModel):
    absolute_error_pct: Optional[float] = None
    stability_variance_ratio: float
    wacc_sensitivity_pct: float
    scenario_spread: float


class MultiplesResponse(BaseModel):
    target_ticker: str
    peer_count: int
    median_ev_ebitda: float
    implied_enterprise_value_ev_ebitda: float
    implied_value_ev_ebitda: float
    median_price_to_book: Optional[float] = None
    implied_value_price_to_book: Optional[float] = None
    selected_anchor: Optional[str] = None
    median_pe: Optional[float] = None
    implied_value_pe: Optional[float] = None


class RiskSummaryItem(BaseModel):
    metric: str
    value: float


class ConfidenceScoreResponse(BaseModel):
    confidence_score: float = Field(ge=0.0, le=1.0)
    components: Dict[str, float]
    explanation: List[str]
    raw_inputs: Dict[str, float] = Field(default_factory=dict)


class ValuationSummaryResponse(BaseModel):
    ticker: str
    sector: Optional[str] = None
    dcf_value: float
    multiples_value: float
    blended_value: Optional[float] = None
    p10: float
    p50: float
    p90: float
    probability_undervalued: float
    confidence_score: float = Field(ge=0.0, le=1.0)
    upside_to_p50_pct: float
    upside_to_p90_pct: float
    downside_to_p10_pct: float
    triangulation_weights: Dict[str, float] = Field(default_factory=dict)
    unit: Optional[str] = None
    input_quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    realism_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # --- Hybrid Intrinsic Value (new, backward-compatible) ---
    intrinsic_value: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    scenario_value: Optional[float] = None
    risk_alpha: Optional[float] = None


class AISummary(BaseModel):
    signal: str
    upside_percent: float
    explanation: List[str]
    investment_insight: str


class StatementRow(BaseModel):
    metric: str
    values: Dict[str, float]


class CompanyStatements(BaseModel):
    income_statement: List[StatementRow]
    balance_sheet: List[StatementRow]
    cash_flow: List[StatementRow]


class WACCScenarioItem(BaseModel):
    scenario: str
    weight: float
    initial_wacc: float
    path: List[float]


class WACCTimePoint(BaseModel):
    year: str
    wacc: float


class DynamicWACCDetails(BaseModel):
    base_wacc: float
    formula: str
    parameters: Dict[str, float]
    inputs: Dict[str, float]
    decomposition: Dict[str, float]
    beta: float
    market_volatility: float
    macro_score: float
    leverage_ratio: float
    scenarios: List[WACCScenarioItem]
    time_varying_wacc: List[WACCTimePoint]


class TriangulationDetails(BaseModel):
    sector: str
    anchor_used: str
    weights: Dict[str, float]
    blended_value: float


class DataQualityDetails(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    components: Dict[str, float]


class ManualInputSummary(BaseModel):
    unit: str
    revenue: float
    ebitda_margin: float
    net_margin: float
    free_cash_flow: float
    debt_to_equity: float
    input_quality_score: float = Field(ge=0.0, le=1.0)
    realism_score: float = Field(ge=0.0, le=1.0)
    conversion_applied: bool = False


class DigitalTwinModel(BaseModel):
    fcf_model: Dict[str, Any]
    wacc_model: Dict[str, Any]
    risk_engine: Dict[str, Any]
    valuation_engine: Dict[str, Any]


class DigitalTwinResponse(BaseModel):
    ticker: str
    generated_at: datetime
    mode: str
    digital_twin: DigitalTwinModel


class PipelineBuildResponse(BaseModel):
    ticker: str
    market: str
    output_dir: str
    generated_files: List[str]
    generated_at: datetime
    reproducibility_tag: str


class ManualValuationRequest(BaseModel):
    company_name: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    country: str = Field(min_length=1)
    revenue: float = Field(gt=0)
    ebitda: float = Field(gt=0)
    net_income: float
    debt: float = Field(ge=0)
    equity: float = Field(gt=0)
    cash: float = Field(ge=0)
    operating_cf: float
    capex: float = Field(ge=0)


class FullReportResponse(BaseModel):
    ticker: str
    generated_at: datetime
    mode: str = "internal"
    dcf: DCFResponse
    dynamic_wacc: DynamicWACCDetails
    monte_carlo: MonteCarloResponse
    multiples: MultiplesResponse
    triangulation: TriangulationDetails
    data_quality: DataQualityDetails
    fcf_forecast: List[FCFForecastItem]
    risk_summary: List[RiskSummaryItem]
    confidence: ConfidenceScoreResponse
    summary: ValuationSummaryResponse
    ai_summary: AISummary
    statements: CompanyStatements
    manual_input_summary: Optional[ManualInputSummary] = None
    model_inputs: Optional[ModelInputsPanel] = None
    validation_diagnostics: Optional[ValidationDiagnostics] = None
    comparison_metrics: Optional[ComparisonMetrics] = None
    performance_metrics: Optional[PerformanceMetrics] = None


class NewsItem(BaseModel):
    title: str
    link: str
    published_at: str
    source: str
    sentiment: str
    sentiment_score: float


class NewsResponse(BaseModel):
    ticker: str
    generated_at: str
    sentiment_score: float
    company_news: List[NewsItem]
    macro_news: List[NewsItem]


class CompanyStatementsResponse(BaseModel):
    ticker: str
    generated_at: datetime
    statements: CompanyStatements


class TickerListItem(BaseModel):
    symbol: str
    name: str
    market: str
    yahoo_ticker: str


class TickerUniverseResponse(BaseModel):
    market: str
    total: int
    returned: int
    query: str
    tickers: List[TickerListItem]
