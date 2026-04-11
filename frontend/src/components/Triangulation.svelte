<script>
  let { data } = $props();

  const formatter = new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0, notation: "compact", compactDisplay: "short"
  });

  let dcfVal = $derived(data?.dcf?.enterprise_value ?? 0);
  let mcVal = $derived(data?.monte_carlo?.p50 ?? 0);
  let mltVal = $derived(data?.multiples?.implied_value_ev_ebitda ?? 0);
  
  let blendedValue = $derived((dcfVal * 0.4) + (mcVal * 0.3) + (mltVal * 0.3));
</script>

<section class="bg-zinc-950/40 p-8 md:p-12 rounded-[3.5rem] border border-zinc-900 relative overflow-hidden group shadow-2xl backdrop-blur-3xl">
  <!-- Internal Glow -->
  <div class="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent pointer-events-none transition-opacity group-hover:opacity-100 opacity-50"></div>
  
  <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-8 mb-16 relative z-10">
    <div class="space-y-3">
      <div class="label-mono text-cyan-500">Blended Valuation Matrix</div>
      <h2 class="text-4xl font-black text-white tracking-tighter">Triangulated Fair Value</h2>
    </div>
    <div class="bg-black/80 border border-zinc-800 rounded-2xl p-6 px-10 text-right shadow-2xl">
       <span class="label-mono opacity-50 block mb-2">Final Weighted Target</span>
       <span class="text-6xl font-black text-premium tracking-tighter">{formatter.format(blendedValue)}</span>
    </div>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-8 relative z-10">
    <div class="bg-zinc-900/20 border border-zinc-800/60 p-6 rounded-3xl group/item hover:bg-zinc-800/30 transition-all">
       <div class="flex justify-between items-end mb-4">
         <span class="label-mono text-zinc-600 group-hover/item:text-cyan-400 transition-colors">DCF Projection</span>
         <span class="text-[10px] bg-zinc-800 px-2 py-0.5 rounded text-zinc-400">W: 40%</span>
       </div>
       <div class="text-2xl font-black text-white">{formatter.format(dcfVal)}</div>
       <div class="mt-4 h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
         <div class="h-full bg-cyan-500/50" style="width: 40%"></div>
       </div>
    </div>
    <div class="bg-zinc-900/20 border border-zinc-800/60 p-6 rounded-3xl group/item hover:bg-zinc-800/30 transition-all">
       <div class="flex justify-between items-end mb-4">
         <span class="label-mono text-zinc-600 group-hover/item:text-indigo-400 transition-colors">Monte Carlo</span>
         <span class="text-[10px] bg-zinc-800 px-2 py-0.5 rounded text-zinc-400">W: 30%</span>
       </div>
       <div class="text-2xl font-black text-white">{formatter.format(mcVal)}</div>
       <div class="mt-4 h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
         <div class="h-full bg-indigo-500/50" style="width: 30%"></div>
       </div>
    </div>
    <div class="bg-zinc-900/20 border border-zinc-800/60 p-6 rounded-3xl group/item hover:bg-zinc-800/30 transition-all">
       <div class="flex justify-between items-end mb-4">
         <span class="label-mono text-zinc-600 group-hover/item:text-fuchsia-400 transition-colors">Peer Multiples</span>
         <span class="text-[10px] bg-zinc-800 px-2 py-0.5 rounded text-zinc-400">W: 30%</span>
       </div>
       <div class="text-2xl font-black text-white">{formatter.format(mltVal)}</div>
       <div class="mt-4 h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
         <div class="h-full bg-fuchsia-500/50" style="width: 30%"></div>
       </div>
    </div>
  </div>
</section>
