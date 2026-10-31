# WDFW stocking data: Step 1 technical validation report

Run: 2026-10-31, roughly 01:39–01:55 UTC. Run from a Claude Code cloud
container with open internet access. An earlier run on the same day was
blocked by the container's own egress policy; see "History" at the end.

All numbers below come from this run. Generated details are in
`RUN_RESULTS.md`, and the committed samples are in `samples/`.

## 1. Verdict: CONDITIONAL PASS (the core data works; the leftover issues are operational)

Every PASS criterion is met for **completed stocking events**:

- Official data is fetched programmatically from documented public
  endpoints. No token, cookies or user-agent tricks were needed, and nothing
  was bypassed.
- The schema is understandable: 26 columns, with dates, location, county,
  species, count, fish-per-pound, pounds, lifestage and facility.
- Current records are present: newest release 2026-10-27, 2,939 releases
  dated 2026, and 187 since Oct 1.
- Completed events can be told apart from plans because they come from
  different sources (section 7).
- Repeated reads were stable: 52 dataset requests and 47 HTML requests, all
  returning 200, with the same row count and schema throughout.
- Normalization was clean: 200 recent records, 0 row-level parse issues.
- A workable incremental strategy exists (section 8).

It is CONDITIONAL rather than PASS because of these open issues. None of
them blocks Step 2.

- **No stable record key.** The dataset is fully replaced on each refresh.
  All 109,527 rows share `:created_at` = `:updated_at` = 2026-10-29T16:30:43Z,
  so Socrata `:id` is not durable. Updates have to replace a date window
  rather than apply true deltas, and IDs have to be content hashes.
- **The plan source is a PDF only**, with month-level timing. Parsing it
  needs fragile layout-based extraction. This doesn't matter for
  completed-event features, but it does for any "coming soon" feature.
- **Rate limits are unpublished.** No rate-limit headers were exposed, and
  about 100 requests in total drew no throttling. Load at production
  frequency hasn't been tested, though the planned strategy needs only a
  handful of requests per day.
- The dataset publishes **no column descriptions**, so meanings come from
  column names and the cross-check with the HTML page.

## 2. Official endpoints tested

| # | Endpoint | Purpose |
|---|---|---|
| 1 | `https://data.wa.gov/api/views/6fex-3r7d.json` | metadata, schema, timestamps |
| 2 | `https://data.wa.gov/resource/6fex-3r7d.json` with SoQL `$select/$where/$order/$limit/$offset` | SODA 2 JSON API |
| 3 | `https://data.wa.gov/resource/6fex-3r7d.csv` with the same SoQL | SODA 2 CSV API |
| 4 | `https://data.wa.gov/api/views/6fex-3r7d/rows.csv?accessType=DOWNLOAD` | full bulk CSV |
| 5 | `https://data.wa.gov/api/views/6fex-3r7d/rows.json?accessType=DOWNLOAD` | bulk JSON v2 (capped read) |
| 6 | `https://data.wa.gov/api/v3/views/6fex-3r7d/query.json?accessType=DOWNLOAD` | bulk JSON v3, the URL from the brief (capped read) |
| 7 | `https://wdfw.wa.gov/fishing/reports/stocking/trout-plants/all` plus `?page=1..41` | current-year catchable plants (HTML) |
| 8 | `https://wdfw.wa.gov/fishing/reports/stocking/statewide` | statewide plan landing page (HTML) |
| 9 | `https://wdfw.wa.gov/publications/02693` → `https://wdfw.wa.gov/sites/default/files/publications/02693/wdfw02693.pdf` | the 2026 plan document |
| 10 | `https://catalog.data.gov/dataset/wdfw-fish-plants` | catalog (reachability only) |

## 3. HTTP and access results

