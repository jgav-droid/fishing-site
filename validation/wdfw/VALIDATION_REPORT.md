# WDFW stocking data — Step 1 technical validation report

Run date: 2026-10-31 (UTC). Run from a Claude Code cloud sandbox.

## 1. Verdict: NOT DETERMINED (no PASS / CONDITIONAL PASS / FAIL can honestly be assigned yet)

No byte of official WDFW or data.wa.gov data was retrieved in this session.
Every request was refused by **this sandbox's own egress proxy**, at the
`CONNECT` stage, before it reached Washington's servers:

```
> CONNECT data.wa.gov:443 HTTP/1.1
< HTTP/1.1 403 Forbidden            <- local policy proxy, not data.wa.gov
curl: (56) CONNECT tunnel failed, response 403
```

The proxy's status endpoint lists each attempt as `connect_rejected`, "gateway
answered 403 to CONNECT (policy denial)". The hosts were `data.wa.gov:443`,
`wdfw.wa.gov:443` and `catalog.data.gov:443`. A control request to
`github.com` went through. A separate fetch tool reported `ENOTFOUND` for
`data.wa.gov`, meaning the host is outside the session's allowed domains.

- **Not a PASS or CONDITIONAL PASS:** both need the core dataset to be shown
  working, and it has not been.
- **Not a FAIL:** FAIL means the *official source* cannot be used. Nothing
  here shows that. The block is in our test environment.
- **About the earlier research:** it reported "HTTP 403 from WDFW pages". The
  same signature showed up here, and here it came from the sandbox proxy. The
  earlier 403s should not be counted as evidence that WDFW blocks automated
  access until they are reproduced from an unrestricted network.

## 2. Official endpoints (prepared and attempted)

| key | URL | result here |
|---|---|---|
| metadata / schema | `https://data.wa.gov/api/views/6fex-3r7d.json` | egress proxy denied |
| SODA JSON | `https://data.wa.gov/resource/6fex-3r7d.json` (+ `$select/$where/$order/$limit/$offset`) | not reached (script stops when metadata fails) |
| SODA CSV | `https://data.wa.gov/resource/6fex-3r7d.csv` | earlier manual curl: egress proxy denied |
| bulk CSV | `https://data.wa.gov/api/views/6fex-3r7d/rows.csv?accessType=DOWNLOAD` | not reached |
| bulk JSON v2 | `https://data.wa.gov/api/views/6fex-3r7d/rows.json?accessType=DOWNLOAD` | not reached |
| bulk JSON v3 (from brief) | `https://data.wa.gov/api/v3/views/6fex-3r7d/query.json?accessType=DOWNLOAD` | not reached |
| catalog | `https://catalog.data.gov/dataset/wdfw-fish-plants` | egress proxy denied |
| current-year plants (HTML) | `https://wdfw.wa.gov/fishing/reports/stocking/trout-plants/all` | egress proxy denied (honest UA and browser UA, ×2) |
| statewide plan (HTML) | `https://wdfw.wa.gov/fishing/reports/stocking/statewide` | egress proxy denied (honest UA and browser UA, ×2) |

## 3. HTTP/access results

