# Research + Patent Layer Notes

## Financial Digital Twin Framing
The system models a company valuation stack as a **digital twin** of valuation mechanics:
- operating cash generation trajectory (FCF state)
- discount-rate dynamics (WACC state)
- relative market pricing anchors (multiples state)
- stochastic risk envelope (Monte Carlo state)
- confidence/meta-quality state.

This transforms valuation from static spreadsheet logic to a stateful, scenario-responsive computational engine.

## Probabilistic Valuation Engine
The valuation core is distribution-first:
- deterministic DCF baseline
- stochastic perturbation of FCF path and WACC
- distribution outputs (P10/P50/P90, histogram, undervaluation probability).

This supports decision-making under uncertainty rather than single-point valuation dependence.

## Dynamic Discounting Model (WACC)
WACC is modeled as a dynamic functional:

`WACC_t = f(beta_t, market_volatility_t, macro_scenario_t, capital_structure_t)`

Inputs:
- `beta_t`: rolling regression beta from local price history
- `market_volatility_t`: annualized volatility from index returns
- `macro_scenario_t`: weighted scenario table (`bull/base/bear`)
- `capital_structure_t`: leverage-sensitive adjustment.

Outputs:
- base WACC
- scenario WACC curve used in simulation.

## Confidence-Based Decision Layer
Confidence is explicitly modeled as:

`C = f(simulation_variance, dcf_multiples_alignment, probability_undervalued, wacc_sensitivity, data_quality)`

Properties:
- normalized to `[0, 1]`
- decomposed into interpretable factors
- exposed in API for explainability and auditability.

## Sector-Aware Triangulation
Valuation blending is not fixed:
- Financials prioritize P/B-based anchoring.
- Non-financial sectors can bias toward DCF or EV/EBITDA anchors.

Blended value:

`V_blended = w_dcf * V_dcf + w_mc * V_p50 + w_mult * V_anchor(sector)`

This supports adaptive valuation policy rather than one-size-fits-all weighting.

## Reproducibility and Publication Alignment
Internal mode enforces:
- local artifact inputs
- deterministic simulation setup
- no external market API dependency for valuation core.

Demo mode is isolated and explicitly non-reproducible by design.
