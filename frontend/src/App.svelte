<script>
  import { Chart, registerables } from 'chart.js';
  Chart.register(...registerables);

  // ── API ────────────────────────────────────────────────────────────────
  const API_BASE =
    import.meta.env.VITE_API_BASE ||
    "https://financial-digital-twin-api.onrender.com";

  const SUGGESTIONS = ["HDFCBANK", "RELIANCE", "TCS", "INFY", "ICICIBANK"];
  const MARKETS     = ["NSE", "BSE", "NASDAQ", "NYSE"];
  const MODES       = [
    { value: "internal",   label: "Internal (Reproducible)" },
    { value: "demo",       label: "Demo (Live APIs)" },
    { value: "simulation", label: "AI Probabilistic Simulation" },
  ];

  // ── Primary state ──────────────────────────────────────────────────────
  let ticker  = "HDFCBANK";
  let market  = "NSE";
  let mode    = "internal";
  let loading = false;
  let error   = "";
  let result  = null;
  let hasRun  = false;

  // ── Compare state ──────────────────────────────────────────────────────
  let tickerB      = "";
  let loadingB     = false;
  let resultB      = null;
  let compareError = "";

  // ── Simulation state ───────────────────────────────────────────────────
  let simStats  = null;  // { mean, median, p5, p95, unit, count }
  let simBins   = [];    // [{ mid, count }] for histogram

  // ── Chart canvas refs ──────────────────────────────────────────────────
  let canvasVal, canvasFcf, canvasMc, canvasCmp, canvasSim;
  let chartVal, chartFcf, chartMc, chartCmp, chartSim;

  // ── Formatters ─────────────────────────────────────────────────────────
  const fmtCr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

  function fmtMoney(val, unit = "") {
    const n = Number(val ?? 0);
    if (!Number.isFinite(n)) return "—";
    const cr = unit === "INR Crores" ? n : n / 1e7;
    return `₹${fmtCr.format(cr)} Cr`;
  }

  function fmtPct(val) {
    const n = Number(val ?? 0);
    return Number.isFinite(n) ? `${n.toFixed(2)}%` : "—";
  }

  function fmtRatio(val) {
    const n = Number(val);
    return Number.isFinite(n) ? n.toFixed(3) : "N/A";
  }

  function signalClass(sig) {
    const v = String(sig ?? "").toUpperCase();
    if (/BUY|UNDERVAL/.test(v)) return "sig-green";
    if (/SELL|OVERVAL/.test(v)) return "sig-red";
    return "sig-yellow";
  }

  function betterVal(a, b) {
    const na = Number(a ?? 0), nb = Number(b ?? 0);
    return na > nb ? "A" : nb > na ? "B" : "same";
  }

  // ── Error parsing ──────────────────────────────────────────────────────
  function parseApiError(body) {
    try {
      const j = JSON.parse(body);
      const raw = j.detail ?? j.message ?? j.error ?? "";
      if (raw) {
        if (/not configured|not found|invalid ticker/i.test(raw))
          return "Ticker not available. Try: HDFCBANK, RELIANCE, TCS";
        return raw;
      }
    } catch (_) {}
    return "Something went wrong. Please try again.";
  }

  // ── API helpers ────────────────────────────────────────────────────────
  async function fetchReport(t, m, md) {
    const url =
      `${API_BASE}/valuation/full-report` +
      `?ticker=${encodeURIComponent(t)}` +
      `&market=${encodeURIComponent(m)}` +
      `&mode=${encodeURIComponent(md)}`;
    console.log("[API] →", url);
    const res = await fetch(url);
    if (!res.ok) throw new Error(parseApiError(await res.text()));
    return res.json();
  }

  // ── Monte Carlo helpers ────────────────────────────────────────────────
  function boxMuller(mean, std) {
    // Box-Muller transform: uniform → normal distribution
    const u1 = Math.max(1e-10, Math.random());
    const u2 = Math.random();
    return mean + std * (Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2));
  }

  function simDCF(baseFCF, growthRate, termGrowth, wacc, horizon) {
    // Discount projected FCFs + Gordon Growth terminal value
    let dcf = 0, fcf = baseFCF;
    const safeWacc   = Math.max(0.02, wacc);
    const safeTerm   = Math.min(termGrowth, safeWacc - 0.005);
    for (let t = 1; t <= horizon; t++) {
      fcf *= (1 + growthRate);
      dcf += fcf / Math.pow(1 + safeWacc, t);
    }
    const tv = (fcf * (1 + safeTerm)) / (safeWacc - safeTerm);
    return dcf + tv / Math.pow(1 + safeWacc, horizon);
  }

  function makeBins(values, numBins = 30) {
    const mn = Math.min(...values), mx = Math.max(...values);
    const step = (mx - mn) / numBins || 1;
    const bins = Array.from({ length: numBins }, (_, i) => ({
      mid: mn + (i + 0.5) * step, count: 0,
    }));
    values.forEach(v => {
      const idx = Math.min(numBins - 1, Math.floor((v - mn) / step));
      bins[idx].count++;
    });
    return bins;
  }

  function runMonteCarlo(baseReport, n = 1000) {
    const dcfIn  = baseReport.model_inputs?.dcf_inputs ?? {};
    const waccIn = baseReport.model_inputs?.wacc_breakdown ?? {};
    const mcIn   = baseReport.model_inputs?.monte_carlo_inputs ?? {};

    const baseGrowth = (dcfIn.forecast_growth_rate_pct ?? 8) / 100;
    const termGrowth = (dcfIn.terminal_growth_rate_pct ?? 3)  / 100;
    const horizon    = dcfIn.forecast_horizon_years ?? 5;
    const baseWacc   = waccIn.final_wacc ?? 0.10;
    const growthVol  = mcIn.growth_volatility ?? 0.04;
    const waccVol    = mcIn.wacc_volatility   ?? 0.015;

    // Base FCF: take the first forecast year's mean value
    const baseFCF = Number(baseReport.fcf_forecast?.[0]?.fcf_mean ?? 1);

    const results = [];
    for (let i = 0; i < n; i++) {
      const g   = boxMuller(baseGrowth, growthVol);
      const w   = boxMuller(baseWacc,   waccVol);
      const val = simDCF(baseFCF, g, termGrowth, w, horizon);
      if (Number.isFinite(val) && val > 0) results.push(val);
    }

    results.sort((a, b) => a - b);
    const pct = (p) => results[Math.max(0, Math.ceil(p / 100 * results.length) - 1)];
    const mean = results.reduce((s, v) => s + v, 0) / results.length;

    return {
      stats: {
        mean, median: pct(50), p5: pct(5), p95: pct(95),
        unit: baseReport.summary?.unit || "INR",
        count: results.length,
      },
      bins: makeBins(results),
    };
  }

  // ── Simulation chart ───────────────────────────────────────────────────
  function buildSimChart(bins, unit) {
    chartSim?.destroy();
    if (!canvasSim || !bins?.length) return;
    const d = getDiv(unit);
    chartSim = new Chart(canvasSim, {
      type: "bar",
      data: {
        labels: bins.map(b =>
          (b.mid / d).toLocaleString("en-IN", { maximumFractionDigits: 1 })
        ),
        datasets: [{
          label: "Simulations",
          data: bins.map(b => b.count),
          backgroundColor: "rgba(139,92,246,0.55)",
          borderColor:     "rgba(139,92,246,0.9)",
          borderWidth: 1,
          borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: TT },
        scales: {
          x: { ticks: { color: TICK, maxTicksLimit: 10 }, grid: { color: GRID } },
          y: {
            ticks: { color: TICK }, grid: { color: GRID },
            title: { display: true, text: "Frequency", color: TICK, font: { size: 11 } },
          },
        },
      },
    });
  }

  async function runValuation() {
    const t = ticker.trim().toUpperCase();
    if (!t) { error = "Please enter a ticker symbol."; return; }
    ticker  = t;
    loading = true;
    error   = "";
    result  = null;
    resultB = null;
    simStats = null;
    simBins  = [];
    hasRun  = true;

    // ── Simulation mode: run client-side Monte Carlo ────────────────────
    if (mode === "simulation") {
      try {
        // Fetch base internal report for parameters
        const base = await fetchReport(t, market, "internal");
        result = base; // show base report data alongside sim
        const { stats, bins } = runMonteCarlo(base, 1000);
        simStats = stats;
        simBins  = bins;
      } catch (err) {
        error = err.name === "TypeError"
          ? "Network error — could not reach the API. Check your connection."
          : err.message;
      } finally {
        loading = false;
      }
      return;
    }

    // ── Normal mode: call API directly ─────────────────────────────────
    try {
      result = await fetchReport(t, market, mode);
    } catch (err) {
      error = err.name === "TypeError"
        ? "Network error — could not reach the API. Check your connection."
        : err.message;
    } finally {
      loading = false;
    }
  }

  async function runComparison() {
    const t = tickerB.trim().toUpperCase();
    if (!t) { compareError = "Enter a second ticker to compare."; return; }
    tickerB      = t;
    loadingB     = true;
    compareError = "";
    resultB      = null;
    try {
      resultB = await fetchReport(t, market, mode);
    } catch (err) {
      compareError = err.message;
    } finally {
      loadingB = false;
    }
  }

  // ── Chart config helpers ───────────────────────────────────────────────
  const GRID = "rgba(255,255,255,0.05)";
  const TICK = "#475569";
  const TT   = { backgroundColor: "#0f1724", borderColor: "#1e2c3e", borderWidth: 1 };

  function getDiv(unit) { return unit === "INR Crores" ? 1 : 1e7; }
  function getAx(unit)  { return unit === "INR Crores" ? "₹ Crores" : "₹ Crores (from INR)"; }

  function xyScales(yTitle) {
    return {
      x: { ticks: { color: TICK }, grid: { color: GRID } },
      y: {
        ticks: {
          color: TICK,
          callback: v => "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 1 }),
        },
        grid: { color: GRID },
        title: yTitle ? { display: true, text: yTitle, color: TICK, font: { size: 11 } } : { display: false },
      },
    };
  }

  // ── Chart builders ─────────────────────────────────────────────────────
  function buildValChart(r) {
    chartVal?.destroy();
    if (!canvasVal || !r?.summary) return;
    const u = r.summary.unit || "INR", d = getDiv(u), a = getAx(u);
    chartVal = new Chart(canvasVal, {
      type: "bar",
      data: {
        labels: ["DCF", "Multiples", "Blended", "P10", "P50", "P90"],
        datasets: [{
          data: [
            r.summary.dcf_value, r.summary.multiples_value, r.summary.blended_value,
            r.summary.p10, r.summary.p50, r.summary.p90,
          ].map(v => Number(v) / d),
          backgroundColor: [
            "rgba(59,130,246,0.78)", "rgba(99,102,241,0.78)", "rgba(20,184,166,0.82)",
            "rgba(239,68,68,0.72)",  "rgba(34,197,94,0.78)",  "rgba(234,179,8,0.78)",
          ],
          borderRadius: 6,
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: TT },
        scales: xyScales(a),
      },
    });
  }

  function buildFcfChart(r) {
    chartFcf?.destroy();
    if (!canvasFcf || !r?.fcf_forecast?.length) return;
    const u = r.summary?.unit || "INR", d = getDiv(u), a = getAx(u);
    chartFcf = new Chart(canvasFcf, {
      type: "line",
      data: {
        labels: r.fcf_forecast.map(p => String(p.year).slice(0, 4)),
        datasets: [
          {
            label: "FCF Mean",
            data: r.fcf_forecast.map(p => Number(p.fcf_mean) / d),
            borderColor: "#22c55e", backgroundColor: "rgba(34,197,94,0.1)",
            fill: true, tension: 0.35, borderWidth: 2,
            pointRadius: 4, pointBackgroundColor: "#22c55e",
          },
          {
            label: "Upper", data: r.fcf_forecast.map(p => Number(p.fcf_upper) / d),
            borderColor: "rgba(34,197,94,0.38)", borderDash: [5, 5],
            tension: 0.3, borderWidth: 1.5, pointRadius: 0,
          },
          {
            label: "Lower", data: r.fcf_forecast.map(p => Number(p.fcf_lower) / d),
            borderColor: "rgba(59,130,246,0.38)", borderDash: [5, 5],
            tension: 0.3, borderWidth: 1.5, pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: TICK, font: { size: 11 }, boxWidth: 12 } }, tooltip: TT },
        scales: xyScales(a),
      },
    });
  }

  function buildMcChart(r) {
    chartMc?.destroy();
    if (!canvasMc || !r?.monte_carlo?.histogram?.length) return;
    const u = r.summary?.unit || "INR", d = getDiv(u);
    chartMc = new Chart(canvasMc, {
      type: "bar",
      data: {
        labels: r.monte_carlo.histogram.map(b => {
          const mid = (Number(b.bin_start) + Number(b.bin_end)) / 2;
          return (mid / d).toLocaleString("en-IN", { maximumFractionDigits: 1 });
        }),
        datasets: [{
          label: "Frequency",
          data: r.monte_carlo.histogram.map(b => b.count),
          backgroundColor: "rgba(20,201,151,0.55)",
          borderColor: "rgba(20,201,151,0.9)",
          borderWidth: 1, borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: TT },
        scales: {
          x: { ticks: { color: TICK, maxTicksLimit: 8 }, grid: { color: GRID } },
          y: {
            ticks: { color: TICK }, grid: { color: GRID },
            title: { display: true, text: "Frequency", color: TICK, font: { size: 11 } },
          },
        },
      },
    });
  }

  function buildCmpChart(rA, rB) {
    chartCmp?.destroy();
    if (!canvasCmp || !rA?.summary || !rB?.summary) return;
    const u = rA.summary.unit || "INR", d = getDiv(u), a = getAx(u);
    const labels = ["DCF", "Multiples", "Blended", "P10", "P50", "P90"];
    const extract = r => [r.summary.dcf_value, r.summary.multiples_value, r.summary.blended_value, r.summary.p10, r.summary.p50, r.summary.p90].map(v => Number(v) / d);
    chartCmp = new Chart(canvasCmp, {
      type: "bar",
      data: {
        labels,
        datasets: [
          { label: rA.ticker || ticker,  data: extract(rA), backgroundColor: "rgba(59,130,246,0.78)", borderRadius: 4 },
          { label: rB.ticker || tickerB, data: extract(rB), backgroundColor: "rgba(234,179,8,0.78)",  borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: TICK, font: { size: 11 }, boxWidth: 12 } }, tooltip: TT },
        scales: xyScales(a),
      },
    });
  }

  // ── Reactive chart triggers (fires when both result + canvas are ready) ─
  $: if (result && canvasVal) buildValChart(result);
  $: if (result && canvasFcf) buildFcfChart(result);
  $: if (result && canvasMc)  buildMcChart(result);
  $: if (result && resultB && canvasCmp) buildCmpChart(result, resultB);
  $: if (simBins.length && canvasSim) buildSimChart(simBins, simStats?.unit || "INR");
</script>

<main>
  <!-- ══ HEADER ══════════════════════════════════════════════════════════ -->
  <header>
    <div class="brand">
      <span class="brand-icon">📈</span>
      <div>
        <h1>Financial Digital Twin</h1>
        <p class="brand-sub">AI-Powered Institutional Valuation Engine</p>
      </div>
    </div>
    <span class="hdr-badge">Bloomberg-grade · Dark Mode</span>
  </header>

  <!-- ══ CONTROLS ════════════════════════════════════════════════════════ -->
  <section class="controls-panel">
    <div class="field field-lg">
      <label for="tk-in">Ticker Symbol</label>
      <input
        id="tk-in"
        type="text"
        value={ticker}
        on:input={e => { ticker = e.target.value.toUpperCase().trimStart(); }}
        on:keydown={e => e.key === "Enter" && runValuation()}
        placeholder="e.g. HDFCBANK"
        autocomplete="off"
        spellcheck="false"
      />
    </div>
    <div class="field">
      <label for="mkt-sel">Market</label>
      <select id="mkt-sel" bind:value={market}>
        {#each MARKETS as m}<option value={m}>{m}</option>{/each}
      </select>
    </div>
    <div class="field">
      <label for="mode-sel">Mode</label>
      <select id="mode-sel" bind:value={mode}>
        {#each MODES as md}<option value={md.value}>{md.label}</option>{/each}
      </select>
    </div>
    <button class="btn-primary" on:click={runValuation} disabled={loading}>
      {#if loading}
        <span class="spin-sm" aria-hidden="true"></span> Analyzing…
      {:else}
        ▶ Run Valuation
      {/if}
    </button>
  </section>

  <!-- ══ CHIPS ═══════════════════════════════════════════════════════════ -->
  <div class="chips-row">
    <span class="chips-lbl">Quick pick:</span>
    {#each SUGGESTIONS as s}
      <button class="chip" on:click={() => { ticker = s; error = ""; }}>{s}</button>
    {/each}
  </div>

  <!-- ══ ERROR ════════════════════════════════════════════════════════════ -->
  {#if error}
    <div class="alert alert-err" role="alert">❌ {error}</div>
  {/if}

  <!-- ══ LOADING ══════════════════════════════════════════════════════════ -->
  {#if loading}
    <div class="loader-wrap" aria-live="polite">
      <div class="spin-lg"></div>
      <p>Running valuation engine for <strong>{ticker}</strong>…</p>
      <p class="muted-sm">First request may take 30–60 s while Render wakes up.</p>
    </div>
  {/if}

  <!-- ══ EMPTY STATE ══════════════════════════════════════════════════════ -->
  {#if !hasRun && !loading}
    <div class="empty-state">
      <span class="empty-icon">🔍</span>
      <p>Enter a ticker to generate an institutional-grade valuation report</p>
      <p class="muted-sm">Powered by DCF · Monte Carlo Simulation · Peer Multiples</p>
    </div>
  {/if}

  <!-- ══════════════════ RESULT ══════════════════════════════════════════ -->
  {#if result}

    <!-- Report title bar -->
    <div class="rpt-header">
      <div>
        <div class="rpt-tag">✔ Valuation Complete</div>
        <h2 class="rpt-ticker">{result.ticker ?? ticker}</h2>
        <p class="rpt-time">Generated {new Date(result.generated_at).toLocaleString()}</p>
      </div>
      <span class="mode-badge">{market} · {mode}</span>
    </div>

    <!-- ── KPI Cards ─────────────────────────────────────────────────── -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-lbl">Blended Value</div>
        <div class="kpi-val">{fmtMoney(result.summary?.blended_value, result.summary?.unit)}</div>
        <div class="kpi-sub">Triangulated estimate</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-lbl">DCF Value</div>
        <div class="kpi-val">{fmtMoney(result.summary?.dcf_value, result.summary?.unit)}</div>
        <div class="kpi-sub">Discounted cash flow</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-lbl">P50 — Median</div>
        <div class="kpi-val">{fmtMoney(result.summary?.p50, result.summary?.unit)}</div>
        <div class="kpi-sub">Monte Carlo median</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-lbl">Upside to P90</div>
        <div class="kpi-val kpi-green">{fmtPct(result.summary?.upside_to_p90_pct)}</div>
        <div class="kpi-sub">Downside P10: {fmtPct(result.summary?.downside_to_p10_pct)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-lbl">Confidence</div>
        <div class="kpi-val">
          {result.confidence?.confidence_score != null
            ? (result.confidence.confidence_score * 100).toFixed(1) + "%"
            : "—"}
        </div>
        <div class="kpi-sub">Model reliability</div>
      </div>
      {#if result.dynamic_wacc}
        <div class="kpi-card">
          <div class="kpi-lbl">Dynamic WACC</div>
          <div class="kpi-val">{fmtPct(result.dynamic_wacc.base_wacc * 100)}</div>
          <div class="kpi-sub">
            β = {result.dynamic_wacc.beta?.toFixed(2) ?? "—"} ·
            vol = {fmtPct(result.dynamic_wacc.market_volatility * 100)}
          </div>
        </div>
      {/if}
    </div>

    <!-- ── AI Signal Card ────────────────────────────────────────────── -->
    {#if result.ai_summary}
      <div class="signal-card">
        <div class="sig-left">
          <div class="sig-chip {signalClass(result.ai_summary.signal)}">{result.ai_summary.signal}</div>
          <p class="sig-insight">{result.ai_summary.investment_insight}</p>
          <ul class="sig-list">
            {#each result.ai_summary.explanation ?? [] as line}
              <li>{line}</li>
            {/each}
          </ul>
        </div>
        <div class="sig-metrics">
          {#if result.comparison_metrics}
            <div class="sm-row">
              <span class="sm-lbl">Market Price</span>
              <span class="sm-val">
                {result.comparison_metrics.market_value != null
                  ? fmtMoney(result.comparison_metrics.market_value, result.summary?.unit)
                  : "N/A"}
              </span>
            </div>
            <div class="sm-row">
              <span class="sm-lbl">Model vs Market</span>
              <span class="sm-val">
                {result.comparison_metrics.error_pct != null
                  ? fmtPct(result.comparison_metrics.error_pct)
                  : "N/A"}
              </span>
            </div>
            <div class="sm-row">
              <span class="sm-lbl">Label</span>
              <span class="sm-val accent">{result.comparison_metrics.label}</span>
            </div>
          {/if}
          <div class="sm-row">
            <span class="sm-lbl">Multiples Value</span>
            <span class="sm-val">{fmtMoney(result.summary?.multiples_value, result.summary?.unit)}</span>
          </div>
          <div class="sm-row">
            <span class="sm-lbl">P10</span>
            <span class="sm-val">{fmtMoney(result.summary?.p10, result.summary?.unit)}</span>
          </div>
          <div class="sm-row">
            <span class="sm-lbl">P90</span>
            <span class="sm-val">{fmtMoney(result.summary?.p90, result.summary?.unit)}</span>
          </div>
        </div>
      </div>
    {/if}

    <!-- ── Validation Warnings ───────────────────────────────────────── -->
    {#if result.validation_diagnostics?.warnings?.length}
      <div class="alert alert-warn">
        <strong>⚠ Validation Warnings</strong>
        <ul class="warn-list">
          {#each result.validation_diagnostics.warnings as w}<li>{w}</li>{/each}
        </ul>
      </div>
    {/if}

    <!-- ── Charts ────────────────────────────────────────────────────── -->
    <div class="section-title">📊 Valuation Analysis</div>
    <div class="charts-grid">
      <div class="chart-card chart-full">
        <div class="chart-title">Valuation Breakdown — DCF · Multiples · Blended · P10/50/90</div>
        <div class="chart-wrap"><canvas bind:this={canvasVal}></canvas></div>
      </div>
      {#if result.fcf_forecast?.length}
        <div class="chart-card">
          <div class="chart-title">FCF Forecast (Stochastic Projection)</div>
          <div class="chart-wrap"><canvas bind:this={canvasFcf}></canvas></div>
        </div>
      {/if}
      {#if result.monte_carlo?.histogram?.length}
        <div class="chart-card">
          <div class="chart-title">Monte Carlo Distribution ({result.model_inputs?.monte_carlo_inputs?.simulations?.toLocaleString() ?? "N"} simulations)</div>
          <div class="chart-wrap"><canvas bind:this={canvasMc}></canvas></div>
        </div>
      {/if}
    </div>

    <!-- ── Model Inputs ───────────────────────────────────────────────── -->
    {#if result.model_inputs}
      <div class="section-title">⚙️ Model Inputs</div>
      <div class="detail-grid">
        <div class="detail-grp">
          <div class="dg-title">DCF Inputs</div>
          <table class="dt">
            <tbody>
              <tr><td>Forecast Growth Rate</td><td>{fmtPct(result.model_inputs.dcf_inputs?.forecast_growth_rate_pct)}</td></tr>
              <tr><td>Terminal Growth Rate</td><td>{fmtPct(result.model_inputs.dcf_inputs?.terminal_growth_rate_pct)}</td></tr>
              <tr><td>Forecast Horizon</td><td>{result.model_inputs.dcf_inputs?.forecast_horizon_years} years</td></tr>
            </tbody>
          </table>
        </div>
        <div class="detail-grp">
          <div class="dg-title">WACC Breakdown</div>
          <table class="dt">
            <tbody>
              <tr><td>Risk-free Rate</td><td>{fmtPct(result.model_inputs.wacc_breakdown?.risk_free_rate * 100)}</td></tr>
              <tr><td>Beta</td><td>{fmtRatio(result.model_inputs.wacc_breakdown?.beta)}</td></tr>
              <tr><td>Market Risk Premium</td><td>{fmtPct(result.model_inputs.wacc_breakdown?.market_risk_premium * 100)}</td></tr>
              <tr><td>Cost of Equity (CAPM)</td><td>{fmtPct(result.model_inputs.wacc_breakdown?.cost_of_equity * 100)}</td></tr>
              <tr><td>Cost of Debt</td><td>{fmtPct(result.model_inputs.wacc_breakdown?.cost_of_debt * 100)}</td></tr>
              <tr><td>Tax Rate</td><td>{fmtPct(result.model_inputs.wacc_breakdown?.tax_rate * 100)}</td></tr>
              <tr><td>Equity / Debt Weight</td><td>{fmtPct(result.model_inputs.wacc_breakdown?.equity_weight * 100)} / {fmtPct(result.model_inputs.wacc_breakdown?.debt_weight * 100)}</td></tr>
              <tr><td>Final WACC</td><td class="td-hi">{fmtPct(result.model_inputs.wacc_breakdown?.final_wacc * 100)}</td></tr>
            </tbody>
          </table>
        </div>
        <div class="detail-grp">
          <div class="dg-title">Monte Carlo Inputs</div>
          <table class="dt">
            <tbody>
              <tr><td>Simulations</td><td>{result.model_inputs.monte_carlo_inputs?.simulations?.toLocaleString()}</td></tr>
              <tr><td>Growth Volatility</td><td>{fmtPct(result.model_inputs.monte_carlo_inputs?.growth_volatility * 100)}</td></tr>
              <tr><td>WACC Volatility</td><td>{fmtPct(result.model_inputs.monte_carlo_inputs?.wacc_volatility * 100)}</td></tr>
              <tr><td>Distribution</td><td>{result.model_inputs.monte_carlo_inputs?.distribution_assumptions}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <!-- ── Peer Multiples ─────────────────────────────────────────────── -->
    {#if result.multiples}
      <div class="section-title">📐 Peer Multiples</div>
      <div class="detail-grid">
        <div class="detail-grp detail-wide">
          <table class="dt">
            <tbody>
              <tr><td>Peer Median EV / EBITDA</td><td>{fmtRatio(result.multiples.median_ev_ebitda)}</td></tr>
              <tr><td>Peer Median P / B</td><td>{result.multiples.median_price_to_book == null ? "N/A" : fmtRatio(result.multiples.median_price_to_book)}</td></tr>
              <tr><td>Implied Value (EV/EBITDA)</td><td>{fmtMoney(result.multiples.implied_value_ev_ebitda, result.summary?.unit)}</td></tr>
              <tr><td>Implied Value (P/B)</td><td>{result.multiples.implied_value_price_to_book == null ? "N/A" : fmtMoney(result.multiples.implied_value_price_to_book, result.summary?.unit)}</td></tr>
              <tr><td>Final Multiples Valuation</td><td class="td-hi">{fmtMoney(result.summary?.multiples_value, result.summary?.unit)}</td></tr>
              <tr><td>Anchor Used</td><td>{result.multiples.selected_anchor ?? "N/A"}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <!-- ── Validation Diagnostics ────────────────────────────────────── -->
    {#if result.validation_diagnostics}
      <div class="section-title">🔬 Model Validation</div>
      <div class="detail-grid">
        <div class="detail-grp detail-wide">
          <table class="dt">
            <tbody>
              <tr><td>DCF vs Multiples Deviation</td><td>{fmtPct(result.validation_diagnostics.dcf_multiples_deviation_pct)}</td></tr>
              <tr><td>Monte Carlo Variance (std/mean)</td><td>{fmtRatio(result.validation_diagnostics.monte_carlo_variance_ratio)}</td></tr>
              <tr><td>Probability Undervalued</td><td>{fmtPct(result.validation_diagnostics.probability_undervalued * 100)}</td></tr>
              <tr><td>Reliability</td><td class="td-hi">{result.validation_diagnostics.reliability_label}</td></tr>
              {#each Object.entries(result.validation_diagnostics.confidence_breakdown ?? {}) as [k, v]}
                <tr><td>{k.replaceAll("_", " ")}</td><td>{fmtRatio(v)}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <!-- ── Performance Metrics ───────────────────────────────────────── -->
    {#if result.performance_metrics}
      <div class="section-title">📈 Performance Metrics</div>
      <div class="detail-grid">
        <div class="detail-grp detail-wide">
          <table class="dt">
            <tbody>
              <tr><td>Absolute Error %</td><td>{result.performance_metrics.absolute_error_pct == null ? "N/A" : fmtPct(result.performance_metrics.absolute_error_pct)}</td></tr>
              <tr><td>Stability (Variance Ratio)</td><td>{fmtRatio(result.performance_metrics.stability_variance_ratio)}</td></tr>
              <tr><td>Sensitivity to WACC</td><td>{fmtPct(result.performance_metrics.wacc_sensitivity_pct)}</td></tr>
              <tr><td>Scenario Spread (P90 − P10)</td><td>{fmtMoney(result.performance_metrics.scenario_spread, result.summary?.unit)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <!-- ══════════════ COMPANY COMPARISON ════════════════════════════════ -->
    <div class="cmp-section">
      <div class="section-title">⚖️ Compare with Another Ticker</div>
      <div class="cmp-controls">
        <div class="field field-lg">
          <label for="tk-b">Second Ticker</label>
          <input
            id="tk-b"
            type="text"
            value={tickerB}
            on:input={e => { tickerB = e.target.value.toUpperCase().trimStart(); compareError = ""; }}
            on:keydown={e => e.key === "Enter" && runComparison()}
            placeholder="e.g. RELIANCE"
            autocomplete="off"
          />
        </div>
        <button class="btn-secondary" on:click={runComparison} disabled={loadingB}>
          {#if loadingB}
            <span class="spin-sm" aria-hidden="true"></span> Fetching…
          {:else}
            ⚖️ Compare
          {/if}
        </button>
      </div>

      {#if compareError}
        <div class="alert alert-err">{compareError}</div>
      {/if}

      {#if resultB}
        <!-- Side-by-side table -->
        <div class="cmp-tbl-wrap">
          <table class="cmp-tbl">
            <thead>
              <tr>
                <th>Metric</th>
                <th class="th-a">{result.ticker ?? ticker}</th>
                <th class="th-b">{resultB.ticker ?? tickerB}</th>
              </tr>
            </thead>
            <tbody>
              {#each [
                { label: "Blended Value",  a: result.summary?.blended_value,      b: resultB.summary?.blended_value,      fmt: v => fmtMoney(v, result.summary?.unit) },
                { label: "DCF Value",      a: result.summary?.dcf_value,          b: resultB.summary?.dcf_value,          fmt: v => fmtMoney(v, result.summary?.unit) },
                { label: "P50 (Median)",   a: result.summary?.p50,                b: resultB.summary?.p50,                fmt: v => fmtMoney(v, result.summary?.unit) },
                { label: "Upside (P90 %)", a: result.summary?.upside_to_p90_pct,  b: resultB.summary?.upside_to_p90_pct,  fmt: fmtPct },
                { label: "Confidence",     a: result.confidence?.confidence_score, b: resultB.confidence?.confidence_score, fmt: v => fmtPct(v * 100) },
              ] as row}
                {@const win = betterVal(row.a, row.b)}
                <tr>
                  <td class="cmp-metric">{row.label}</td>
                  <td class:cmp-win={win === "A"}>{row.fmt(row.a)}</td>
                  <td class:cmp-win={win === "B"}>{row.fmt(row.b)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

        <!-- Comparison chart -->
        <div class="chart-card chart-full" style="margin-top:1rem">
          <div class="chart-title">
            Valuation Comparison — {result.ticker ?? ticker} vs {resultB.ticker ?? tickerB}
          </div>
          <div class="chart-wrap"><canvas bind:this={canvasCmp}></canvas></div>
        </div>
      {/if}
    </div>

    <!-- ══════════ AI PROBABILISTIC SIMULATION RESULTS ═══════════════════ -->
    {#if simStats}
      <div class="sim-section">
        <div class="sim-banner">
          <span class="sim-icon">🎲</span>
          <div>
            <div class="sim-title">AI Probabilistic Valuation Mode</div>
            <div class="sim-sub">
              {simStats.count.toLocaleString()} Monte Carlo simulations · randomised growth & discount rate
            </div>
          </div>
        </div>

        <!-- Sim KPI cards -->
        <div class="sim-kpi-row">
          <div class="sim-kpi-card">
            <div class="sim-kpi-lbl">Mean Valuation</div>
            <div class="sim-kpi-val">{fmtMoney(simStats.mean, simStats.unit)}</div>
            <div class="sim-kpi-sub">Expected value across {simStats.count} runs</div>
          </div>
          <div class="sim-kpi-card">
            <div class="sim-kpi-lbl">Median (P50)</div>
            <div class="sim-kpi-val">{fmtMoney(simStats.median, simStats.unit)}</div>
            <div class="sim-kpi-sub">50th percentile outcome</div>
          </div>
          <div class="sim-kpi-card sim-bear">
            <div class="sim-kpi-lbl">Bear Case (P5)</div>
            <div class="sim-kpi-val bear">{fmtMoney(simStats.p5, simStats.unit)}</div>
            <div class="sim-kpi-sub">5th percentile — worst 5% of outcomes</div>
          </div>
          <div class="sim-kpi-card sim-bull">
            <div class="sim-kpi-lbl">Bull Case (P95)</div>
            <div class="sim-kpi-val bull">{fmtMoney(simStats.p95, simStats.unit)}</div>
            <div class="sim-kpi-sub">95th percentile — best 5% of outcomes</div>
          </div>
        </div>

        <!-- Range bar -->
        <div class="sim-range-wrap">
          <span class="sim-range-lbl">Bear</span>
          <div class="sim-range-bar">
            <div class="sim-range-fill"></div>
            <div class="sim-range-mid" title="Median"></div>
          </div>
          <span class="sim-range-lbl">Bull</span>
          <span class="sim-range-legend">
            {fmtMoney(simStats.p5, simStats.unit)} — {fmtMoney(simStats.p95, simStats.unit)}
          </span>
        </div>

        <!-- Sim histogram -->
        <div class="chart-card chart-full" style="margin-top:1rem">
          <div class="chart-title">Simulation Distribution — {simStats.count} DCF outcomes (₹ Crores)</div>
          <div class="chart-wrap"><canvas bind:this={canvasSim}></canvas></div>
        </div>
      </div>
    {/if}

  {/if}
  <!-- ── end result ──────────────────────────────────────────────────── -->
</main>

<style>
  /* ── Global ─────────────────────────────────────────────────────────── */
  :global(*) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) {
    background: #080c12;
    color: #dde3ec;
    font-family: "Inter", "Segoe UI", system-ui, sans-serif;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 1.75rem 1.5rem 6rem;
  }

  /* ── Header ─────────────────────────────────────────────────────────── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding-bottom: 1.5rem;
    margin-bottom: 2rem;
    border-bottom: 1px solid #10192a;
  }

  .brand { display: flex; align-items: center; gap: 0.85rem; }
  .brand-icon { font-size: 2rem; line-height: 1; }

  h1 {
    font-size: 1.55rem;
    font-weight: 700;
    color: #f0f4f8;
    letter-spacing: -0.025em;
  }

  .brand-sub {
    font-size: 0.76rem;
    color: #3d4f63;
    margin-top: 0.2rem;
    letter-spacing: 0.02em;
  }

  .hdr-badge {
    font-size: 0.7rem;
    background: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.2);
    color: #60a5fa;
    border-radius: 20px;
    padding: 0.3rem 0.85rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    white-space: nowrap;
  }

  /* ── Controls panel ─────────────────────────────────────────────────── */
  .controls-panel {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: flex-end;
    background: #0d1420;
    border: 1px solid #10192a;
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 0.85rem;
  }

  .field { display: flex; flex-direction: column; gap: 0.4rem; flex: 1; min-width: 130px; }
  .field-lg { flex: 2; }

  label {
    font-size: 0.68rem;
    font-weight: 700;
    color: #3d4f63;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  input, select {
    background: #080c12;
    border: 1px solid #10192a;
    border-radius: 8px;
    color: #dde3ec;
    font-size: 0.9rem;
    padding: 0.55rem 0.75rem;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    width: 100%;
  }

  input::placeholder { color: #1e2c3e; }
  input:focus, select:focus {
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
  select option { background: #0d1420; }

  .btn-primary {
    align-self: flex-end;
    background: linear-gradient(135deg, #2563eb, #4f46e5);
    border: none;
    border-radius: 8px;
    color: #fff;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.88rem;
    font-weight: 700;
    padding: 0.6rem 1.5rem;
    transition: opacity 0.15s, transform 0.1s;
    white-space: nowrap;
    min-width: 152px;
    justify-content: center;
    letter-spacing: 0.02em;
  }
  .btn-primary:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-secondary {
    align-self: flex-end;
    background: #10192a;
    border: 1px solid #1a2a3e;
    border-radius: 8px;
    color: #60a5fa;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.88rem;
    font-weight: 700;
    padding: 0.55rem 1.2rem;
    transition: background 0.15s;
    white-space: nowrap;
    letter-spacing: 0.02em;
  }
  .btn-secondary:hover:not(:disabled) { background: #172235; }
  .btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

  /* ── Chips ──────────────────────────────────────────────────────────── */
  .chips-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-bottom: 1.5rem;
    padding: 0 0.1rem;
  }

  .chips-lbl { font-size: 0.72rem; color: #2d3a4a; font-weight: 600; margin-right: 0.1rem; }

  .chip {
    background: #0f1925;
    border: 1px solid #172235;
    border-radius: 20px;
    color: #60a5fa;
    cursor: pointer;
    font-size: 0.73rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.22rem 0.75rem;
    transition: background 0.14s, border-color 0.14s;
  }
  .chip:hover { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.4); }

  /* ── Alerts ─────────────────────────────────────────────────────────── */
  .alert {
    display: flex;
    gap: 0.6rem;
    align-items: flex-start;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    font-size: 0.87rem;
    margin-bottom: 1.25rem;
    line-height: 1.5;
  }

  .alert-err {
    background: rgba(239, 68, 68, 0.09);
    border: 1px solid rgba(239, 68, 68, 0.25);
    color: #fca5a5;
  }

  .alert-warn {
    background: rgba(234, 179, 8, 0.09);
    border: 1px solid rgba(234, 179, 8, 0.25);
    color: #fde68a;
    flex-direction: column;
    gap: 0.45rem;
  }

  .warn-list { padding-left: 1.2rem; }
  .warn-list li { margin: 0.15rem 0; }

  /* ── Loader ─────────────────────────────────────────────────────────── */
  .loader-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.85rem;
    padding: 4.5rem 0;
    color: #3d4f63;
    font-size: 0.9rem;
    text-align: center;
  }

  .spin-lg {
    width: 42px; height: 42px;
    border: 3px solid #10192a;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  .spin-sm {
    display: inline-block;
    width: 13px; height: 13px;
    border: 2px solid rgba(255, 255, 255, 0.25);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  @keyframes spin { to { transform: rotate(360deg); } }
  .muted-sm { font-size: 0.78rem; color: #243040; }

  /* ── Empty state ────────────────────────────────────────────────────── */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.65rem;
    padding: 6rem 0;
    color: #1e2c3e;
    font-size: 0.92rem;
    user-select: none;
    text-align: center;
  }
  .empty-icon { font-size: 2.5rem; opacity: 0.35; }

  /* ── Report header ──────────────────────────────────────────────────── */
  .rpt-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
    animation: fadeUp 0.3s ease;
  }

  .rpt-tag {
    font-size: 0.68rem;
    font-weight: 800;
    color: #4ade80;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin-bottom: 0.15rem;
  }

  .rpt-ticker {
    font-size: 2rem;
    font-weight: 800;
    color: #f0f4f8;
    letter-spacing: -0.03em;
    line-height: 1.1;
  }

  .rpt-time { font-size: 0.76rem; color: #3d4f63; margin-top: 0.25rem; }

  .mode-badge {
    background: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 20px;
    color: #60a5fa;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.3rem 0.85rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    white-space: nowrap;
    margin-top: 0.4rem;
  }

  /* ── KPI Row ────────────────────────────────────────────────────────── */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
    gap: 0.85rem;
    margin-bottom: 1.25rem;
    animation: fadeUp 0.3s ease;
  }

  .kpi-card {
    background: #0d1420;
    border: 1px solid #10192a;
    border-radius: 12px;
    padding: 1rem 1.1rem;
  }

  .kpi-lbl {
    font-size: 0.66rem;
    font-weight: 700;
    color: #3b82f6;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 0.4rem;
  }

  .kpi-val {
    font-size: 1.2rem;
    font-weight: 700;
    color: #f0f4f8;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }

  .kpi-green { color: #4ade80; }
  .kpi-sub { font-size: 0.68rem; color: #2d3a4a; margin-top: 0.3rem; line-height: 1.4; }

  /* ── Signal card ────────────────────────────────────────────────────── */
  .signal-card {
    background: #0d1420;
    border: 1px solid #10192a;
    border-radius: 14px;
    padding: 1.25rem 1.4rem;
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    margin-bottom: 1.25rem;
    animation: fadeUp 0.32s ease;
  }

  .sig-left { flex: 1; min-width: 220px; }
  .sig-metrics { flex: 0 0 220px; }

  .sig-chip {
    display: inline-block;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    border-radius: 6px;
    padding: 0.28rem 0.9rem;
    margin-bottom: 0.75rem;
  }

  .sig-green  { background: rgba(74, 222, 128, 0.12); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.3); }
  .sig-red    { background: rgba(239, 68, 68, 0.12);  color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
  .sig-yellow { background: rgba(234, 179, 8, 0.12);  color: #fde047; border: 1px solid rgba(234, 179, 8, 0.3); }

  .sig-insight {
    font-size: 0.86rem;
    color: #7e9ab5;
    line-height: 1.55;
    margin-bottom: 0.75rem;
  }

  .sig-list {
    padding-left: 1.1rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.8rem;
    color: #4a607a;
    line-height: 1.45;
  }

  .sm-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.32rem 0;
    border-bottom: 1px solid #10192a;
    font-size: 0.8rem;
  }
  .sm-row:last-child { border-bottom: none; }
  .sm-lbl { color: #3d4f63; font-size: 0.73rem; }
  .sm-val  { color: #b8ccd8; font-weight: 600; }
  .accent  { color: #60a5fa; }

  /* ── Section titles ─────────────────────────────────────────────────── */
  .section-title {
    font-size: 0.76rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #3d4f63;
    margin: 1.85rem 0 0.85rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  /* ── Charts grid ────────────────────────────────────────────────────── */
  .charts-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.9rem;
    animation: fadeUp 0.35s ease;
  }

  .chart-card {
    background: #0d1420;
    border: 1px solid #10192a;
    border-radius: 12px;
    padding: 1rem 1.1rem;
  }

  .chart-full { grid-column: 1 / -1; }

  .chart-title {
    font-size: 0.72rem;
    font-weight: 700;
    color: #3d4f63;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.75rem;
  }

  .chart-wrap { height: 280px; position: relative; }
  .chart-wrap canvas { width: 100% !important; height: 100% !important; }

  /* ── Detail grid ────────────────────────────────────────────────────── */
  .detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
    gap: 0.9rem;
    animation: fadeUp 0.35s ease;
  }

  .detail-grp {
    background: #0d1420;
    border: 1px solid #10192a;
    border-radius: 12px;
    padding: 1rem 1.1rem;
    overflow: hidden;
  }

  .detail-wide { grid-column: 1 / -1; }

  .dg-title {
    font-size: 0.68rem;
    font-weight: 800;
    color: #3b82f6;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 0.65rem;
  }

  .dt { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  .dt td { padding: 0.3rem 0.2rem; border-bottom: 1px solid #10192a; vertical-align: middle; }
  .dt tr:last-child td { border-bottom: none; }
  .dt td:first-child { color: #3d4f63; font-weight: 500; width: 62%; }
  .dt td:last-child  { color: #dde3ec; text-align: right; font-weight: 600; }
  .td-hi { color: #60a5fa !important; }

  /* ── Comparison section ─────────────────────────────────────────────── */
  .cmp-section {
    margin-top: 2.5rem;
    padding-top: 2rem;
    border-top: 1px solid #10192a;
    animation: fadeUp 0.4s ease;
  }

  .cmp-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.85rem;
    align-items: flex-end;
    margin-bottom: 0.85rem;
  }

  .cmp-tbl-wrap { overflow-x: auto; margin-bottom: 0.5rem; }

  .cmp-tbl { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
  .cmp-tbl th, .cmp-tbl td {
    padding: 0.6rem 0.9rem;
    border: 1px solid #10192a;
    text-align: right;
  }
  .cmp-tbl th {
    background: #0d1420;
    font-size: 0.7rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #3d4f63;
  }
  .th-a { color: #60a5fa !important; }
  .th-b { color: #fde047 !important; }
  .cmp-tbl td:first-child { text-align: left; color: #3d4f63; font-weight: 500; }
  .cmp-tbl tr:nth-child(even) td { background: rgba(13, 20, 32, 0.5); }
  .cmp-metric { font-weight: 500; }
  .cmp-win { color: #4ade80 !important; font-weight: 700; }

  /* ── Simulation section ─────────────────────────────────────────────── */
  .sim-section {
    margin-top: 2rem;
    padding-top: 2rem;
    border-top: 1px solid #10192a;
    animation: fadeUp 0.4s ease;
  }

  .sim-banner {
    display: flex;
    align-items: center;
    gap: 1rem;
    background: linear-gradient(135deg, rgba(139,92,246,0.12), rgba(99,102,241,0.08));
    border: 1px solid rgba(139,92,246,0.25);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.25rem;
  }

  .sim-icon { font-size: 1.75rem; line-height: 1; flex-shrink: 0; }

  .sim-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #c4b5fd;
    letter-spacing: -0.01em;
  }

  .sim-sub {
    font-size: 0.76rem;
    color: #5b4f7c;
    margin-top: 0.2rem;
  }

  .sim-kpi-row {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.85rem;
    margin-bottom: 1rem;
  }

  .sim-kpi-card {
    background: #0d1420;
    border: 1px solid #10192a;
    border-radius: 12px;
    padding: 1rem 1.1rem;
  }

  .sim-bear { border-color: rgba(239,68,68,0.25); }
  .sim-bull { border-color: rgba(74,222,128,0.25); }

  .sim-kpi-lbl {
    font-size: 0.66rem;
    font-weight: 700;
    color: #8b5cf6;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 0.4rem;
  }

  .sim-kpi-val {
    font-size: 1.15rem;
    font-weight: 700;
    color: #f0f4f8;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }

  .sim-kpi-val.bear { color: #f87171; }
  .sim-kpi-val.bull { color: #4ade80; }

  .sim-kpi-sub {
    font-size: 0.67rem;
    color: #2d3a4a;
    margin-top: 0.3rem;
    line-height: 1.4;
  }

  .sim-range-wrap {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.6rem 0;
    margin-bottom: 0.25rem;
  }

  .sim-range-lbl {
    font-size: 0.7rem;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .sim-range-bar {
    flex: 1;
    height: 8px;
    background: linear-gradient(90deg, rgba(239,68,68,0.6), rgba(139,92,246,0.7), rgba(74,222,128,0.6));
    border-radius: 4px;
    position: relative;
  }

  .sim-range-mid {
    position: absolute;
    left: 50%;
    top: -3px;
    width: 2px;
    height: 14px;
    background: #c4b5fd;
    border-radius: 2px;
    transform: translateX(-50%);
  }

  .sim-range-legend {
    font-size: 0.73rem;
    color: #475569;
    white-space: nowrap;
    font-weight: 500;
  }

  /* ── Animations ─────────────────────────────────────────────────────── */
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* ── Responsive ─────────────────────────────────────────────────────── */
  @media (max-width: 768px) {
    .charts-grid { grid-template-columns: 1fr; }
    .chart-full { grid-column: unset; }
    .detail-wide { grid-column: unset; }
    .hdr-badge { display: none; }
    .sig-metrics { flex: 1 1 100%; }
    .rpt-ticker { font-size: 1.6rem; }
  }
</style>