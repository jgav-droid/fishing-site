# Step 3: access-layer validation (validation only)

Can shore-fishing access facts (shore access, piers, parking, passes, fees,
hours, seasons, closures, rule sources) be sourced from official managers
for the 20 MVP waters, with provenance and a sustainable maintenance load?

Findings and verdict: `ACCESS_VALIDATION_REPORT.md`.

## Rebuild

Run from `validation/wdfw/`. Page caches live in the gitignored `out/access/`;
Step 2's `out/identity/` cache must exist.

```bash
python3 access/probes/spotcheck_identity.py
```

```bash
python3 access/probes/fetch_wdfw_gis_access.py
```

```bash
python3 access/probes/wdfw_access_sites.py
```

```bash
python3 access/probes/manager_pages.py
```

```bash
python3 access/build_access_dataset.py
```

```bash
python3 access/trip_decision.py --date 2026-10-31 --lakes wa-w-battle-ground-lake wa-w-klineline-pond wa-w-spanaway-lake wa-w-lake-bradley wa-w-ward-lake wa-w-clear-lake-pierce
```

```bash
python3 access/analyze.py
```

Optional template and monitoring tests:

```bash
python3 access/probes/wdfw_lake_access_fields.py
```

```bash
python3 access/probes/state_parks_template.py
```

```bash
python3 access/probes/change_detection.py
```

The builder also needs the shore-point join, which must run after
`fetch_wdfw_gis_access.py`:

```bash
python3 access/probes/wdfw_gis_shore_join.py
```

## Rules the data follows

- States are YES / NO / LIMITED / UNKNOWN. UNKNOWN never means NO; a NO needs
  an explicit official statement or field.
- Every value carries its source URL, a verbatim quote and the retrieval
  time. `build_access_dataset.py` fails if a quote is not found in the
  cached official page.
- Stocking events, fishing rules and physical access are separate facts. No
  record claims a lake is "open".
- Search engines were used only to find official URLs, never as a source of
  facts.
