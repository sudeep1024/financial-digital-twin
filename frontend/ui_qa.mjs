import { chromium } from 'playwright';

const UI_BASE = process.env.UI_BASE || 'http://127.0.0.1:5173';

function toNumber(text) {
  const cleaned = String(text || '').replace(/[^0-9.-]/g, '');
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

const result = {
  ticker_mode: {},
  manual_mode: {},
  charts: {},
  ai_panel: {},
  news_panel: {},
};

await page.goto(UI_BASE, { waitUntil: 'domcontentloaded', timeout: 120000 });
await page.waitForTimeout(3500);

// Ticker mode flow
await page.locator('input[list="ticker-universe"]').fill('HDFCBANK');
await page.locator('form.search-form label').nth(1).locator('select').selectOption('NSE');
await page.locator('form.search-form label').nth(2).locator('select').selectOption('internal');
await page.getByRole('button', { name: 'Run Valuation' }).click();
await page.waitForTimeout(5000);

result.ticker_mode.dashboard_loaded = (await page.locator('.headline h2').count()) > 0;
result.ticker_mode.active_ticker = (await page.locator('.headline h2').first().textContent())?.trim() || '';

// KPI sanity
const dcfText = (await page.locator('.kpi-card').nth(0).locator('h3').textContent()) || '';
result.ticker_mode.dcf_present = toNumber(dcfText) !== null;

// Charts
result.charts.monte_carlo = (await page.getByRole('heading', { name: 'Monte Carlo Histogram' }).count()) > 0;
result.charts.fcf_forecast = (await page.getByRole('heading', { name: 'FCF Forecast' }).count()) > 0;
result.charts.valuation_comparison = (await page.getByRole('heading', { name: 'Valuation Comparison' }).count()) > 0;

// AI panel
result.ai_panel.signal_present = (await page.locator('.summary-grid .value').first().count()) > 0;
result.ai_panel.confidence_present = (await page.locator('.summary-grid .value').nth(1).count()) > 0;
result.ai_panel.explanation_lines = await page.locator('.ai-response li').count();

// News panel
result.news_panel.loaded = (await page.getByRole('heading', { name: 'News Sentiment' }).count()) > 0;

// Manual mode flow
await page.locator('form.search-form label').first().locator('select').selectOption('manual');
await page.locator('input[placeholder="Company name"]').fill('ManualQA');
await page.locator('input[placeholder="e.g. Financials"]').fill('Financials');
await page.locator('input[placeholder="e.g. India"]').fill('India');
await page.locator('input[type="number"]').nth(0).fill('120000'); // revenue
await page.locator('input[type="number"]').nth(1).fill('35000');  // ebitda
await page.locator('input[type="number"]').nth(2).fill('15000');  // net income
await page.locator('input[type="number"]').nth(3).fill('30000');  // debt
await page.locator('input[type="number"]').nth(4).fill('90000');  // equity
await page.locator('input[type="number"]').nth(5).fill('20000');  // cash
await page.locator('input[type="number"]').nth(6).fill('28000');  // operating cf
await page.locator('input[type="number"]').nth(7).fill('6000');   // capex
await page.getByRole('button', { name: 'Run Valuation' }).click();
await page.waitForTimeout(3500);

result.manual_mode.dashboard_loaded = (await page.locator('.headline h2').count()) > 0;
result.manual_mode.active_ticker = (await page.locator('.headline h2').first().textContent())?.trim() || '';
result.manual_mode.manual_ticker_shape = result.manual_mode.active_ticker.includes('_MANUAL');
result.manual_mode.news_hidden = (await page.getByRole('heading', { name: 'News Sentiment' }).count()) === 0;

console.log(JSON.stringify(result, null, 2));
await browser.close();
