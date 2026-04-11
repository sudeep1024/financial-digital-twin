# Validation Report: AI-Driven Financial Digital Twin (IEEE/Patent Upgrade)

## 1. Scope and Objective
This validation pass corrected and upgraded the valuation system to:
- default to **reproducible internal CSV artifacts** (`mode=internal`)
- isolate external live data into explicit **demo mode** (`mode=demo`)
- strengthen the core probabilistic valuation and confidence logic for research-grade use.

## 2. Stage-by-Stage Pipeline Validation

### Stage 1: FCF preprocessing
Status: **Validated and enforced**
- Verified `FCF = Operating Cash Flow + Capital Expenditure` consistency through local fundamentals pipeline.
- Added robust fallback path when forecast artifacts are incomplete by rebuilding forecasts from internal `fcf_clean.csv`.
- No hardcoded valuation constants are used for final FCF forecast values in internal mode.

### Stage 2: ML-based FCF forecasting
Status: **Validated and hardened**
- Primary source remains `data/final_forecast_fcf.csv` (pipeline artifact).
- Added deterministic fallback ML forecaster (linear regression on historical FCF with uncertainty bands) when artifact quality is insufficient.
- Forecast confidence contribution is captured in data-quality scoring.

### Stage 3: Beta estimation (regression-based)
Status: **Upgraded**
- Implemented regression beta estimation from internal price CSVs:
  - stock returns vs market returns via OLS (`LinearRegression`)
  - rolling beta (`beta_t`) and annualized market volatility.
- Beta is now dynamic and data-driven, not static/hardcoded.

### Stage 4: Dynamic WACC
Status: **Upgraded (research-grade structure)**
- Added dynamic WACC with:
  - `beta_t` (regression-derived)
  - market volatility adjustment
  - macro scenario factors (`data/macro_factors.csv`)
  - capital structure dynamics (leverage-based adjustment from local peer file).
- Added scenario outputs (`bull/base/bear`) with normalized weights.

### Stage 5: DCF valuation
Status: **Validated and integrated with dynamic WACC**
- DCF now uses dynamic base WACC from internal model.
- Preserves reconciliation against stored DCF artifact.
- Enforces WACC vs terminal growth constraints in simulation path.

### Stage 6: Monte Carlo (>= 10,000)
Status: **Validated and upgraded**
- Internal Monte Carlo now runs **10,000** iterations minimum.
- Simulates both:
  - FCF uncertainty (from forecast upper/lower bands)
  - WACC uncertainty (scenario-mixture sampling).
- Produces full valuation distribution and histogram.

### Stage 7: Risk summary (P10/P50/P90)
Status: **Validated**
- Uses Monte Carlo output directly.
- Added blended valuation metric to risk summary.

### Stage 8: Multiples valuation (P/B + EV/EBITDA)
Status: **Fixed and upgraded**
- Added explicit P/B multiple path from `peer_group_hdfc.csv`.
- Retained EV/EBITDA path from `peer_ev_ebitda.csv`.
- Added sector anchor selection (`price_to_book` for Financials, otherwise EV/EBITDA).

## 3. Critical Reproducibility Fix

### Problem identified
Production path had drifted to live external dependencies (`yfinance`, live symbol APIs), which is not suitable for deterministic research workflows.

### Fix implemented
- Introduced strict **mode separation**:
  - `mode=internal` (default): reproducible local CSV pipeline only.
  - `mode=demo`: external/live behavior kept for demonstration only.
- Internal mode now has no runtime dependency on external financial APIs for valuation inputs.

## 4. Core Innovation Upgrades

### 4.1 Dynamic discounting model (WACC)
- Implemented:
  - time-varying beta
  - volatility-driven risk premium adjustment
  - macro scenario spread inputs
  - leverage-sensitive capital-structure adjustment.

### 4.2 Probabilistic valuation framework
- Fully distribution-based valuation:
  - DCF point estimate
  - Monte Carlo distribution (P10/P50/P90, histogram, undervaluation probability).

### 4.3 Confidence score (patent-aligned)
Implemented:
`confidence_score = f(variance, dcf_vs_multiples_deviation, probability_undervalued, wacc_sensitivity, data_quality_score)`
- normalized to `[0,1]`
- exposed in API with detailed factors and raw inputs.

### 4.4 Sector-aware triangulation
- Added weighted blending of:
  - DCF
  - Monte Carlo P50
  - sector-appropriate multiples anchor.
- Financials now prioritize P/B-weighted triangulation.

## 5. Backend API Compliance

All required endpoints are present and validated:
- `/forecast/fcf`
- `/valuation/dcf`
- `/valuation/multiples`
- `/risk/montecarlo`
- `/summary`
- `/valuation/confidence`
- `/valuation/full-report`

Added/retained supporting endpoints:
- `/market/tickers`
- `/company/statements`
- `/news`

All endpoints support structured JSON with Pydantic response models and centralized exception handling.

## 6. Data Integrity Findings

- Removed default dependence on external APIs for valuation inputs in production path.
- Internal mode outputs are generated from local pipeline artifacts and deterministic simulation configuration.
- Traceable file set includes:
  - `data/final_forecast_fcf.csv`
  - `data/wacc_hdfc.csv`
  - `data/dcf_hdfc.csv`
  - `data/peer_ev_ebitda.csv`
  - `data/peer_group_hdfc.csv`
  - `data/fundamentals/*.csv`
  - `data/prices/*.csv`
  - `data/macro_factors.csv`
  - `data/ticker_profiles.csv`

## 7. Frontend Validation

UI now exposes:
- valuation mode selector (`internal` vs `demo`)
- ticker universe loading via selected mode
- AI explanation text
- charts:
  - Monte Carlo histogram
  - FCF forecast
  - valuation comparison (DCF, multiples, blended, P10/P50/P90).

## 8. Residual Constraints

- Current full internal pipeline artifacts are configured for `HDFCBANK.NS`.
- Additional tickers in `ticker_profiles.csv` are listed but flagged as partial until full artifact sets are added.
- This is intentional to preserve strict reproducibility and avoid synthetic fabrication.

## 9. Changed Files (Key)

- Backend:
  - `backend/main.py`
  - `backend/schemas/responses.py`
  - `backend/services/research_engine.py`
  - `backend/services/internal_universe.py`
- Frontend:
  - `frontend/src/App.svelte`
  - `frontend/src/components/ValuationComparisonChart.svelte`
- Data/config:
  - `data/ticker_profiles.csv`
  - `data/macro_factors.csv`

## 10. Validation Outcome

Result: **PASS (with controlled data-coverage boundary)**
- Internal reproducible mode satisfies research-grade architecture requirements.
- Demo mode remains available but cleanly separated.
