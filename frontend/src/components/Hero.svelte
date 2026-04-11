<script>
  export let ticker = "HDFCBANK.NS";
</script>

<header class="mb-10 flex flex-col md:flex-row md:justify-between md:items-center relative pb-8 border-b border-white/10">
  <div>
    <div class="flex items-center gap-3 mb-3">
      <div class="w-2 h-2 bg-indigo-400 rounded-full animate-pulse shadow-[0_0_12px_#818cf8]"></div>
      <span class="text-xs text-indigo-300 font-mono tracking-[0.25em] uppercase font-bold">Global Valuation Engine</span>
    </div>
    <h1 class="text-4xl md:text-5xl font-black tracking-tight text-gradient mb-2">Financial Digital Twin</h1>
    <p class="text-slate-400 text-base font-medium">Algorithmic pricing synthesis & NLP market sentiment analysis</p>
  </div>
  
  <div class="mt-6 md:mt-0 flex items-center gap-5 apple-glass px-6 py-4 rounded-2xl shadow-xl group cursor-default">
    <div class="w-12 h-12 rounded-full bg-gradient-to-tr from-indigo-500 to-fuchsia-500 flex items-center justify-center shadow-[0_0_20px_rgba(99,102,241,0.5)]">
      <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path></svg>
    </div>
    <div class="flex flex-col text-left">
      <span class="text-[10px] text-slate-400 uppercase tracking-[0.15em] font-bold mb-1">Target Asset</span>
      <span class="text-2xl font-mono text-white tracking-widest font-black group-hover:text-indigo-300 transition-colors drop-shadow-md">{ticker}</span>
    </div>
  </div>
</header>