| Endpoint | HTTP | Redirects | Content-Type | Size | Notes |
|---|---|---|---|---|---|
| metadata (1) | 200 | 0 | `application/json; charset=utf-8` | 46,278 B | |
| `count(*)` (2) | 200 | 0 | `application/json;charset=utf-8` | 17 B | `109527` |
| newest 200, JSON (2) | 200 | 0 | `application/json;charset=utf-8` | 156,699 B | includes `:id,:created_at,:updated_at,:version` |
| newest 200, CSV (3) | 200 | 0 | `text/csv; charset=UTF-8` | 52,292 B | header equals the API fieldNames |
| no `$limit` (2) | 200 | 0 | json | 639,565 B | **returns 1,000 rows, so pagination is required** |
| `$limit=50000` `$select=:id` (2) | 200 | 0 | json | 1,500,001 B | large pages work, in 0.7 s |
| bulk CSV (4), full | 200 | 0 | `text/csv; charset=utf-8` | **22,281,525 B** (4,648,157 B gzip) | 109,527 rows; ~1 s; `Content-Disposition: WDFW-Fish_Plants.csv`; no Content-Length (chunked) |
| bulk JSON v2 (5) | 200 | 0 | `application/json` | read capped at 2 MB | |
| bulk JSON v3 (6) | 200 | 0 | `application/json` | read capped at 2 MB | **worked without an app token** |
| HTML plants (7) | 200 ×42 pages plus repeats | 0 | `text/html; charset=utf-8` | ~135 KB per page | honest UA, no challenge markers, `cache-control: max-age=900` |
| HTML plan (8) | 200 | 0 | `text/html` | 40,719 B | |
| plan PDF (9) | 200 | 0 | `application/pdf` | 531,704 B | `Last-Modified: Wed, 04 Mar 2026 23:39:22 GMT` |
| catalog (10) | 200 | | `text/html` | | |

**Authentication:** none needed anywhere.

**Rate limiting:** no `X-RateLimit-*` or `Retry-After` headers on any
response. There were no 429s or 5xx responses in about 100 requests, which
included a full 42-page HTML crawl at 3-second intervals.

**Headers exposed by Socrata:**

- `Last-Modified` and `X-SODA2-Truth-Last-Modified`, both
  `Thu, 29 Oct 2026 16:30:43 GMT`
- `ETag`
- `X-SODA2-Fields` and `X-SODA2-Types`
- `X-SODA2-Data-Out-Of-Date: false`
- `X-Socrata-RequestId`
- `X-Socrata-Region: aws-us-east-1-fedramp-prod`

**Conditional GET results:**

- `If-Modified-Since` returns **304** on the API and on the bulk CSV.
- `If-None-Match` with the weak ETag returns 200, so it does not work for
  change detection.

**The earlier "403 from WDFW" finding did not reproduce.** All WDFW pages
returned 200 to a plainly labelled script user-agent. The earlier 403s
matched this container's own egress-proxy denial.

## 4. Dataset schema (actual, from the metadata endpoint)

Dataset name: "WDFW-Fish Plants". Description: "Fish Plant data".
Category: Natural Resources & Environment. Custom metadata: Posting
Frequency "Nightly", Period of Time "1995-Present". No row-identifier column
is declared (`rowIdentifierColumnId` is absent), and no column has a
description.

| fieldName | type | non-null / 109,527 | observed range or notes |
|---|---|---|---|
| `agency` | text | all | e.g. WDFW, "WDFW - ED COOPS", DOUG, SQAX, USFWS |
| `facility` | text | all | hatchery or facility, e.g. "VANCOUVER HATCHERY" |
| `release_year` | number | all | 1995–2026; always matches `release_start_date` |
| `release_month` | number | all | 1–12; always matches `release_start_date` |
| `release_start_date` | calendar_date | all | 1995-01-04 .. **2026-10-27** |
| `release_end_date` | calendar_date | all | 1995-01-05 .. 2026-10-27; differs from start on 11,565 rows |
| `release_location` | text | all | e.g. "BATTLE GROUND LK (CLAR)", "15 MILE CR   08.0207" |
| `county` | text | all present, but **10,804 blank** | padded with trailing spaces; 39 counties |
| `elevation` | number | **0** | always empty |
| `geo_code` | text | 108,154 | undocumented code, e.g. `L333`, `08.0207`; one `proposed-Tmp…` |
| `species_type` | text | all | `Trout/Kokanee` 70,224; `Salmon` 38,076; `Warmwater` 1,227 |
| `species` | text | all | e.g. Rainbow, Cutthroat, Brown Trout, Kokanee, Chinook |
| `run` | text | all | salmon run, or "NA" |
| `brood_year` | number | all | 1989–2026 |
| `origin` | text | 109,526 | e.g. HATCHERY, WILD, CAPTIVE BROOD |
| `stock` | text | 109,525 | broodstock name, e.g. "Goldendale" |
| `number_released` | number | all | 0 .. 11,545,821; 167 rows are 0 |
| `number_of_fish_per_pound` | number | all | 0 .. 999,999; 201 rows are 0 and 3 are ≥999,999 (sentinel?) |
| `total_pounds` | number | all | 0 .. 487,730; 4,865 rows are 0 |
| `lifestage` | text | 109,376 | e.g. Legals, Fry, Fingerling, Yearling, Adult |
| `cwt_code` | text | all | |
| `mark_code` | text | all | e.g. AD, UM, …+CWT |
| `number_marked_and_tagged` | **text** | 109,526 | numeric stored as text |
| `number_marked_only` | **text** | 109,526 | numeric stored as text |
| `number_tagged_only` | **text** | 109,526 | numeric stored as text |
| `number_neither_marked_or` | number | all | |

