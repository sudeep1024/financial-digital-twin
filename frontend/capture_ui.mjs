import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000';
const UI_BASE = process.env.UI_BASE || 'http://127.0.0.1:5173';
const outDir = path.resolve(process.env.OUT_DIR || '../artifacts/screenshots');
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

await page.goto(`${API_BASE}/docs`, { waitUntil: 'domcontentloaded', timeout: 120000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: path.join(outDir, 'backend_docs.png'), fullPage: true });

await page.goto(UI_BASE, { waitUntil: 'domcontentloaded', timeout: 120000 });
await page.waitForTimeout(8000);
await page.screenshot({ path: path.join(outDir, 'dashboard_hdfcbank.png'), fullPage: true });

await page.locator('input[list="ticker-universe"]').fill('AAPL');
await page.locator('form.search-form label').nth(1).locator('select').selectOption('NASDAQ');
await page.locator('form.search-form label').nth(2).locator('select').selectOption('demo');
await page.getByRole('button', { name: 'Run Valuation' }).click();
await page.waitForTimeout(9000);
await page.screenshot({ path: path.join(outDir, 'dashboard_aapl_demo.png'), fullPage: true });

await browser.close();
console.log(outDir);
