// Phone-width check (needs Playwright + Chromium): every page fits 390 px with no
// horizontal scroll and no JS errors; the finder re-evaluates flags for a new date.
//   (cd mvp/dist && python3 -m http.server 8811) & node mvp/tests/mobile_check.js http://127.0.0.1:8811
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const base = process.argv[2] || 'http://127.0.0.1:8811';
  const sitemap = fs.readFileSync(path.join(__dirname, '..', 'dist', 'sitemap.xml'), 'utf8');
  const paths = [...sitemap.matchAll(/<loc>[^<]*?(\/[^<]*)<\/loc>/g)].map(m => m[1].replace(/^\/\/[^/]+/, ''));
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  let bad = 0;
  for (const u of paths) {
    const url = base + new URL(u, 'https://x').pathname;
    await p.goto(url);
    const w = await p.evaluate(() => document.documentElement.scrollWidth);
    if (w > 390) { bad++; console.log('OVERFLOW', w, url); }
  }
  await p.goto(base + '/'); await p.fill('#f-date', '2026-11-01'); await p.dispatchEvent('#f-date', 'change');
  const clear = await p.$$eval('#lake-clear-lake-pierce-county .flags li:not([hidden])', l => l.map(x => x.textContent));
  const ok = clear.some(t => t.includes('Outside the fishing season'));
  console.log(`${paths.length} pages checked; overflow: ${bad}; JS errors: ${errs.length}; date re-evaluation: ${ok ? 'ok' : 'FAILED'}`);
  await b.close();
  process.exit(bad || errs.length || !ok ? 1 : 0);
})();
