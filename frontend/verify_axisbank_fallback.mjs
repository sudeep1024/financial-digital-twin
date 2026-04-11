import { chromium } from 'playwright';
import path from 'node:path';

const UI_BASE = process.env.UI_BASE || 'http://127.0.0.1:5173';
const OUT_DIR = path.resolve(process.env.OUT_DIR || '../artifacts/screenshots');

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

await page.goto(UI_BASE, { waitUntil: 'domcontentloaded', timeout: 120000 });
await page.waitForTimeout(4000);

await page.locator('input[list="ticker-universe"]').fill('AXISBANK');
await page.locator('form.search-form label').nth(1).locator('select').selectOption('NSE');
await page.locator('form.search-form label').nth(2).locator('select').selectOption('internal');
await page.getByRole('button', { name: 'Run Valuation' }).click();
await page.waitForTimeout(9000);

const modeValue = await page.locator('form.search-form label').nth(2).locator('select').inputValue();
const noticeVisible = await page.locator('.notice-box').count();
const headline = await page.locator('.headline h2').textContent();

console.log('mode=', modeValue);
console.log('noticeCount=', noticeVisible);
console.log('headline=', headline?.trim());

await page.screenshot({ path: path.join(OUT_DIR, 'axisbank_fallback.png'), fullPage: true });
await browser.close();
