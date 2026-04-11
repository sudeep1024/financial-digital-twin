<script>
  import { onMount } from "svelte";

  const API_BASE =
    import.meta.env.VITE_API_BASE ||
    "https://financial-digital-twin-api.onrender.com";

  let tickerInput = "HDFCBANK";
  let market = "NSE";
  let mode = "internal";

  let loading = false;
  let error = null;
  let result = null;

  async function runValuation() {
    try {
      loading = true;
      error = null;
      result = null;

      const url = `${API_BASE}/valuation/full-report?ticker=${tickerInput}&market=${market}&mode=${mode}`;

      const res = await fetch(url);
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data?.detail || "API error");
      }

      result = data;
    } catch (err) {
      error = err.message || "Something went wrong";
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    // optional auto-run
    // runValuation();
  });
</script>

<main>
  <h1>Financial Digital Twin</h1>
  <p>Probabilistic intrinsic valuation from fundamentals and simulation.</p>

  <div class="card">
    <label>Ticker</label>
    <input bind:value={tickerInput} placeholder="HDFCBANK" />

    <label>Market</label>
    <select bind:value={market}>
      <option value="NSE">NSE</option>
    </select>

    <label>Mode</label>
    <select bind:value={mode}>
      <option value="internal">Internal</option>
    </select>

    <button on:click={runValuation}>
      {loading ? "Running..." : "Run Valuation"}
    </button>
  </div>

  {#if error}
    <div class="card" style="color: #f87171;">
      Error: {error}
    </div>
  {/if}

  {#if result}
    <div class="card">
      <h3>Result</h3>
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  {/if}
</main>

<style>
  main {
    background: #0f172a;
    color: white;
    min-height: 100vh;
    padding: 20px;
    font-family: sans-serif;
  }

  input,
  select,
  button {
    margin: 8px 0;
    padding: 10px;
    border-radius: 6px;
    border: none;
  }

  button {
    background: #10b981;
    color: white;
    cursor: pointer;
  }

  .card {
    background: #1e293b;
    padding: 15px;
    border-radius: 10px;
    margin-top: 15px;
  }
</style>
