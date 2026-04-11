<script>
  let { selectedMarket = $bindable("NSE"), onSelect } = $props();

  const markets = [
    { id: "NSE", name: "National Stock Exchange (IN)", icon: "🇮🇳" },
    { id: "NASDAQ", name: "NASDAQ (US)", icon: "🇺🇸" },
    { id: "NYSE", name: "New York Stock Exchange (US)", icon: "🇺🇸" },
    { id: "BSE", name: "Bombay Stock Exchange (IN)", icon: "🇮🇳" },
    { id: "LSE", name: "London Stock Exchange (UK)", icon: "🇬🇧" }
  ];

  let isOpen = $state(false);

  const toggleDropdown = () => (isOpen = !isOpen);

  const selectMarket = (market) => {
    onSelect(market.id);
    isOpen = false;
  };
</script>

<div class="relative inline-block text-left z-50">
  <button 
    type="button"
    onclick={toggleDropdown}
    class="flex items-center gap-2 px-4 py-2.5 bg-zinc-900/80 border border-zinc-800 rounded-xl text-sm font-medium hover:bg-zinc-800 transition shadow-inner group"
  >
    <span class="text-xs opacity-60 uppercase tracking-widest font-bold">Market:</span>
    <span class="text-white">{selectedMarket}</span>
    <svg class="w-4 h-4 text-zinc-500 group-hover:text-white transition" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
    </svg>
  </button>

  {#if isOpen}
    <div 
      class="absolute left-0 mt-2 w-72 origin-top-left rounded-xl bg-zinc-900 border border-zinc-800 shadow-2xl backdrop-blur-xl p-2 focus:outline-none"
    >
      <div class="py-1">
        {#each markets as market}
          <button
            type="button"
            onclick={() => selectMarket(market)}
            class="flex items-center w-full px-4 py-3 text-sm text-zinc-400 hover:text-white hover:bg-zinc-800/50 rounded-lg transition group"
          >
            <span class="mr-3">{market.icon}</span>
            <span class="flex-1 text-left font-medium">{market.name}</span>
            {#if selectedMarket === market.id}
              <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            {/if}
          </button>
        {/each}
      </div>
    </div>
  {/if}
</div>
