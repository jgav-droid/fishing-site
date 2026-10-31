// Browser check of trip-finder URL state (needs Playwright + Chromium):
//   (cd mvp/dist && python3 -m http.server 8811) & node mvp/tests/url_state_check.js http://127.0.0.1:8811
const { chromium } = require('playwright');
(async () => {
  const base = process.argv[2] || 'http://127.0.0.1:8811';
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  const results = [];
  const check = (name, ok, detail) => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : ' :: ' + detail}`); };
  const path = () => { const u = new URL(p.url()); return u.pathname + u.hash; };
  const settle = () => p.waitForTimeout(500);

  await p.goto(base + '/'); await p.waitForTimeout(1200);
  check('clean URL on initial load', path() === '/', path());
  check('no automatic default-state hash', !p.url().includes('#'), p.url());

  await p.fill('#f-place', 'Tacoma'); await settle();
  check('changed location is shareable, defaults omitted', path() === '/#from=Tacoma', path());
  await p.selectOption('#f-max', '40'); await settle();
  check('two changes serialised, nothing else', path() === '/#from=Tacoma&max=40', path());
  await p.click('.more summary'); await p.selectOption('#f-dock', 'require'); await settle();
  check('more-filters change serialised', path() === '/#from=Tacoma&max=40&dock=require', path());

  await p.fill('#f-place', ''); await p.selectOption('#f-max', '25'); await p.selectOption('#f-dock', 'any'); await settle();
  check('resetting all to defaults removes the hash', path() === '/' && !p.url().includes('#'), p.url());

  await p.fill('#f-place', 'Olympia'); await p.selectOption('#f-max', '10'); await settle();
  await p.click('a.brand'); await settle();
  check('logo click returns to clean homepage', path() === '/', path());
  check('logo click clears finder state', (await p.inputValue('#f-place')) === '' && (await p.inputValue('#f-max')) === '25', 'fields not reset');
  await p.fill('#f-place', 'Seattle'); await settle();
  await p.click('nav a[href="/"]'); await settle();
  check('"Trip finder" nav link also resets', path() === '/' && (await p.inputValue('#f-place')) === '', path());

  await p.goto(base + '/#from=Tacoma&max=10&dock=require'); await p.waitForTimeout(800);
  check('shared URL restores place', (await p.inputValue('#f-place')) === 'Tacoma', await p.inputValue('#f-place'));
  check('shared URL restores max/dock', (await p.inputValue('#f-max')) === '10' && (await p.inputValue('#f-dock')) === 'require', 'not restored');
  check('shared URL left unchanged on load', path() === '/#from=Tacoma&max=10&dock=require', path());
  const status = await p.textContent('#f-status');
  check('shared URL applies the filters', status.includes('Tacoma') && status.includes('10 mi'), status);

  await p.goto(base + '/#from=&date=2026-10-31&max=25&shore=1&dock=any&hide=0'); await p.waitForTimeout(800);
  check('legacy full-default fragment restores defaults without rewriting', (await p.inputValue('#f-max')) === '25', path());

  await p.goto(base + '/lakes/ward-lake/'); await settle();
  await p.click('a.brand'); await settle();
  check('logo from a lake page goes to clean homepage', path() === '/', path());

  const canon = await p.getAttribute('link[rel=canonical]', 'href');
  check('canonical unaffected by finder state', /\/$/.test(canon) && !canon.includes('#'), canon);
  check('no JS errors', errs.length === 0, errs.join(' | '));
  await b.close();
  const failed = results.filter(x => !x).length;
  console.log(`${results.length - failed}/${results.length} URL-state checks passed`);
  process.exit(failed ? 1 : 0);
})();
