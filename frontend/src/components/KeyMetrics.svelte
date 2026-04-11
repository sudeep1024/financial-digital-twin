<script>
  let { data } = $props();

  const formatter = new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0
  });

  let dcfVal = $derived(data?.dcf?.enterprise_value ?? 0);
  let mcVal = $derived(data?.monte_carlo?.p50 ?? 0);
  let mltVal = $derived(data?.multiples?.implied_value_ev_ebitda ?? 0);
  let conf = $derived((data?.confidence?.confidence_score ?? 0) * 100);
</script>

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
  <!-- DCF Strip -->
  <div class="panel-glass p-8 rounded-[2.5rem] hover-elevate group">
    <div class="label-mono mb-4 text-zinc-500 group-hover:text-cyan-400/80 transition-colors">Intrinsic (DCF)</div>
    <div class="text-3xl font-black text-white tracking-tighter mb-6">{formatter.format(dcfVal)}</div>
    <div class="space-y-2">
      <div class="data-strip border-none p-0 group-hover:bg-transparent">
        <span class="label-mono text-[8px] text-zinc-600 opacity-60">WACC Benchmark</span>
        <span class="text-xs font-mono text-zinc-300">{(data?.dcf?.wacc ? data.dcf.wacc * 100 : 0).toFixed(2)}%</span>
      </div>
      <div class="data-strip border-none p-0 group-hover:bg-transparent">
        <span class="label-mono text-[8px] text-zinc-600 opacity-60">Term Growth</span>
        <span class="text-xs font-mono text-zinc-300">{(data?.dcf?.terminal_growth_rate ? data.dcf.terminal_growth_rate * 100 : 0).toFixed(1)}%</span>
      </div>
    </div>
  </div>

  <!-- MC Strip -->
  <div class="panel-glass p-8 rounded-[2.5rem] hover-elevate group border-t-cyan-500/20">
    <div class="label-mono mb-4 text-cyan-400">Monte Carlo (P50)</div>
    <div class="text-3xl font-black text-white tracking-tighter mb-6">{formatter.format(mcVal)}</div>
    <div class="w-full bg-zinc-900/80 h-1.5 rounded-full overflow-hidden mt-auto">
       <div class="h-full bg-cyan-500" style="width: 75%"></div>
    </div>
    <p class="text-[9px] font-mono text-zinc-600 mt-2 uppercase tracking-widest text-center">Variance Probability: High</p>
  </div>

  <!-- Confidence Strip -->
  <div class="panel-glass p-8 rounded-[2.5rem] hover-elevate group border-t-emerald-500/20">
    <div class="label-mono mb-4 text-emerald-400">Quant Conviction</div>
    <div class="flex items-baseline gap-2 mb-6">
       <span class="text-5xl font-black text-emerald-400">{conf.toFixed(0)}</span>
       <span class="text-xl font-bold text-emerald-900">%</span>
    </div>
    <div class="flex gap-1 justify-between items-end mt-auto h-8">
      {#each Array(8) as _, i}
        <div class="w-2.5 rounded-sm bg-zinc-800 {i < (conf/12.5) ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]' : ''}"></div>
      {/each}
    </div>
  </div>

  <!-- Signal Strip -->
  <div class="panel-glass p-8 rounded-[2.5rem] hover-elevate group bg-gradient-to-br from-indigo-500/10 to-transparent">
     <div class="label-mono mb-4 text-indigo-400">AI Signal</div>
     <div class="text-4xl font-black text-white tracking-widest mb-4">{data?.ai_summary?.signal || "HOLD"}</div>
     <div class="mt-auto py-2 bg-zinc-950/50 border border-zinc-800/50 rounded-xl text-center">
       <span class="text-[10px] font-mono font-bold text-indigo-300 tracking-[0.2em]">{data?.ai_summary?.upside_percent || 0}% Upside Est.</span>
     </div>
  </div>
</div>
