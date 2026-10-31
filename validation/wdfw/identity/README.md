# Step 2: canonical water identity (validation only)

Can raw `6fex-3r7d` stocking rows be attached to the right real-world water
and its official WDFW page, without silent wrong matches?

Findings and verdict: `IDENTITY_VALIDATION_REPORT.md`.

## Pipeline

All scripts are Python 3 standard library only. Run from
`validation/wdfw/identity/`. Large inputs and outputs go to the gitignored
`../out/identity/`.

| step | script | output |
|---|---|---|
| 1 | `python3 build_inventory.py` (needs `../out/full_export.csv` from Step 1: `python3 ../fetch_dataset.py --date-field release_start_date --full-bulk`) | `stocking_locations.json`, `geo_code_profile.json`, `county_suffix_map.json` |
| 2 | `python3 fetch_official_lakes.py --delay 1.5` (crawls about 756 WDFW pages, cached; about 25–35 min the first time) | `official_lowland_lakes.json`, `gis_lowland_lakes.json`, `gis_high_lakes.json` |
| 3 | `python3 match.py` | `matches.json`, `entities.json` |
| 4 | `python3 audit.py` | `audit_results.json` (committed) |
| 5 | `python3 export_samples.py` | committed samples in `samples/` |

`validation_sample.json` holds the hand-labelled ground truth for the audit.
Each item records its `truth_basis`, meaning the official evidence the label
rests on.

## Evidence levels used by `match.py`

| level | meaning | automated? |
|---|---|---|
| A | exact normalized name, county agrees, exactly one official entity with that name in the county, **and** the stocking `geo_code` equals the entity's official Geo Code, with no other water sharing the code | yes |
| B | stocking `geo_code` equals the official Geo Code (WDFW's own lake page uses this key to list "fish plants in this lake"), the code is not shared by another water, the county agrees, the entity is unique, and the names agree after a listed alias rule (word order, generic word omitted, spacing, `@ site` on the same water) | yes |
| C | exactly one plausible entity, but weaker evidence | **no, human review** |
| D | ambiguous or conflicting: several same-name waters, missing county, shared or contradictory codes | **no, human review** |
| NONE | no official entity found (mostly streams and rivers, plus waters that have no WDFW page) | no |

Nothing is ever promoted from C or D automatically.

## Politeness

`fetch_official_lakes.py` makes ordinary GETs with an honest User-Agent,
waits 1.5 s between requests, and caches every page so later runs refetch
nothing. `robots.txt` allows `/fishing/locations/`. Lake pages embed WDFW's
own Socrata app token in `drupalSettings`; it is **not** used.
