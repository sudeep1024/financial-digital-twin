# AI-Driven Financial Digital Twin for Probabilistic Valuation

Research-oriented valuation platform with:

- Reproducible internal-data pipeline
- Dynamic WACC modeling
- DCF + Monte Carlo + multiples triangulation
- Confidence scoring and digital-twin style API outputs
- Svelte dashboard for interactive analysis

## Repository Structure

- `backend/` FastAPI services, schemas, valuation engines
- `frontend/` Svelte + Vite dashboard
- `data/` reproducible CSV artifacts and company pipeline outputs
- `notebooks/` research workflow notebooks (data -> valuation)

## Prerequisites

- Python 3.11+ (tested on Python 3.13)
- Node.js 20+

## Backend Setup

```powershell
cd C:\Users\ASUS\OneDrive\Desktop\financial_digital_twin
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Swagger docs: `http://127.0.0.1:8000/docs`

## Frontend Setup

```powershell
cd C:\Users\ASUS\OneDrive\Desktop\financial_digital_twin\frontend
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

Optional API base override:

```powershell
$env:VITE_API_BASE='http://127.0.0.1:8000'
npm run dev
```

## Core API Endpoints

- `GET /`
- `GET /forecast/fcf`
- `GET /valuation/dcf`
- `GET /valuation/multiples`
- `GET /risk/montecarlo`
- `GET /valuation/confidence`
- `GET /summary`
- `GET /valuation/full-report`
- `GET /valuation/digital-twin`
- `POST /valuation/manual`
- `POST /pipeline/build`

## Modes

- `internal`: reproducible CSV-driven valuation (recommended for research/IEEE)
- `demo`: live API-assisted mode; backend now falls back to internal when available if live fetch fails

## Frontend Flows

- Ticker mode: query ticker/market/mode and render valuation dashboard
- Manual mode: submit financial statement inputs and reuse same dashboard/plots

## Notes

- Monte Carlo uses `>= 10,000` iterations in current valuation engines.
- For internal-only reproducible studies, keep mode as `internal`.
