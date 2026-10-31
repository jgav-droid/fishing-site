# WDFW stocking-data validation (Step 1 only)

Isolated technical check of whether Washington fish-stocking data can be
fetched and normalized from official sources. No site, UI or production
code lives here.

**Step 1 status (2026-10-31): CONDITIONAL PASS.** Run with open internet access.
See `VALIDATION_REPORT.md` for the verdict and findings, and `RUN_RESULTS.md`
for every request made.

## Later steps in this folder

- **Step 2, canonical water identity:** `identity/`. Start with
  `identity/IDENTITY_VALIDATION_REPORT.md` (verdict: CONDITIONAL PASS) and
  `identity/README.md` (how to run it).
- **Step 3, access layer:** `access/`. Start with
  `access/ACCESS_VALIDATION_REPORT.md` (verdict: CONDITIONAL PASS) and
  `access/trip_decisions.txt` (example trip-decision records).
- **Daily Step 1 monitor (one week):** `monitor/daily_snapshot.py` writes
  `monitor/snapshots/<date>.json` and appends to `monitor/MONITOR_LOG.md`.
  It observes refresh frequency, regenerated row IDs, corrections and
  reporting lag. A scheduled cloud task runs it daily at 14:13 Pacific.

## Files

| file | purpose |
|---|---|
| `_http.py` | stdlib GET helper; logs status, redirects, content type, size, headers (rate limit, Socrata, caching) |
| `fetch_dataset.py` | probes dataset `6fex-3r7d`: metadata/schema, `count(*)`, date coverage, newest-N JSON + CSV sample, paging, incremental queries, capped bulk exports, repeated reads |
| `fetch_html.py` | probes the two WDFW HTML pages (current-year plants, statewide plan); extracts tables generically |
| `normalize.py` | applies `field_map.json` to `samples/raw_sample.json` → `samples/normalized_sample.json` + `samples/quality.json` |
| `field_map.json` | official fieldName → normalized key, reviewed against the real schema |
| `report.py` | renders `RUN_RESULTS.md` (facts only) from the probe outputs |
| `RUN_RESULTS.md` | generated from the latest run |
| `VALIDATION_REPORT.md` | human-written findings and verdict |
| `out/` | full logs and optional full export (gitignored) |
| `samples/` | schema, newest-200 raw sample (JSON + CSV), normalized sample, quality checks, HTML sample, plan PDF excerpt |

Requirements: Python 3.9+, standard library only.

## Run

```bash
cd validation/wdfw
```

The dataset has two date columns (`release_start_date`, `release_end_date`), so name the stocking-date column explicitly:

```bash
python3 fetch_dataset.py --date-field release_start_date --sample 200 --repeat 3
```

```bash
python3 fetch_html.py --max-pages 60 --repeat 2
```

```bash
python3 normalize.py --propose
```

Review `field_map.proposed.json` against the column descriptions in
`samples/schema_6fex-3r7d.json`. Fill `field_map.json` with real `fieldName`s
only, or `null`, and set `_record_kind`. Then run:

```bash
python3 normalize.py
```

```bash
python3 report.py
```

Optional, to measure the full bulk export (writes to `out/`, not committed):

```bash
python3 fetch_dataset.py --full-bulk
```

## Ground rules the scripts follow

- Only documented public endpoints; no app token, cookies or auth.
- An honest User-Agent. The HTML probe makes one comparison request with a
  normal browser UA if the first is refused. There is no challenge solving
  and no proxy rotation.
- `normalize.py` refuses mappings that reference columns not in the official
  schema, and leaves unmapped fields out instead of inferring them.
- Planned stockings and reported plants are never combined. Each normalized
  record carries `record_kind` and `source_dataset`.

`WDFW_TEST_BASE` overrides the base URL. It exists only to smoke-test the
scripts against a local mock; never set it for a real run.