**Coverage against the fields you asked about:**

| Requested | Status |
|---|---|
| water/lake name | `release_location` |
| county | `county` (about 10% blank) |
| stocking date | `release_start_date` and `release_end_date` |
| species | `species` (and `species_type`) |
| quantity | `number_released` |
| size/weight | `number_of_fish_per_pound`, `total_pounds`, `lifestage` |
| hatchery/source | `facility` (also `stock`, `origin`) |
| latitude/longitude | **not present** |
| stable water identifier | **none documented**; `geo_code` may be one but is unverified |
| record identifier | **none**; only Socrata `:id`, which is regenerated on refresh |
| publication/update timestamp | metadata `rowsUpdatedAt` and the `Last-Modified` header |

The SODA 2 API and the bulk CSV are formatted differently:

| | SODA 2 API (`/resource/`) | bulk CSV (`rows.csv`) |
|---|---|---|
| column headers | fieldNames (`release_start_date`) | display names ("Release Start Date") |
| dates | ISO (`2026-10-27T00:00:00.000`) | `10/27/2026 12:00:00 AM` |

A parser has to target one of them explicitly.

## 5. Row count and date coverage

- **109,527 rows.** Measured four ways, all agreeing: `count(*)`, three
  repeated `count(*)` reads, the full bulk CSV, and `count(distinct :id)`.
- Date range is 1995-01-04 to 2026-10-27. Since 2015 there are about
  3,100–3,600 rows a year; 2026 has 2,939 so far.
- 2026 by month: Jan 46, Feb 118, Mar 453, Apr 921, May 699, Jun 232, Jul 100,
  Aug 75, Sep 108, Oct 187.
- 2026 by species type: Trout/Kokanee 1,873, Salmon 1,040, Warmwater 26.
  1,629 of the 2026 rows have LK/LAKE/POND in the location, across 609
  distinct locations.
- **0 rows are dated after today** in either date column.

## 6. Newest records found

From the API, ordered by `release_start_date DESC`:

| date | release_location | county | species | number | fish/lb | lifestage | facility |
|---|---|---|---|---|---|---|---|
| 2026-10-27 | BATTLE GROUND LK (CLAR) | Clark | Rainbow | 1,080 | 2.6 | Legals | VANCOUVER HATCHERY |
| 2026-10-27 | LACAMAS LK (CLAR) | Clark | Rainbow | 4,000 | 2.6 | Legals | VANCOUVER HATCHERY |
| 2026-10-26 | FRANKS POND (CHEL) | Chelan | Cutthroat | 3,385 | 75 | Fingerling | CHELAN HATCHERY |
| 2026-10-26 | WARD LK (THUR) | Thurston | Cutthroat | 306 | 1.6 | Yearling | EELLS SPRINGS |
| 2026-10-26 | GREEN LK (KING) | King | Brown Trout | 14,688 | 51 | Fry | KENDALL CR HATCHERY |
| 2026-10-26 | KLINELINE PD (CLAR) | Clark | Rainbow | 2,000 | 2.6 | Legals | VANCOUVER HATCHERY |

**Small recent-records query, as requested** (returns 187 rows):

