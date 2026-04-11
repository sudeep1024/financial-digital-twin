<script>
  const API_BASE =
    import.meta.env.VITE_API_BASE ||
    "https://financial-digital-twin-api.onrender.com";

  let ticker = "";
  let market = "NSE";
  let mode = "internal";

  let loading = false;
  let error = "";
  let result = null;

  const markets = ["NSE"];
  const modes = ["internal", "dcf", "comps"];

  async function runValuation() {
    if (!ticker.trim()) {
      error = "Please enter a ticker symbol.";
      return;
    }
    loading = true;
    error = "";
    result = null;

    try {
      const url = `${API_BASE}/valuation/full-report?ticker=${encodeURIComponent(
        ticker.trim().toUpperCase()
      )}&market=${encodeURIComponent(market)}&mode=${encodeURIComponent(mode)}`;

      const res = await fetch(url);

      if (!res.ok) {
        const body = await res.text();
        throw new Error(`API error ${res.status}: ${body}`);
      }

      result = await res.json();
    } catch (err) {
      error = err.message || "An unexpected error occurred.";
    } finally {
      loading = false;
    }
  }

  function formatValue(val) {
    if (val === null || val === undefined) return "—";
    if (typeof val === "object") return JSON.stringify(val, null, 2);
    return String(val);
  }

  function isObject(val) {
    return val !== null && typeof val === "object" && !Array.isArray(val);
  }

  function flatEntries(obj) {
    return Object.entries(obj);
  }
</script>

<main>
  <header>
    <div class="logo">
      <span class="logo-icon">📈</span>
      <div>
        <h1>Financial Digital Twin</h1>
        <p class="subtitle">AI-Powered Equity Valuation Engine</p>
      </div>
    </div>
  </header>

  <section class="controls">
    <div class="field">
      <label for="ticker">Ticker Symbol</label>
      <input
        id="ticker"
        type="text"
        placeholder="e.g. RELIANCE"
        bind:value={ticker}
        on:keydown={(e) => e.key === "Enter" && runValuation()}
      />
    </div>

    <div class="field">
      <label for="market">Market</label>
      <select id="market" bind:value={market}>
        {#each markets as m}
          <option value={m}>{m}</option>
        {/each}
      </select>
    </div>

    <div class="field">
      <label for="mode">Mode</label>
      <select id="mode" bind:value={mode}>
        {#each modes as md}
          <option value={md}>{md}</option>
        {/each}
      </select>
    </div>

    <button class="run-btn" on:click={runValuation} disabled={loading}>
      {#if loading}
        <span class="spinner"></span> Analysing…
      {:else}
        ▶ Run Valuation
      {/if}
    </button>
  </section>

  {#if error}
    <div class="banner error">
      <span>⚠</span>
      <span>{error}</span>
    </div>
  {/if}

  {#if loading}
    <div class="loader-wrap">
      <div class="big-spinner"></div>
      <p>Fetching full report for <strong>{ticker.toUpperCase()}</strong>…</p>
    </div>
  {/if}

  {#if result}
    <section class="result">
      <div class="result-header">
        <h2>Valuation Report — {result.ticker ?? ticker.toUpperCase()}</h2>
        <span class="badge">{market} · {mode}</span>
      </div>

      <div class="cards">
        {#each flatEntries(result) as [key, val]}
          <div class="card">
            <div class="card-key">{key}</div>
            {#if isObject(val)}
              <table class="nested-table">
                {#each flatEntries(val) as [k2, v2]}
                  <tr>
                    <td class="nt-key">{k2}</td>
                    <td class="nt-val">{formatValue(v2)}</td>
                  </tr>
                {/each}
              </table>
            {:else if Array.isArray(val)}
              <pre class="card-pre">{JSON.stringify(val, null, 2)}</pre>
            {:else}
              <div class="card-val">{formatValue(val)}</div>
            {/if}
          </div>
        {/each}
      </div>
    </section>
  {/if}
</main>

<style>
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  :global(body) {
    background: #0d0f14;
    color: #e2e8f0;
    font-family: "Inter", "Segoe UI", system-ui, sans-serif;
    min-height: 100vh;
  }

  main {
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1.25rem 4rem;
  }

  header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 2.5rem;
    border-bottom: 1px solid #1e2433;
    padding-bottom: 1.5rem;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 0.9rem;
  }

  .logo-icon {
    font-size: 2rem;
    line-height: 1;
  }

  h1 {
    font-size: 1.6rem;
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -0.02em;
  }

  .subtitle {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 0.2rem;
    letter-spacing: 0.02em;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: flex-end;
    background: #131720;
    border: 1px solid #1e2433;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    flex: 1;
    min-width: 140px;
  }

  label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  input,
  select {
    background: #0d0f14;
    border: 1px solid #1e2433;
    border-radius: 8px;
    color: #e2e8f0;
    font-size: 0.95rem;
    padding: 0.55rem 0.75rem;
    outline: none;
    transition: border-color 0.18s;
    width: 100%;
  }

  input::placeholder {
    color: #3d4a5c;
  }

  input:focus,
  select:focus {
    border-color: #3b82f6;
  }

  select option {
    background: #131720;
  }

  .run-btn {
    align-self: flex-end;
    background: linear-gradient(135deg, #3b82f6, #6366f1);
    border: none;
    border-radius: 8px;
    color: #fff;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    font-weight: 600;
    padding: 0.6rem 1.4rem;
    transition: opacity 0.18s, transform 0.12s;
    white-space: nowrap;
  }

  .run-btn:hover:not(:disabled) {
    opacity: 0.88;
    transform: translateY(-1px);
  }

  .run-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .banner {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-bottom: 1.25rem;
    font-size: 0.9rem;
  }

  .error {
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid rgba(239, 68, 68, 0.35);
    color: #fca5a5;
  }

  .loader-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding: 3rem 0;
    color: #64748b;
    font-size: 0.9rem;
  }

  .big-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #1e2433;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .result {
    animation: fadeIn 0.35s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0);   }
  }

  .result-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-bottom: 1.25rem;
  }

  .result-header h2 {
    font-size: 1.15rem;
    font-weight: 700;
    color: #f1f5f9;
  }

  .badge {
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 20px;
    color: #93c5fd;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.3rem 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }

  .card {
    background: #131720;
    border: 1px solid #1e2433;
    border-radius: 10px;
    padding: 1rem 1.1rem;
    overflow: hidden;
  }

  .card-key {
    font-size: 0.72rem;
    font-weight: 700;
    color: #3b82f6;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
  }

  .card-val {
    font-size: 1rem;
    color: #e2e8f0;
    word-break: break-word;
  }

  .card-pre {
    font-size: 0.75rem;
    color: #94a3b8;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.55;
  }

  .nested-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
  }

  .nested-table tr {
    border-bottom: 1px solid #1e2433;
  }

  .nested-table tr:last-child {
    border-bottom: none;
  }

  .nt-key {
    color: #64748b;
    padding: 0.3rem 0.5rem 0.3rem 0;
    white-space: nowrap;
    vertical-align: top;
    font-weight: 500;
  }

  .nt-val {
    color: #e2e8f0;
    padding: 0.3rem 0;
    word-break: break-word;
    text-align: right;
  }
</style>