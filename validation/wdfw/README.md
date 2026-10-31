# WDFW stocking-data validation (Step 1 only)

Isolated technical check of whether Washington fish-stocking data can be
fetched and normalized from official sources. No site, UI or production
code lives here.

**Current status: blocked, not yet validated.** See `VALIDATION_REPORT.md`.
The session that wrote these scripts could not reach `data.wa.gov` or
`wdfw.wa.gov` because of its own sandbox network policy. These scripts are
ready to run from any machine with normal internet access.

## Files

| file | purpose |
|---|---|
| `_http.py` | stdlib GET helper; logs status, redirects, content type, size, headers (rate limit, Socrata, caching) |
| `fetch_dataset.py` | probes dataset `6fex-3r7d`: metadata/schema, `count(*)`, date coverage, newest-N JSON + CSV sample, paging, incremental queries, capped bulk exports, repeated reads |
| `fetch_html.py` | probes the two WDFW HTML pages (current-year plants, statewide plan); extracts tables generically |
| `normalize.py` | applies `field_map.json` to `samples/raw_sample.json` → `samples/normalized_sample.json` + `samples/quality.json` |
| `field_map.json` | official fieldName → normalized key. **Empty until the real schema is retrieved** |
| `report.py` | renders `RUN_RESULTS.md` (facts only) from the probe outputs |
| `RUN_RESULTS.md` | generated; currently shows the blocked run |
| `VALIDATION_REPORT.md` | human-written findings and verdict |
| `out/` | full logs and optional full export (gitignored) |
| `samples/` | small committed samples (created by a successful run) |

Requirements: Python 3.9+, standard library only.

## Run

```bash
cd validation/wdfw
```

```bash
python3 fetch_dataset.py --sample 200 --repeat 3
```

If more than one date-typed column exists, the script says so. Re-run it with the stocking-date column named explicitly:

```bash
python3 fetch_dataset.py --date-field <fieldName> --sample 200 --repeat 3
```

```bash
python3 fetch_html.py --max-pages 3 --repeat 2
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