`https://data.wa.gov/resource/6fex-3r7d.json?$where=release_start_date >= '2026-10-01'`

### Freshness

| Measure | Value |
|---|---|
| newest stocking date in the dataset | **2026-10-27**, 4 days before this run |
| `rowsUpdatedAt` / `Last-Modified` | **2026-10-29 16:30 UTC**, about 33 h before this run |
| `publicationDate` | 2023-08-30 (first publication, not a freshness signal) |
| `viewLastModified` | 2025-06-14 (metadata edit) |
| stated posting frequency | "Nightly" |
| refreshes observed | none between 10-29 16:30 and 10-31 01:55, so "Nightly" was not seen |
| current-year records present | yes |
| HTML current-year page newest date | **2026-10-27**, the same as the dataset |

The HTML `Last-Modified` header is the Drupal render time, not a data
timestamp.

### HTML page vs dataset: in sync, and the HTML is not fresher

The HTML plants page (`?page=0..41`) has 1,041 rows with columns
`Lake, Stock date, Species, Number, Fish per pound, Hatchery, Notes`. It
covers 2026-01-02 to 2026-10-27, and its species are Rainbow, Brown,
Cutthroat and Tiger trout. No lake-name matching was needed to compare it:

- The HTML `Lake` field is `<release_location> <County> - Region N`.
- All **890** (location, date) groups on the HTML page are explained by
  dataset rows:
  - 883 have identical totals;
  - 4 are a subset of the dataset rows for that location and date (the
    dataset also has fry or put-grow-take rows there);
  - 3 are sums of several same-size dataset rows, e.g. BEAR LK 3/11:
    709 + 2,292 = 3,001.
- The reverse does not hold. 128 dataset "Legals" groups in 2026 are not on
  the HTML page, mostly 4–5 fish/lb put-grow-take plants (Ford, Columbia
  Basin and Sherman Cr hatcheries).

**Conclusion:** the HTML page is a filtered, aggregated view of the same
underlying data. It is limited to catchable and jumbo trout, and
same-size rows are summed. It is **not** an independent or fresher source,
and the dataset is a superset of it. There is no reason to scrape it.

## 7. Completed vs planned stocking

| | Fish Plants dataset `6fex-3r7d` (and the HTML plants page derived from it) | Statewide plan |
|---|---|---|
| Form | API / CSV, 109,527 rows | 17-page **PDF** (Appendix A), linked from the HTML page; published March 2026 |
| Timing | exact day (`release_start_date`, `release_end_date`) | **month windows only**, e.g. "Mar-Apr, Dec". The PDF says: "Exact dates are not known at this time" |
| Numbers | exact counts (e.g. 1,080; 3,385) and pounds | round allotments (e.g. 10,500), in categories: Catchables, Put-Grow-Take, Jumbos, Triploids, Fry/Fingerlings |
| WDFW's own wording | the HTML page is for keeping "track of when catchables are stocked in real-time" (per the plan page) | "Stocking allotments and timing are subject to change without notice"; "based on information developed in the early part of the year" |
| Future-dated rows | **0** | the whole document is forward-looking at publication |

**Interpretation:**

- Treat **Fish Plants `6fex-3r7d` as historical, completed releases**
  (`record_kind = reported_plant`).
- Treat **the statewide plan PDF as planned, intended stocking**
  (`record_kind = planned_stocking`), with month-level timing and an
  explicit `plan_year` and `plan_published` date.

**Evidence that the two differ in practice:** the plan lists Lacamas Lake
catchables for "Mar-Apr, Dec" with 10,500 fish. The dataset records Lacamas
releases on 2026-03-03, 2026-04-01 and **2026-10-27**. The October release
falls outside every planned month. A product that showed the plan as
activity would mislead users.

**Remaining ambiguity:**

- The dataset has **no explicit status field**. "Completed" is inferred
  from:
  - the dataset's name ("Fish Plants");
  - having no future dates;
  - exact, non-round counts;
  - WDFW using the derived HTML page as its "stocked in real-time" report.
- We have not observed whether WDFW ever corrects or deletes past rows.
  The nightly full replace means it could do so silently.
- The plan PDF names lakes differently ("Lacamas Lake" vs
  "LACAMAS LK (CLAR)"). That matters only for Step 2.

