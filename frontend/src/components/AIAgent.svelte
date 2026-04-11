<script>
  import { onMount } from 'svelte';
  import { fly, fade } from 'svelte/transition';
  
  let { ticker, reportData, loading, onSearch } = $props();

  let searchInput = $state("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (searchInput.trim()) onSearch(searchInput);
  };
</script>

<div class="flex flex-col h-full">
  <!-- AI Response Log -->
  <div class="flex-1 space-y-8 overflow-y-auto no-scrollbar pr-2 pt-2">
    
    <!-- User Input Simulation -->
    <div class="space-y-2 opacity-60" in:fade>
      <div class="flex items-center gap-2 label-mono text-[9px]">
        <svg class="w-3 h-3 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
        Query Entry
      </div>
      <div class="bg-zinc-900/50 border border-zinc-800 text-zinc-400 text-xs p-4 rounded-2xl font-medium italic">
        "Assess the probabilistic intrinsic value for {ticker} using multi-model synthesis..."
      </div>
    </div>

    <!-- AI Systematic Response -->
    {#if reportData}
      <div class="space-y-6" in:fly={{y: 20, duration: 800}}>
        <div class="flex items-center gap-2 label-mono text-[9px] text-cyan-400/80">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          Nexus Inference Engine
        </div>

        <div class="space-y-4">
          <div class="bg-zinc-900/80 border border-zinc-800 rounded-[2rem] p-6 shadow-2xl relative overflow-hidden">
            <div class="absolute top-0 left-0 w-1 h-full bg-cyan-500/50"></div>
            <p class="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500 mb-4 border-b border-zinc-800 pb-3">Valuation Rationale</p>
            <div class="space-y-4">
               {#each (reportData?.ai_summary?.explanation || []) as text, i}
                 <div class="flex gap-4 group" in:fly={{x: -10, delay: i * 100}}>
                    <div class="mt-1.5 w-1.5 h-1.5 rounded-full bg-cyan-500 shadow-[0_0_8px_cyan] shrink-0 opacity-40 group-hover:opacity-100 transition"></div>
                    <p class="text-xs leading-relaxed text-zinc-300 font-medium">{text}</p>
                 </div>
               {/each}
            </div>
          </div>

          <!-- Quick Metrics inside AI Panel -->
          <div class="grid grid-cols-2 gap-4">
             <div class="bg-zinc-900/40 border border-zinc-800 p-5 rounded-3xl text-center">
                <p class="label-mono mb-2 text-[9px] opacity-60">Upside Target</p>
                <p class="text-2xl font-black text-emerald-400">+{reportData.ai_summary.upside_percent}%</p>
             </div>
             <div class="bg-zinc-900/40 border border-zinc-800 p-5 rounded-3xl text-center">
                <p class="label-mono mb-2 text-[9px] opacity-60">Market Regime</p>
                <p class="text-sm font-bold text-zinc-300 tracking-widest uppercase py-2">STABLE-ACCUM</p>
             </div>
          </div>
        </div>

        <!-- System Prompt Hint -->
        <div class="pt-6 border-t border-zinc-900">
           <p class="text-[9px] font-mono text-zinc-700 italic leading-loose">
             PROMPT EXECUTED: "Analyze ticker: {ticker} using DCF, Peer-Multiples, and Monte Carlo N=10,000 simulations. Apply Bayesian weighting to output final BLENDED target."
           </p>
        </div>
      </div>
    {/if}
  </div>

  <!-- Bottom Quick Input -->
  <div class="mt-auto pt-6 border-t border-zinc-900 bg-zinc-950/20">
    <form onsubmit={handleSubmit} class="relative w-full">
      <input 
        bind:value={searchInput}
        class="w-full bg-zinc-900/80 border border-zinc-800 rounded-2xl px-5 py-4 text-xs text-white placeholder-zinc-600 outline-none focus:border-cyan-500/50 transition-all font-medium"
        placeholder="Revise query or search new ticker..."
      />
      <button type="submit" aria-label="Search" class="absolute right-3 top-3 p-1.5 bg-zinc-800 text-zinc-400 rounded-lg hover:text-white transition">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
      </button>
    </form>
    <div class="mt-3 text-[9px] text-center font-bold text-zinc-700 uppercase tracking-widest">Shift + Enter to submit</div>
  </div>
</div>