Every attempt ended with `egress_proxy_denied` ("Tunnel connection failed:
403 Forbidden"): 0 bytes, no destination headers, no redirects, about 0.2 s.
Nothing could be observed about WDFW's own status codes, content types,
payload sizes, pagination, auth or rate-limit headers. The full log is in
`out/probe_log.jsonl` (gitignored), and a summary is in `RUN_RESULTS.md`.

## 4. Dataset schema: not retrieved

No field names are reported. Listing them from memory or from secondary
descriptions would break the brief's "do not invent fields" rule.
`fetch_dataset.py` writes the real column list, with `fieldName`, display
name, type, description and cached min/max/non-null counts, to
`samples/schema_6fex-3r7d.json`. `field_map.json` is left deliberately empty.

## 5–6. Row count, date coverage, newest records: not retrieved

The script collects these with `count(*)`, plus `min`/`max`/`count` for every
date-typed column, plus a count of rows dated after today, plus the newest 200
rows ordered by the stocking-date column.

## 7. Completed vs planned: not verified from data

Working hypothesis, which **has not been confirmed**:

- Fish Plants (`6fex-3r7d`) and the "trout-plants/all" page hold reported or
  completed plants.
- The "statewide" page holds the annual plan of intended stockings.

The harness tests this as follows:

- `fetch_dataset.py` counts dataset rows dated after today
  (`date_coverage.*.rows_after_today`). Any such rows would mean the dataset
  is not purely completed events.
- `normalize.py` flags future-dated records relative to `retrieved_at`.
- `fetch_html.py` saves the plan page's table headers. If it is laid out by
  month or season with target counts and no event dates, that is structural
  evidence it is a plan.

Data-model rule, regardless of how this turns out: keep plan and plant
records in separate tables or collections. Every record carries
`record_kind` (`reported_plant` or `planned_stocking`) and `source_dataset`,
and the UI must never present a `planned_stocking` as having happened.
`normalize.py` refuses to run until `_record_kind` is set on purpose.

## 8. Incremental update strategy: designed, not proven

Candidate strategies, each tested by `fetch_dataset.py`:

1. **Change detection:** poll `api/views/6fex-3r7d.json` and compare
   `rowsUpdatedAt`. If it hasn't changed, skip the run.
2. **Window query:** `$where=<stocking_date> >= '<today-30d>'`, re-fetched
   over a rolling window, with upserts on the source record id. This copes
   with late-reported and corrected rows.
3. **System-field delta:** `$where=:updated_at >= '<last_run>'`. This works
   only if WDFW updates rows in place. A full-replace publishing process would
   reset every `:updated_at` and `:id`, and the script measures the
   `:updated_at` range to show which applies.
4. **Fallback:** periodic full bulk CSV with diffing. Its size is measured
   with `--full-bulk`.

Open question: whether the dataset has a stable business key. The script
reports `rowIdentifierColumnId`. Without one, Socrata `:id` is the only id
and may not survive a full republish.

## 9. Data-quality problems: none can be reported (no data)

Checks implemented in `normalize.py`:

- unparseable dates and quantities
- nulls per field
- future-dated rows
- zero or negative counts
- duplicate ids and duplicate content
- the set of species and county values
- water names containing codes or parentheticals, which feed later name
  matching

## 10. Files created (all under `validation/wdfw/`)

- `README.md`
- `VALIDATION_REPORT.md`
- `RUN_RESULTS.md` (generated; shows the blocked run)
- `_http.py`
- `fetch_dataset.py`
- `fetch_html.py`
- `normalize.py`
- `report.py`
- `field_map.json`
- `.gitignore`

No raw or normalized sample is committed, because no official data was
obtained. No synthetic data is committed either.

## 11. Commands and tests run

```bash
curl -sS -D - "https://data.wa.gov/api/views/6fex-3r7d.json"
curl -sS -D - "https://data.wa.gov/resource/6fex-3r7d.json?\$limit=5"
curl -sS -D - "https://data.wa.gov/resource/6fex-3r7d.csv?\$limit=5"
curl -sS -v https://data.wa.gov/
curl -sS https://catalog.data.gov/dataset/wdfw-fish-plants
curl -sS https://wdfw.wa.gov/
curl -sS https://github.com
curl -sS http://127.0.0.1:43121/__agentproxy/status
python3 fetch_dataset.py
python3 fetch_html.py --repeat 1 --delay 1
python3 report.py
```

Results:

- **All curl requests to WDFW and data.gov hosts:** CONNECT 403 from the
  sandbox proxy.
- **`github.com` control request:** reached the server, which answered 400.
- **Proxy status endpoint:** recorded each attempt as a policy denial.
- **`fetch_dataset.py`:** exited 2 because the metadata request was denied.
- **`fetch_html.py`:** recorded the denials and exited 0.
- **`report.py`:** wrote `RUN_RESULTS.md`.

**Script smoke test (code check only, not evidence about WDFW):** I ran the
whole pipeline against a throwaway local mock server with obviously fake
columns, kept outside the repo. It went: `fetch_dataset.py --repeat 2` →
`fetch_html.py` → `normalize.py --propose` → `normalize.py` → `report.py`.
All steps ran and normalized 200 mock rows. Offset paging gave 100 + 100 rows
with 0 overlap, and the CSV header matched the schema.

## 12. Unresolved risks: all of the original Step 1 questions, plus these

- Whether WDFW really answers ordinary scripted requests with 200, or puts a
  WAF or bot challenge in front of `wdfw.wa.gov`. The earlier 403s are
  unexplained until rerun from an open network.
- Whether the v3 `query.json` export needs an app token. If it does, use the
  SODA 2 `/resource/` endpoint or `rows.csv` instead.
- Whether the dataset is current. The newest stocking date and
  `rowsUpdatedAt` against today (2026-10-31) are unknown.
- Whether a stable record or water identifier exists.
- Plan vs completed semantics (section 7).
- Rate limits for anonymous SODA use. Socrata documents throttling for
  requests without a token; the headers are unobserved.

## 13. Recommendation: fix the ingestion-environment issue first, then rerun Step 1

Do not proceed to Step 2, and do not kill the idea. Nothing about the source
has been disproven. Either:

- allow `data.wa.gov` and `wdfw.wa.gov` (and optionally `catalog.data.gov`)
  in this cloud environment's network settings, under Network access →
  Allowed domains (https://code.claude.com/docs/en/cloud-environments#network-access),
  then rerun; or
- run the commands in `README.md` on any normal internet connection and
  commit `samples/` and `RUN_RESULTS.md`.

The verdict can then be assigned from real evidence. That takes about five
minutes of runtime.