**Data-model rule to preserve:**

- Store reported plants and plan entries in **separate tables**. Each record
  carries `record_kind`, `source_dataset` and `retrieved_at`.
- Plan entries never get a `stocking_date`, only `planned_months` and
  `plan_year`.
- The UI may say "stocked on <date>" only for `reported_plant`.

## 8. Incremental update strategy

What we found:

- `:created_at` and `:updated_at` are identical on all 109,527 rows and
  equal the last refresh time. **The dataset is wholly replaced on each
  refresh**, so `$where=:updated_at > last_run` returns every row (it
  returned 109,527) and `:id` can't be used as a key.
- `$where` on `release_start_date` works and is cheap. A query from
  2026-10-01 returned 187 rows.
- `If-Modified-Since` returns 304 when nothing has changed.
- The full gzipped export is 4.6 MB and takes about 1 s.

Recommended strategy:

1. **Change check, about hourly or nightly:** send `If-Modified-Since` to the
   `/resource/` endpoint, or compare metadata `rowsUpdatedAt`. On a 304,
   stop.
2. **On change:** fetch a rolling window with
   `$where=release_start_date >= today-N` (N around 60–120 days), paged with
   `$limit` and `$offset` (or one call, since `$limit=50000` works), ordered
   by `release_start_date, :id`. **Replace** every stored reported plant in
   that window with the fresh set. Don't apply deltas: there are no stable
   IDs, and late reports or corrections can land inside the window.
3. **Weekly or monthly full reconcile:** pull the 4.6 MB gzip export and
   diff it against the store to catch corrections older than the window.
4. **Record IDs:** a SHA-256 of all official columns, with a suffix for
   repeated identical rows. `normalize.py` already does this.

This is a reasonable, low-cost strategy, but it is window-replace, not true
incremental sync.

## 9. Data-quality problems found (full dataset unless noted)

- **1,146 exact duplicate rows** across 817 groups, where every column is
  identical. Examples: KLINELINE PD 2026-05-05 2,000 @ 2.2 appears twice;
  PALMER LK 2009-04-02. These might be separate truckloads or might be true
  duplicates; the source doesn't say. Don't dedupe silently.
- **County:**
  - blank on 10,804 rows (about 10%), and on 12 of the 200 recent rows;
  - padded with trailing spaces;
  - some locations span two counties, written in the name only, e.g.
    "ALDER LK (THUR/PIER)".
- `release_end_date < release_start_date` on 6 rows; the two dates differ on
  11,565 rows (multi-day releases).
- `number_released = 0` on 167 rows; `number_of_fish_per_pound = 0` on 201;
  `≥ 999,999` on 3 (sentinel?); `total_pounds = 0` on 4,865.
- `elevation` is empty on every row. The three marked/tagged count columns
  are stored as text.
- 22 `release_location` values contain a literal `?`, apparently lost
  characters (e.g. "SOUTHGATE CR  09?"). Location strings embed codes and
  abbreviations, e.g. "BEAVER LKS (KING) T24" and "15 MILE CR   08.0207",
  some with runs of spaces.
- No coordinates. `geo_code` is undocumented.
- The dataset mixes salmon, steelhead, fry and fingerling releases with
  catchable trout. For shore anglers, `lifestage` / `number_of_fish_per_pound`
  and `species_type` are the filter. The HTML page's view (catchable-size
  trout) shows WDFW applies a similar filter itself.
- The SODA API and the bulk CSV differ in header names and date formats
  (section 4).
- The recent sample normalized with **0** unparseable dates or quantities
  and **0** future dates (`samples/quality.json`).

## 10. Files (`validation/wdfw/`)

| File | Notes |
|---|---|
| `README.md` | how to run it |
| `VALIDATION_REPORT.md` | this report |
| `RUN_RESULTS.md` | generated from this run: every request, schema table, repeats |
| `_http.py` | logging GET helper |
| `fetch_dataset.py` | dataset probe |
| `fetch_html.py` | HTML probe (pager now bounded by the last pager link) |
| `normalize.py` | normalizer and quality checks (content-hash IDs, end date, `official_extra`) |
| `report.py` | builds `RUN_RESULTS.md` |
| `field_map.json` | filled from the real schema |
| `samples/schema_6fex-3r7d.json` | the real schema |
| `samples/raw_sample.json`, `samples/raw_sample.csv` | newest 200 rows, verbatim from the API |
| `samples/normalized_sample.json` | 200 normalized records |
| `samples/quality.json` | quality-check output |
| `samples/html_plants_sample.json` | first 200 of the 1,041 HTML rows |
| `samples/plan_2026_excerpt.txt` | verbatim first 60 lines of the plan PDF text |

