<script>
  export let ticker = 'HDFCBANK.NS';

  const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';
  let loading = false;
  let error = '';
  let companyNews = [];
  let macroNews = [];
  let sentimentScore = 0;
  let loadedTicker = '';

  function sentimentClass(sentiment) {
    const value = String(sentiment || '').toLowerCase();
    if (value === 'positive') return 'positive';
    if (value === 'negative') return 'negative';
    return 'neutral';
  }

  async function fetchNews(force = false) {
    if (!ticker) return;
    if (!force && loadedTicker === ticker) return;
    loading = true;
    error = '';
    try {
      const response = await fetch(`${API_BASE}/news?ticker=${encodeURIComponent(ticker)}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || 'Failed to load news.');
      }
      companyNews = payload.company_news || [];
      macroNews = payload.macro_news || [];
      sentimentScore = payload.sentiment_score || 0;
      loadedTicker = ticker;
    } catch (err) {
      error = err.message || 'Failed to fetch news.';
      companyNews = [];
      macroNews = [];
    } finally {
      loading = false;
    }
  }

  $: if (ticker) {
    fetchNews();
  }
</script>

<section class="news-card">
  <div class="news-header">
    <h2>News Sentiment</h2>
    <p>Aggregate score: {sentimentScore.toFixed(3)}</p>
  </div>

  {#if loading}
    <p class="news-state">Loading company and macro feed...</p>
  {:else if error}
    <p class="news-error">{error}</p>
  {:else}
    <div class="news-grid">
      <div>
        <h3>Company News</h3>
        <div class="feed-list">
          {#if companyNews.length === 0}
            <p class="news-state">No company headlines found.</p>
          {:else}
            {#each companyNews as item}
              <article class="feed-item">
                <div class="title-row">
                  <a href={item.link} target="_blank" rel="noreferrer">{item.title}</a>
                  <span class={`sentiment ${sentimentClass(item.sentiment)}`}>
                    {item.sentiment} ({item.sentiment_score.toFixed(3)})
                  </span>
                </div>
                <p>{item.source} | {item.published_at}</p>
              </article>
            {/each}
          {/if}
        </div>
      </div>

      <div>
        <h3>Macro News</h3>
        <div class="feed-list">
          {#if macroNews.length === 0}
            <p class="news-state">No macro headlines found.</p>
          {:else}
            {#each macroNews as item}
              <article class="feed-item">
                <div class="title-row">
                  <a href={item.link} target="_blank" rel="noreferrer">{item.title}</a>
                  <span class={`sentiment ${sentimentClass(item.sentiment)}`}>
                    {item.sentiment} ({item.sentiment_score.toFixed(3)})
                  </span>
                </div>
                <p>{item.source} | {item.published_at}</p>
              </article>
            {/each}
          {/if}
        </div>
      </div>
    </div>
  {/if}
</section>

<style>
  .news-card {
    background: #0f172a;
    border: 1px solid #1f2937;
    border-radius: 16px;
    padding: 16px;
    margin-top: 16px;
  }

  .news-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 12px;
  }

  .news-header h2 {
    margin: 0;
    font-size: 1rem;
  }

  .news-header p {
    margin: 0;
    font-size: 0.82rem;
    color: #94a3b8;
  }

  .news-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .news-grid h3 {
    margin: 0 0 8px 0;
    font-size: 0.86rem;
    color: #cbd5e1;
  }

  .feed-list {
    max-height: 240px;
    overflow-y: auto;
    display: grid;
    gap: 8px;
    padding-right: 4px;
  }

  .feed-item {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 10px;
  }

  .title-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .feed-item a {
    color: #e2e8f0;
    text-decoration: none;
    font-size: 0.85rem;
    line-height: 1.4;
  }

  .feed-item a:hover {
    text-decoration: underline;
  }

  .feed-item p {
    margin: 8px 0 0 0;
    color: #94a3b8;
    font-size: 0.75rem;
  }

  .sentiment {
    width: fit-content;
    font-size: 0.72rem;
    border-radius: 999px;
    padding: 2px 8px;
    border: 1px solid transparent;
  }

  .sentiment.positive {
    color: #34d399;
    border-color: rgba(52, 211, 153, 0.4);
    background: rgba(5, 150, 105, 0.15);
  }

  .sentiment.negative {
    color: #f87171;
    border-color: rgba(248, 113, 113, 0.4);
    background: rgba(153, 27, 27, 0.15);
  }

  .sentiment.neutral {
    color: #cbd5e1;
    border-color: rgba(148, 163, 184, 0.35);
    background: rgba(30, 41, 59, 0.45);
  }

  .news-state {
    margin: 0;
    color: #94a3b8;
    font-size: 0.84rem;
  }

  .news-error {
    margin: 0;
    color: #fca5a5;
    font-size: 0.84rem;
  }

  @media (min-width: 1080px) {
    .news-grid {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
