# Launch checklist (manual steps remaining)

## Decisions

1. **Martha Lake:** confirm the MVP lake is Martha Lake in **Lynnwood** (WDFW
   "Martha Alderwood Manor"), not the Warm Beach "Lake Martha". The site
   currently publishes the Lynnwood lake as `/lakes/martha-lake-lynnwood/`.
2. **Site name and domain:** "Washington Stocked Lake Finder" is a
   placeholder. Pick a domain.
3. **Pass/fee wording:** the site shows "Not stated by <manager>" at Green,
   Angle, Meridian (city park), Long's Pond and Bradley. Optional: email those
   five park departments and add any confirmed answers to the access facts,
   with the email as provenance.

## Configuration (`mvp/config.json`)

1. Set `base_url` to the real `https://` domain. The production build refuses
   the placeholder.
2. Set `contact_email` for corrections. The production build refuses it if
   empty.
3. Optional: set `ga4_measurement_id`. Tracked events are `trip_search`,
   `lake_result_click`, `source_click` and `alternative_click`.
4. Optional: set `google_site_verification`, or verify Search Console by DNS
   instead.

## Hosting (GitHub Pages via `.github/workflows/mvp-site.yml`)

1. Merge to the default branch. Scheduled workflows only run there.
2. Repo Settings → Pages → Source: **GitHub Actions**. Add the custom domain
   and enforce HTTPS.
3. Repo Settings → Variables: `MVP_PRODUCTION = true`. Until then builds are
   `noindex` and robots.txt disallows crawling.
4. Allow the workflow to push data commits (Settings → Actions → Workflow
   permissions: read and write), or switch the persist step to an artifact
   or cache.
5. Run the workflow once by hand (`workflow_dispatch`). Check the log: tests
   pass, every source status is `ok`, and the build reports no stale sources.

## Before announcing

1. Human spot-check of the 20 lake pages against their official links,
   especially:
   - the shore YES/LIMITED states;
   - the Kapowsin dock conflict;
   - the Meridian ramp fee conflict;
   - the Spanaway closure dates.
2. Open `/data-quality/` and clear or acknowledge every review item.
3. Run the phone check (`mvp/tests/mobile_check.js`) on the deployed URL.
4. Search Console: add the property, submit `/sitemap.xml`, and use URL
   Inspection on `/` and two lake pages.
5. Check `/robots.txt` shows `Allow: /` and that pages no longer carry
   `noindex`.

## After launch (weekly, about 1.3 h/week at this scale)

- **Review queue:** changed or unreachable official pages, unmapped stocking
  names, advisory name matches.
- **Dated notices:**
  - Spanaway's closure ends Jan 11, 2027, after which the notice drops off
    automatically.
  - Re-check Angle Lake's ramp/pier notice, which has no end date.
- **Calibration:** measure the actual change-review time over 4–6 weeks.
  Don't expand past 20 lakes until it's known.
- **Monitor task:** disable the one-week Step 1 monitor scheduled task ("WDFW
  stocking daily monitor (1 week)") once it reports completion.