Not committed (gitignored `out/`): the 22 MB full export, the full HTML
crawl, the plan PDF, and the request logs.

## 11. Commands and tests run

```bash
curl -sS -o /dev/null -w "%{http_code} %{content_type}\n" https://data.wa.gov/api/views/6fex-3r7d.json
```

```bash
cd validation/wdfw && python3 fetch_dataset.py --sample 200 --repeat 3
```

```bash
python3 fetch_dataset.py --date-field release_start_date --sample 200 --repeat 3 --full-bulk
```

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -H "If-Modified-Since: Thu, 29 Oct 2026 16:30:43 GMT" "https://data.wa.gov/resource/6fex-3r7d.json?\$select=count(*)%20as%20n"
```

Also run:

- curl with `If-None-Match` (returned 200).
- curl with `If-Modified-Since` on `rows.csv` (returned 304).
- curl for gzip `rows.csv` (4,648,157 B).
- curl for `$select=min(:created_at),max(:created_at),count(distinct :id)`.
- curl for `$limit=50000`.
- `python3 fetch_html.py --max-pages 60 --delay 3 --repeat 2`, which
  fetched 42 pages, all 200, then 2× repeats of each page, all 200.
- curl for the plan landing page, the publication page and the PDF, then
  `pdfinfo` and `pdftotext -layout`.
- One-off Python profiling of `out/full_export.csv` for duplicates, blanks,
  sentinels, year-month consistency and per-year/month counts.
- The HTML↔dataset reconciliation on (location, date) totals.
- `python3 normalize.py --propose` → field map reviewed and filled →
  `python3 normalize.py` (200 records, 0 issues) → `python3 report.py`.

Request tally: 52 logged dataset requests, all 200, and 47 HTML attempts,
all 200. Rows were stable across all six repeated reads at 109,527, with the
same column hash `9f66c1ef9c7a294c` and the same `rowsUpdatedAt`.

## 12. Unresolved risks

- **No refresh was observed during the session.** Whether rows keep the
  same content across refreshes, whether past rows get corrected, and
  whether "Nightly" is real (the last refresh was about 33 h earlier) all
  need a multi-day watch. That means running `fetch_dataset.py` daily for
  about a week and diffing content hashes.
- **Reporting lag.** The newest release was 2–4 days old at retrieval.
  Whether stockings on Oct 28–30 were still to be reported is unknown. That
  lag bounds how "recent" the product can claim to be.
- **Throttling** behaviour without an app token is undocumented here. A free
  Socrata app token is an easy mitigation to register before production.
- **Duplicate rows:** we don't know whether they are real repeat releases.
- **Plan data** exists only as a PDF and would need layout parsing. The
  format may change from year to year.
- **`geo_code` semantics:** unknown whether it is a stable water ID; that
  matters for Step 2.
- **Blank counties:** about 10% are blank, so county has to be derived from
  location for those rows. That is a Step 2 concern.

## 13. Recommendation: proceed to Step 2

Build on the Fish Plants dataset (`6fex-3r7d`) via the SODA API, using the
window-replace and content-hash approach. Treat the HTML plants page as
redundant, and keep the plan PDF as a separate, optional, planned-only
source.

Before or during Step 2:

- start a daily `fetch_dataset.py` run for about a week to confirm refresh
  cadence and row stability;
- register a Socrata app token.

## History

An earlier run on the same date, from the same container under a restricted
network policy, was refused by the container's egress proxy (CONNECT 403)
for `data.wa.gov`, `wdfw.wa.gov` and `catalog.data.gov`. Once network access
was opened, every endpoint returned 200. The 403 seen in earlier research is
best explained by the same kind of sandbox restriction, not by WDFW.
