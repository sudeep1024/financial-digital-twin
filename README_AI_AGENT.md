# AI-Driven Financial Digital Twin: Valuation Agent Dashboard

This project unifies generative AI design patterns (ChatGPT-style prompting and explanation logic) with elite institutional finance data structures (Bloomberg Terminal / McKinsey).

## 🔹 1. Folder Structure
Your application is currently integrated directly into the active directories:
```text
financial_digital_twin/
├── backend/
│   ├── main.py                <-- Complete FastAPI router (Multi-asset dynamic fallback + NLP + Signals)
│   ├── schemas/               <-- Pydantic validation
│   └── services/              <-- Quant modules (monte_carlo.py, dcf.py, confidence.py)
├── frontend/
│   ├── postcss.config.js      <-- Tailwind V4 processing
│   ├── src/
│   │   ├── app.css            <-- Global 'Apple-glass' frosted UI themes & Aurora animations
│   │   ├── App.svelte         <-- Main split layout (AI Sidebar + Terminal View)
│   │   ├── main.js
│   │   └── components/
│   │       ├── AIAgent.svelte       <-- Left Panel: ChatGPT-style interaction + Dynamic gauges
│   │       ├── Hero.svelte          <-- Top Header Dashboard Title
│   │       ├── KeyMetrics.svelte    <-- 4 Top KPI Cards (DCF, Conviction, Targets, Signals)
│   │       ├── MonteCarloChart.svelte
│   │       ├── NewsFeed.svelte      <-- Live yfinance NLP sentiment news
│   │       ├── RiskSummary.svelte
│   │       └── Triangulation.svelte <-- McKinsey style bottom blended target synthesis
```

## 🔹 2. How to Run Instructions
The servers must be booted in two independent processes (terminals):

**Start the Backend (Quant Engine):**
1. Open terminal and navigate to project root.
2. Activate the virtual environment: `.\venv\Scripts\activate`
3. Export path: `$env:PYTHONPATH="c:/Users/ASUS/OneDrive/Desktop/financial_digital_twin"`
4. Run FastApi: `uvicorn backend.main:app --reload`
*(The backend runs on `http://127.0.0.1:8000`)*

**Start the Frontend (Svelte UI):**
1. Open terminal and navigate to `frontend` folder.
2. Run Vite: `npm run dev`
*(The frontend runs on `http://localhost:5173`)*

## 🔹 3. API Integration Details
The Svelte UI actively queries:
- `GET /valuation/full-report?ticker=...`
  - *Returns*: DCF, Monte Carlo probabilities, Peer Multiples.
  - *Agent Injection*: Returns an `ai_summary` JSON sub-object containing a `signal` (BUY/HOLD/SELL), an `upside_percent`, and an `explanation` array parsed directly by the AI sidebar.
- `GET /news?ticker=...`
  - *Returns*: Scrapes live news headlines using `yfinance` and parses the title using `TextBlob` NLP sentiment mapping (returning `-1` to `1` polarity, converted to Bullish/Neutral/Bearish tags).

## 🔹 4. Interaction Flow
1. **Search**: Enter a company ticker into the left AI Agent panel (e.g. `AAPL`, `TSLA`, `RELIANCE.NS`).
2. **Process**: The system will dynamically simulate a terminal run (showing the glowing `Running Neural Models` spinner).
3. **Response**: The sidebar will update with the ChatGPT-style valuation rationale, and the Bloomberg-style right pane will immediately repopulate with massive data metrics. 
