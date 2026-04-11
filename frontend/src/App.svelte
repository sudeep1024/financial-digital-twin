<script>
  import { onMount } from 'svelte';
  import MonteCarlo
  import FCFForecastChart from './components/FCFForecastChart.svelte';
  import ValuationComparisonChart from './components/ValuationComparisonChart.svelte';
  import NewsFeed from './components/NewsFeed.svelte';

  const API_BASE = import.meta.env.VITE_API_BASE || "https://financial-digital-twin-api.onrender.com";

  let valuationEntryMode = 'ticker';
  let tickerInput = 'HDFCBANK';
  let market = 'NSE';
  let mode = 'internal';
  let activeTicker = 'HDFCBANK.NS';
  let manualInput = {
    company_name: 'ManualCo',
    sector: 'Financials',
    country: 'India',
    revenue: 1000,
    ebitda: 300,
    net_income: 120,
    debt: 400,
    equity: 600,
    cash: 150,
    operating_cf: 250,
    capex: 50
  };
  let report = null;
  let loading = false;
  let error = '';
  let notice = '';
  let manualWarning = '';
  let comparisonMode = true;
  let tickers = [];
  let tickerLoading = false;
  let tickerError = '';

  const currency = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    notation: 'compact',
    compactDisplay: 'short',
    maximumFractionDigits: 2
  });
  const croreNumber = new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: 2
  });

  function fmtMoney(value, unit = report?.summary?.unit || '') {
    const numeric = Number(value || 0);
    if (unit === 'INR Crores') {
      return `${croreNumber.format(numeric)} Cr`;
    }
    return currency.format(numeric);
  }

  function fmtPct(value) {
    return `${Number(value || 0).toFixed(2)}%`;
  }

  function fmtRatio(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 'N/A';
    return numeric.toFixed(3);
  }

  async function parseResponseBody(response) {
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      return { detail: text || `HTTP ${response.status}` };
    }
  }

  function validateManualPayload(payload) {
    const warnings = [];
    if (!(payload.revenue > 0)) warnings.push('Revenue must be greater than 0.');
    if (payload.ebitda > payload.revenue) warnings.push('EBITDA exceeds revenue.');
    if (payload.net_income > payload.revenue) warnings.push('Net Income exceeds revenue.');
    if (payload.debt > payload.revenue * 100) warnings.push('Debt is unreasonably high versus revenue (>100x).');
    if (payload.equity > 0 && payload.debt / payload.equity > 3) warnings.push('Debt/Equity is above 3x.');

    const ocfAbs = Math.abs(payload.operating_cf);
    if (ocfAbs > 0 && payload.capex > ocfAbs * 2.5) {
      warnings.push('CapEx is unreasonably high versus Operating Cash Flow.');
    }
    if (ocfAbs === 0 && payload.capex > payload.revenue * 0.5) {
      warnings.push('CapEx is too high for zero OCF and current revenue.');
    }
    if (payload.operating_cf - payload.capex < 0) {
      warnings.push('Free cash flow is negative (OCF - CapEx).');
    }
    return warnings;
  }

  async function loadTickers(selectedMarket = market) {
    tickerLoading = true;
    tickerError = '';
    try {
      const url = `${API_BASE}/market/tickers?market=${encodeURIComponent(selectedMarket)}&limit=20000&mode=${encodeURIComponent(mode)}`;
      console.log("[TICKERS] Calling:", url);
      const response = await fetch(url);

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || 'Failed to load ticker universe.');
      }
      tickers = payload.tickers || [];
    } catch (err) {
      tickerError = err.message || 'Failed to load ticker universe.';
      tickers = [];
    } finally {
      tickerLoading = false;
    }
  }

