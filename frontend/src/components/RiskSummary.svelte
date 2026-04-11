<script>
  let { risk_summary } = $props();
  
  const formatter = new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0
  });
</script>

<div class="flex-1 flex flex-col font-mono">
  <div class="flex-1 space-y-0.5">
    {#each (risk_summary || []) as item}
      {#if item.metric !== 'Base DCF Value'}
        <div class="data-strip hover:translate-x-1 group">
          <span class="text-[11px] text-zinc-500 font-medium group-hover:text-zinc-300 transition-colors uppercase tracking-widest">{item.metric}</span>
          <span class="text-xs font-black {item.metric.includes('Undervalued') ? 'text-emerald-400' : item.metric.includes('Overvalued') ? 'text-rose-500' : 'text-white'}">
            {#if typeof item.value === 'number'}
              {#if item.metric.includes('%') || item.metric.includes('Probability')}
                {(item.value * (item.metric.includes('Probability') ? 100 : 1)).toFixed(2)}%
              {:else}
                {formatter.format(item.value)}
              {/if}
            {:else}
              {item.value}
            {/if}
          </span>
        </div>
      {/if}
    {/each}
  </div>
</div>