async function fetchReport(ticker = tickerInput, selectedMarket = market) {
    loading = true;
    error = '';
    notice = '';
    manualWarning = '';
    report = null;
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000); // 45s timeout for cold starts
    
    let lastError = null;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const url = `${API_BASE}/valuation/full-report?ticker=${encodeURIComponent(
          ticker
        )}&market=${encodeURIComponent(selectedMarket)}&mode=${encodeURIComponent(mode)}`;
        
        console.log(`[API ${attempt}] API_BASE:`, API_BASE);
        console.log(`[API ${attempt}] Calling:`, url);
        
        const response = await fetch(url, { signal: controller.signal });
        clearTimeout(timeoutId);
        
        console.log(`[API ${attempt}] Response status:`, response.status, response.statusText);
        console.log(`[API ${attempt}] Response headers:`, [...response.headers.entries()]);
        
        const payload = await parseResponseBody(response);
        if (!response.ok) {
          console.error(`[API ${attempt}] Server error:`, response.status, payload);
          
          // Retry on 5xx (server errors, cold starts)
          if (attempt === 1 && response.status >= 500) {
            console.log(`[API ${attempt}] Retrying due to 5xx... (Render cold start?)`);
            await new Promise(resolve => setTimeout(resolve, 10000)); // 10s delay
            continue;
          }
          
          const detail = payload.detail || `HTTP ${response.status}`;
          throw new Error(detail);
        }
        
        report = payload;
        activeTicker = payload.ticker || ticker.toUpperCase();
        comparisonMode = true;
        return; // Success
        
      } catch (err) {
        console.error(`[API ${attempt}] Fetch failed:`, err.message, {url, attempt});
        lastError = err;
        
        if (err.name === 'AbortError') {
          error = 'Request timeout (45s). Backend may be waking from sleep (Render free tier). Try again in 30-60s.';
          break;
        }
        if (attempt === 2) break;
        
        // Wait before retry
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
    
    // Final error
    error = lastError?.message || 'Failed after retries.';
    if (error.includes('timeout') || error.includes('ECONNRESET')) {
      error += ' Tip: Render backend sleeps; first request wakes it (30-60s).';
    }

      const payload = await parseResponseBody(response);
      if (!response.ok) {
        const detail = payload.detail || 'Failed to load valuation report.';
        const fallbackEligible =
          mode === 'internal' &&
          (detail.includes('does not have full reproducible pipeline artifacts') ||
            detail.includes('not configured in internal reproducible dataset'));

        const demoUnavailable =
          mode === 'demo' &&
          (detail.toLowerCase().includes('demo mode unavailable') ||
            detail.toLowerCase().includes('yfinance') ||
            detail.toLowerCase().includes('missing dependency') ||
            detail.toLowerCase().includes('live data fetch failed') ||
            detail.toLowerCase().includes('failed to connect') ||
            detail.toLowerCase().includes('curl'));

        if (fallbackEligible) {
          mode = 'demo';
          notice = `Internal reproducible artifacts are unavailable for ${ticker.toUpperCase()} (${selectedMarket}). Switched to Demo mode automatically.`;

          const demoUrl = `${API_BASE}/valuation/full-report?ticker=${encodeURIComponent(
            ticker
          )}&market=${encodeURIComponent(selectedMarket)}&mode=demo`;
          const demoResponse = await fetch(demoUrl);
          const demoPayload = await demoResponse.json();
          if (!demoResponse.ok) {
            throw new Error(demoPayload.detail || detail);
          }
          report = demoPayload;
          activeTicker = demoPayload.ticker || ticker.toUpperCase();
          comparisonMode = true;
          return;
        }

        if (demoUnavailable) {
          mode = 'internal';
          notice = `Demo mode is unavailable on this setup for ${ticker.toUpperCase()}. Switched to Internal mode automatically.`;
          const internalUrl = `${API_BASE}/valuation/full-report?ticker=${encodeURIComponent(
            ticker
          )}&market=${encodeURIComponent(selectedMarket)}&mode=internal`;
          const internalResponse = await fetch(internalUrl);
          const internalPayload = await parseResponseBody(internalResponse);
          if (!internalResponse.ok) {
            throw new Error(internalPayload.detail || detail);
          }
          report = internalPayload;
          activeTicker = internalPayload.ticker || ticker.toUpperCase();
          comparisonMode = true;
          return;
        }

        throw new Error(detail);
      }
      report = payload;
      activeTicker = payload.ticker || ticker.toUpperCase();
      comparisonMode = true;
    } catch (err) {
      error = err.message || 'Unexpected error.';
    } finally {
      loading = false;
    }
  }

  async function fetchManualReport() {
    error = '';
    notice = '';
    manualWarning = '';
    report = null;
    try {
      const payload = {
        company_name: String(manualInput.company_name || '').trim(),
        sector: String(manualInput.sector || '').trim(),
        country: String(manualInput.country || '').trim(),
        revenue: Number(manualInput.revenue),
        ebitda: Number(manualInput.ebitda),
        net_income: Number(manualInput.net_income),
        debt: Number(manualInput.debt),
        equity: Number(manualInput.equity),
        cash: Number(manualInput.cash),
        operating_cf: Number(manualInput.operating_cf),
        capex: Number(manualInput.capex)
      };

      const validationWarnings = validateManualPayload(payload);
      if (validationWarnings.length > 0) {
        manualWarning = `Input warnings: ${validationWarnings.join(' ')}`;
      }

      loading = true;

      const url = `${API_BASE}/valuation/manual`;
      console.log("[MANUAL] Calling:", url, payload);
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to run manual valuation.');
      }
      report = data;
      activeTicker = data.ticker || payload.company_name.toUpperCase();
      comparisonMode = true;
    } catch (err) {
      error = err.message || 'Unexpected error.';
    } finally {
      loading = false;
    }
  }

  function onMarketChange() {
    manualWarning = '';
    loadTickers(market);
  }

  function onModeChange() {
    manualWarning = '';
    loadTickers(market);
  }

  function submit(event) {
    event.preventDefault();
    manualWarning = '';
    if (valuationEntryMode === 'manual') {
      fetchManualReport();
      return;
    }
    if (!tickerInput.trim()) return;
    fetchReport(tickerInput.trim(), market);
  }

  $: filteredTickers =
    tickerInput.trim().length === 0
      ? tickers.slice(0, 250)
      : tickers
          .filter((item) => {
            const q = tickerInput.trim().toUpperCase();
            return item.symbol.startsWith(q) || item.name.toUpperCase().includes(q);
          })
          .slice(0, 250);

  onMount(() => {
    loadTickers(market);
    fetchReport();
  });
</script>

<main class="app-shell">
  <section class="left-panel">
    <div class="panel-header">
      <p class="eyebrow">AI Financial Assistant</p>
      <h1>Financial Digital Twin</h1>
      <p class="subtle">Probabilistic intrinsic valuation from fundamentals and simulation.</p>
    </div>

    <form class="search-form" on:submit={submit}>
      <label>
        Input Mode
        <select bind:value={valuationEntryMode}>
          <option value="ticker">Ticker Mode</option>
          <option value="manual">Manual Input Mode</option>
        </select>
      </label>

      {#if valuationEntryMode === 'ticker'}
        <label>
          Ticker
          <input
            bind:value={tickerInput}
            list="ticker-universe"
            placeholder="Choose from market list or type manually"
          />
          <datalist id="ticker-universe">
            {#each filteredTickers as item}
              <option value={item.symbol}>{item.symbol} - {item.name}</option>
            {/each}
          </datalist>
        </label>
        <label>
          Market
          <select bind:value={market} on:change={onMarketChange}>
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
            <option value="NASDAQ">NASDAQ</option>
            <option value="NYSE">NYSE</option>
          </select>
        </label>
        <label>
          Mode
          <select bind:value={mode} on:change={onModeChange}>
            <option value="internal">Internal (Reproducible)</option>
            <option value="demo">Demo (Live APIs)</option>
          </select>
        </label>
      {:else}
        <label>
          Company Name
          <input bind:value={manualInput.company_name} placeholder="Company name" />
        </label>
        <label>
          Sector
          <input bind:value={manualInput.sector} placeholder="e.g. Financials" />
        </label>
        <label>
          Country
          <input bind:value={manualInput.country} placeholder="e.g. India" />
        </label>
        <label>
          Revenue
          <input type="number" bind:value={manualInput.revenue} />
        </label>
        <label>
          EBITDA
          <input type="number" bind:value={manualInput.ebitda} />
        </label>
        <label>
          Net Income
          <input type="number" bind:value={manualInput.net_income} />
        </label>
        <label>
          Debt
          <input type="number" bind:value={manualInput.debt} />
        </label>
        <label>
          Equity
          <input type="number" bind:value={manualInput.equity} />
        </label>
        <label>
          Cash
          <input type="number" bind:value={manualInput.cash} />
        </label>
        <label>
          Operating CF
          <input type="number" bind:value={manualInput.operating_cf} />
        </label>
        <label>
          CapEx
          <input type="number" bind:value={manualInput.capex} />
        </label>
      {/if}
      <button type="submit" disabled={loading}>{loading ? 'Analyzing...' : 'Run Valuation'}</button>
    </form>

    {#if valuationEntryMode === 'ticker' && tickerLoading}
      <div class="error-box">Loading full ticker universe for {market}...</div>
    {:else if valuationEntryMode === 'ticker' && tickerError}
      <div class="error-box">{tickerError}</div>
    {/if}

    {#if notice}
      <div class="notice-box">{notice}</div>
    {/if}

    {#if manualWarning}
      <div class="notice-box">{manualWarning}</div>
    {/if}

    {#if error}
      <div class="error-box">{error}</div>
    {/if}

    {#if report}
      <div class="ai-response">
        <h2>AI Response</h2>
        <div class="summary-grid">
          <div>
            <p class="label">Signal</p>
            <p class="value">{report.ai_summary.signal}</p>
          </div>
          <div>
            <p class="label">Confidence</p>
            <p class="value">{(report.confidence.confidence_score * 100).toFixed(1)}%</p>
          </div>
          {#if report.manual_input_summary}
            <div>
              <p class="label">Input Quality</p>
              <p class="value">{(report.manual_input_summary.input_quality_score * 100).toFixed(1)}%</p>
            </div>
          {/if}
        </div>
        <p class="insight">{report.ai_summary.investment_insight}</p>
        <ul>
          {#each report.ai_summary.explanation as line}
            <li>{line}</li>
          {/each}
        </ul>
        {#if report.dynamic_wacc}
          <p class="insight">
            <span title="Weighted Average Cost of Capital; discount rate used in DCF.">Dynamic WACC</span>: {(report.dynamic_wacc.base_wacc * 100).toFixed(2)}% |
            <span title="Beta measures sensitivity to market returns in CAPM.">Beta</span>: {report.dynamic_wacc.beta.toFixed(2)} |
            <span title="Monte Carlo uses stochastic FCF and WACC path variation.">Volatility</span>: {(report.dynamic_wacc.market_volatility * 100).toFixed(2)}%
          </p>
        {/if}
      </div>

      {#if valuationEntryMode === 'ticker'}
        <NewsFeed ticker={activeTicker} />
      {/if}
    {/if}
  </section>

  <section class="right-panel">
    {#if loading}
      <div class="loading-box">Running valuation engine...</div>
    {:else if report}
      <div class="headline">
        <h2>{activeTicker}</h2>
        <p>Generated {new Date(report.generated_at).toLocaleString()}</p>
      </div>

      {#if report.validation_diagnostics?.warnings?.length}
        <div class="notice-box warning-list">
          <strong>Validation Warnings</strong>
          <ul>
            {#each report.validation_diagnostics.warnings as warn}
              <li>{warn}</li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if report.manual_input_summary}
        <div class="panel-block">
          <h3>Model Inputs Summary</h3>
          <div class="kpi-grid">
            <article class="kpi-card">
              <p>Unit</p>
              <h3>{report.manual_input_summary.unit}</h3>
            </article>
            <article class="kpi-card">
              <p>Revenue</p>
              <h3>{fmtMoney(report.manual_input_summary.revenue, report.manual_input_summary.unit)}</h3>
            </article>
            <article class="kpi-card">
              <p>EBITDA Margin</p>
              <h3>{(report.manual_input_summary.ebitda_margin * 100).toFixed(2)}%</h3>
            </article>
            <article class="kpi-card">
              <p>Net Margin</p>
              <h3>{(report.manual_input_summary.net_margin * 100).toFixed(2)}%</h3>
            </article>
            <article class="kpi-card">
              <p>Free Cash Flow</p>
              <h3>{fmtMoney(report.manual_input_summary.free_cash_flow, report.manual_input_summary.unit)}</h3>
            </article>
            <article class="kpi-card">
              <p>Debt / Equity</p>
              <h3>{report.manual_input_summary.debt_to_equity.toFixed(2)}x</h3>
            </article>
            <article class="kpi-card">
              <p>Input Quality Score</p>
              <h3>{report.manual_input_summary.input_quality_score.toFixed(2)}</h3>
            </article>
            <article class="kpi-card">
              <p>Realism Score</p>
              <h3>{report.manual_input_summary.realism_score.toFixed(2)}</h3>
            </article>
          </div>
        </div>
      {/if}

      <div class="panel-block">
        <h3>Valuation Snapshot</h3>
        <div class="kpi-grid">
          <article class="kpi-card">
            <p>DCF Value</p>
            <h3>{fmtMoney(report.summary.dcf_value, report.summary.unit)}</h3>
          </article>
          <article class="kpi-card">
            <p>P10 / P50 / P90</p>
            <h3>{fmtMoney(report.summary.p10, report.summary.unit)} / {fmtMoney(report.summary.p50, report.summary.unit)} / {fmtMoney(report.summary.p90, report.summary.unit)}</h3>
          </article>
          <article class="kpi-card">
            <p>Multiples Value</p>
            <h3>{fmtMoney(report.summary.multiples_value, report.summary.unit)}</h3>
          </article>
          <article class="kpi-card">
            <p>Blended Value</p>
            <h3>{fmtMoney(report.summary.blended_value, report.summary.unit)}</h3>
          </article>
          <article class="kpi-card">
            <p>Upside / Downside</p>
            <h3>{fmtPct(report.summary.upside_to_p90_pct)} / {fmtPct(report.summary.downside_to_p10_pct)}</h3>
          </article>
        </div>
      </div>

      {#if report.model_inputs}
        <div class="panel-block">
          <h3>Model Inputs</h3>
          <div class="kpi-grid">
            <article class="kpi-card">
              <p>Forecast Growth Rate</p>
              <h3>{fmtPct(report.model_inputs.dcf_inputs.forecast_growth_rate_pct)}</h3>
            </article>
            <article class="kpi-card">
              <p>Terminal Growth Rate</p>
              <h3>{fmtPct(report.model_inputs.dcf_inputs.terminal_growth_rate_pct)}</h3>
            </article>
            <article class="kpi-card">
              <p>Forecast Horizon</p>
              <h3>{report.model_inputs.dcf_inputs.forecast_horizon_years} years</h3>
            </article>
            <article class="kpi-card">
              <p title="Risk-free benchmark yield used in CAPM.">Risk-free Rate</p>
              <h3>{fmtPct(report.model_inputs.wacc_breakdown.risk_free_rate * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p title="Beta from sector/market sensitivity in CAPM.">Beta</p>
              <h3>{fmtRatio(report.model_inputs.wacc_breakdown.beta)}</h3>
            </article>
            <article class="kpi-card">
              <p>Market Risk Premium</p>
              <h3>{fmtPct(report.model_inputs.wacc_breakdown.market_risk_premium * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p>Cost of Equity (CAPM)</p>
              <h3>{fmtPct(report.model_inputs.wacc_breakdown.cost_of_equity * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p>Cost of Debt</p>
              <h3>{fmtPct(report.model_inputs.wacc_breakdown.cost_of_debt * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p>Tax Rate</p>
              <h3>{fmtPct(report.model_inputs.wacc_breakdown.tax_rate * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p>Equity / Debt Weights</p>
              <h3>{fmtPct(report.model_inputs.wacc_breakdown.equity_weight * 100)} / {fmtPct(report.model_inputs.wacc_breakdown.debt_weight * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p>Final WACC</p>
              <h3>{fmtPct(report.model_inputs.wacc_breakdown.final_wacc * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p title="Number of Monte Carlo valuation runs.">Monte Carlo Simulations</p>
              <h3>{report.model_inputs.monte_carlo_inputs.simulations}</h3>
            </article>
            <article class="kpi-card">
              <p>Growth Volatility</p>
              <h3>{fmtPct(report.model_inputs.monte_carlo_inputs.growth_volatility * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p title="Pathwise WACC standard deviation used in simulation.">WACC Volatility</p>
              <h3>{fmtPct(report.model_inputs.monte_carlo_inputs.wacc_volatility * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p>Distribution Assumptions</p>
              <h3>{report.model_inputs.monte_carlo_inputs.distribution_assumptions}</h3>
            </article>
          </div>
        </div>
      {/if}

      <div class="panel-block">
        <h3>Multiples Model</h3>
        <div class="kpi-grid">
          <article class="kpi-card">
            <p>Peer Median EV / EBITDA</p>
            <h3>{fmtRatio(report.multiples.median_ev_ebitda)}</h3>
          </article>
          <article class="kpi-card">
            <p>Peer Median P / B</p>
            <h3>{report.multiples.median_price_to_book == null ? 'N/A' : fmtRatio(report.multiples.median_price_to_book)}</h3>
          </article>
          <article class="kpi-card">
            <p>Equity Value from EV/EBITDA</p>
            <h3>{fmtMoney(report.multiples.implied_value_ev_ebitda, report.summary.unit)}</h3>
          </article>
          <article class="kpi-card">
            <p>Equity Value from P/B</p>
            <h3>{report.multiples.implied_value_price_to_book == null ? 'N/A' : fmtMoney(report.multiples.implied_value_price_to_book, report.summary.unit)}</h3>
          </article>
          <article class="kpi-card">
            <p>Final Multiples Valuation</p>
            <h3>{fmtMoney(report.summary.multiples_value, report.summary.unit)}</h3>
          </article>
          <article class="kpi-card">
            <p>Anchor Used</p>
            <h3>{report.multiples.selected_anchor || 'N/A'}</h3>
          </article>
        </div>
      </div>

      {#if report.validation_diagnostics}
        <div class="panel-block">
          <h3>Model Validation Panel</h3>
          <div class="kpi-grid">
            <article class="kpi-card">
              <p>DCF vs Multiples Deviation</p>
              <h3>{fmtPct(report.validation_diagnostics.dcf_multiples_deviation_pct)}</h3>
            </article>
            <article class="kpi-card">
              <p>Monte Carlo Variance (std/mean)</p>
              <h3>{fmtRatio(report.validation_diagnostics.monte_carlo_variance_ratio)}</h3>
            </article>
            <article class="kpi-card">
              <p>Probability Undervalued</p>
              <h3>{fmtPct(report.validation_diagnostics.probability_undervalued * 100)}</h3>
            </article>
            <article class="kpi-card">
              <p>Reliability</p>
              <h3>{report.validation_diagnostics.reliability_label}</h3>
            </article>
            {#each Object.entries(report.validation_diagnostics.confidence_breakdown || {}) as [key, value]}
              <article class="kpi-card">
                <p>{key.replaceAll('_', ' ')}</p>
                <h3>{fmtRatio(value)}</h3>
              </article>
            {/each}
          </div>
        </div>
      {/if}

      {#if report.comparison_metrics}
        <div class="panel-block">
          <div class="toggle-row">
            <h3>Comparison Mode</h3>
            <label class="toggle-control">
              <input type="checkbox" bind:checked={comparisonMode} />
              <span>Internal Model vs Market Price</span>
            </label>
          </div>
          {#if comparisonMode}
            <div class="kpi-grid">
              <article class="kpi-card">
                <p>Model Value</p>
                <h3>{fmtMoney(report.comparison_metrics.model_value, report.summary.unit)}</h3>
              </article>
              <article class="kpi-card">
                <p>Market Value</p>
                <h3>{report.comparison_metrics.market_value == null ? 'N/A' : fmtMoney(report.comparison_metrics.market_value, report.summary.unit)}</h3>
              </article>
              <article class="kpi-card">
                <p>Error %</p>
                <h3>{report.comparison_metrics.error_pct == null ? 'N/A' : fmtPct(report.comparison_metrics.error_pct)}</h3>
              </article>
              <article class="kpi-card">
                <p>Label</p>
                <h3>{report.comparison_metrics.label}</h3>
              </article>
            </div>
          {/if}
        </div>
      {/if}

      {#if report.performance_metrics}
        <div class="panel-block">
          <h3>Performance Panel</h3>
          <div class="kpi-grid">
            <article class="kpi-card">
              <p>Absolute Error %</p>
              <h3>{report.performance_metrics.absolute_error_pct == null ? 'N/A' : fmtPct(report.performance_metrics.absolute_error_pct)}</h3>
            </article>
            <article class="kpi-card">
              <p>Stability (Variance)</p>
              <h3>{fmtRatio(report.performance_metrics.stability_variance_ratio)}</h3>
            </article>
            <article class="kpi-card">
              <p>Sensitivity to WACC</p>
              <h3>{fmtPct(report.performance_metrics.wacc_sensitivity_pct)}</h3>
            </article>
            <article class="kpi-card">
              <p>Scenario Spread (P90 - P10)</p>
              <h3>{fmtMoney(report.performance_metrics.scenario_spread, report.summary.unit)}</h3>
            </article>
          </div>
        </div>
      {/if}

      {#if report.digital_twin}
        <div class="panel-block">
          <h3>Digital Twin Visualization</h3>
          <pre class="json-viewer">{JSON.stringify(report.digital_twin, null, 2)}</pre>
        </div>
      {/if}

      <div class="chart-grid">
        <article class="chart-card">
          <h3>Monte Carlo Histogram</h3>
          <MonteCarloHistogram histogram={report.monte_carlo.histogram} unit={report.summary.unit || 'INR'} />
        </article>
        <article class="chart-card">
          <h3>FCF Forecast</h3>
          <FCFForecastChart forecast={report.fcf_forecast} unit={report.summary.unit || 'INR'} />
        </article>
        <article class="chart-card full-width">
          <h3>Valuation Comparison</h3>
          <ValuationComparisonChart
            dcf={report.summary.dcf_value}
            multiples={report.summary.multiples_value}
            blended={report.summary.blended_value}
            p10={report.summary.p10}
            p50={report.summary.p50}
            p90={report.summary.p90}
            unit={report.summary.unit || 'INR'}
          />
        </article>
      </div>
    {/if}
  </section>
</main>
