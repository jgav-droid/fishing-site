# Step 2: canonical water identity, validation report

Run: 2026-10-31 UTC. Inputs: the Step 1 full export of `6fex-3r7d`
(109,527 rows, rowsUpdatedAt 2026-10-29) and the official WDFW sources
crawled the same day. The numbers below come from `audit_results.json`,
`samples/match_summary.json` and `samples/geo_code_profile.json`.

## 1. Verdict: CONDITIONAL PASS

| PASS criterion | Result |
|---|---|
| 20/20 MVP waters matched correctly | **18/20 automatically and correctly**. 2 were routed to human review with the correct lake as the only or listed candidate: the "Martha Lake (Snohomish)" item, which is two official lakes, and Long's Pond. **0 wrong.** |
| 0 false confident matches in the audited sample | **0 / 83 items**, and 0 among the 44 automated (A/B) matches, including 20 randomly drawn automated matches |
| ≥ 90% matched correctly automatically or safely routed to review | **100%** (83/83) |
| Ambiguous same-name waters not silently merged | Met. Every collision is kept as a separate entity or alias; shared or contradictory codes force review |
| Durable canonical key independent of stocking row IDs | Met. Use a minted internal ID, keyed by the WDFW page slug and Geo Code; aliases are keyed by the stable `release_location` string |
| Official entity URLs and identifiers can be stored | Met. Page URL, slug, Geo Code, county, centre lat/lon; GIS GeometryID / FishWAid for high lakes |
| Matching repeatable on new records | Met. Deterministic rules plus a stored alias table (section 11) |

Why it is CONDITIONAL and not PASS:

- **Not every MVP water matches automatically.** 2 of 20 need a one-time
  human decision, caused by defects in WDFW's own codes (section 2).
- **There is a meaningful review load beyond the MVP:**
  - 40% of the deliberately hard 83-item sample went to review;
  - statewide, for 2026 catchable-size trout plants, 60 distinct locations
    (17% of rows) need a one-time review.
- **There is an official-source gap.** 64 waters stocked in 2026 carry a
  lake code but have **no** WDFW lowland page and no GIS high-lake entry
  (e.g. Bonaparte Lake `L238`, Molson Lake `L3139`). They have no official
  URL or coordinates to link to.

## 2. What `geo_code` represents

**It is undocumented.** In the `6fex-3r7d` metadata the column's description
is empty and there are no attachments. The dataset description is just "Fish
Plant data". No other data.wa.gov dataset has the field: I searched the
Socrata catalog for "WDFW", "geo code", "fish plants" and "stocking".

What I found it does:

- **WDFW's own lake pages use it as the join key.** Each lowland-lake page
  shows "Geo Code: L333". Its script queries `6fex-3r7d` with
  `where geo_code = "<page Geo Code>"` (and, on lowland pages, also
  `number_of_fish_per_pound <= 3.0`) to fill the "fish plants in this lake"
  table. The script is `drupalSettings.wdfwSocrataTable.geo_id` in the page
  plus the site JS bundle.
- **The same namespace appears in an independent official dataset.** WDFW
  GIS `FishWA_2014_AllLakes_PROD` layer 21 (High Lakes) uses `L…` codes as
  `GeometryID`. 796 of its 1,080 GeometryIDs appear as stocking geo_codes,
  and 112 equal a lowland-page Geo Code.
- **Inferred, not documented:**
  - the `L<digits>` codes are WDFW lake IDs;
  - the `NN.NNNN` codes (973 distinct) have the form of Washington
    stream-catalog numbers (WRIA.stream);
  - there are also `G…`, `P…` and free-text values, e.g.
    `10.0600@rm0toL2668inlet`, `proposed-Tmp20200707i`, a comma list of three
    codes, and a coordinate pair.

| Measure | Value |
|---|---|
| distinct geo_codes | **2,987** (1,781 `L…`, 973 `NN.NNNN`, 16 `G…`, 217 other) |
| null/blank rate | **1.25%** (1,373 rows) |
| codes mapping to more than one normalized location name | **76** |
| normalized names mapping to more than one code | **0** (each name carries one code across 1995–2026) |
| codes spanning more than one non-blank county | 10 |
| official lowland pages: Geo Code unique per page | yes, 704 L-codes on 710 pages; 6 pages have none |
| official page codes found in stocking | 624 / 705 |

### Should geo_code be the identity key?

**Use it as strong evidence, never as the sole identity key.**

Evidence for:

- WDFW uses it operationally.
- It is unique per official page.
- It is perfectly stable per name over 30 years. That suggests a lookup
  applied at export time. It also means WDFW could change it everywhere at
  once, which the daily monitor will watch.

Evidence against (these are errors in the source, not in our matching):

| Code | What it covers | Why it's a problem |
|---|---|---|
| `L2818` | `LONGS PD (THUR)` and `LONG LK (THUR)` (286 rows) | Two different waters. Long Lake's own page code `L2807` is used only by "LACEY DERBY". **WDFW's Long's Pond page therefore lists Long Lake's plants.** |
| page `L3218`, stocking `L3219` | "Lake Martha (Snohomish)" page vs `MARTHA LK (WB) (SNOH)` rows | **No stocking row carries `L3218`**, so that official page's plants table cannot match these plants. |
| `L3991` | Silver Lake (Jefferson) and Silver Lake (Mason) | different counties |
| `L3724` | Beaver Lake (Snohomish) and Quail Lake (Adams) | different counties |
| `L1060` | Deer Lake (Lincoln) and Deer Springs Lake | |
| `L1009` | Duck Lake ponds (1)/(2)/(3)/(22) | |
| `L4475` | Twin Lakes (1) and Little Twin Lake | |

So a plain geo_code join, which is what WDFW's own pages do, would attach
some stocking to the wrong lake.

## 3. Official canonical-water source

| Source | Use | Exposes |
|---|---|---|
| **WDFW lowland-lake pages**: listing `https://wdfw.wa.gov/fishing/locations/lowland-lakes?name=&page=0..35` (Drupal view, 720 rows) and profile `https://wdfw.wa.gov/fishing/locations/lowland-lakes/<slug>` | **primary canonical entity** | name, page slug (stable URL), county or counties, acres, elevation, **Geo Code**, centre lat/lon (697/710), species list |
| WDFW GIS `https://geodataservices.wdfw.wa.gov/arcgis/rest/services/ApplicationServices/FishWA_2014_AllLakes_PROD/MapServer/21` (High Lakes; structured REST JSON, no token) | secondary entities (968 after merging codes that duplicate a lowland page) | `GeometryID` (L-code), `FishWAid`, name, county, lat/lon, species list; `WebsiteURL` mostly blank |
| same service, layer 2 (Lowland Lakes, 653 features) | corroboration only | name, county, point. No code, and `WebsiteURL` is blank on all 653. It can only be joined by name, county and coordinates |
| data.wa.gov `nbd2-vdmz` (WDFW Creel Water Bodies, 199 rows) | not used | GUID, LLID, centroid. A different ID system, not linkable to geo_code |

**No JSON API was found** (`/jsonapi` returns 404, `?_format=json` returns 406), so the lowland pages
are crawled as HTML:

- 756 requests at 1.5 s intervals with an honest User-Agent, all cached;
  `robots.txt` allows the path.
- 0 failures.
- The page parser reads labelled fields (`<strong>Geo Code:</strong>`) and
  `drupalSettings`. That is less fragile than layout scraping, but it is
  still HTML.
- Multi-county lakes appear once per county under a single slug (Carney
  Lake, Franklin Roosevelt Lake ×5, Banks Lake, Lake Merwin and others), so
  entities are **deduplicated by slug** and carry a county set.
- WDFW's Socrata app token is embedded in the pages. It was **not used**.

## 4. Stocking-location inventory (`build_inventory.py`)

| Measure | Value |
|---|---|
| distinct raw `release_location` | **3,314** |
| after basic normalization (case and whitespace) | **3,314** (no raw variants collapse) |
| in more than one non-blank county | 5 |
| with any blank-county rows | 256; **233 have no county at all**; 3 of those recover a county from the name suffix |
| with obvious encoding issues | 1 location (`SOUTHGATE CR 09?`, 22 rows) |
| in potential naming-collision groups (same name once the county suffix is removed) | **323 locations in 121 groups** (largest: LONG LK 9, CLEAR LK 8, DEER LK 8, HORSESHOE LK 8) |
| with a 4-letter county suffix "(CLAR)" | 2,035. Suffix → county mapping learned from data: 38 codes, each ≥ 99.86% consistent |
| stream-type locations | 829 of the 1,472 unmatched locations |

For each location the inventory records raw names, counties, geo_codes, first
and latest stocking date, row count and species. The full file is
`out/identity/stocking_locations.json` (gitignored). The sample is
`samples/stocking_locations_sample.json`.

Collision statistics on the official side:

- 87 official name keys are used by more than one entity statewide.
- 14 (name, county) pairs have more than one entity, 24 at the core-name
  level. Examples: two "Mud Lake (Snohomish County)" pages, three
  Okanogan "Blue Lake" pages, two Snohomish Martha lakes.

## 5. Matching system (`match.py`)

Every stocking location gets exactly one decision with level, method,
evidence, candidates and (if A/B/C) entity ID, canonical name, county,
official URL and coordinates.

- **A**: exact normalized name, county agrees, one entity in the county,
  **and** the stocking geo_code equals the official Geo Code, and the code is
  not shared with a different water. This is stricter than the brief, which
  required only name and county.
- **B**: geo_code equals the official code, the code is unshared, county
  agrees, the entity is unique, and the names agree after a listed alias
  rule. The rules are word order ("LK BRADLEY" = "Lake Bradley"), generic
  word omitted ("Wagner" = "WAGNER LK"), spacing, and `@ site` on the same
  water.
- **C**: one plausible entity, weaker evidence. **Human review.**
- **D**: ambiguous or conflicting (same-name waters, missing county, shared
  or contradictory codes, malformed record). **Human review.**
- **NONE**: no official entity.

Qualifier tokens (N/S/E/W, Upper/Lower, Little/Big, numbers, AM/WB) must
agree for any alias or close-name match. A name match whose code
contradicts goes to D.

Full population (3,314 locations):

| | A | B | C | D | NONE |
|---|---|---|---|---|---|
| locations | 509 | 554 | 276 | 503 | 1,472 |
| rows (all years) | 46,100 | 8,600 | 9,006 | 15,769 | 30,052 |
| **2026 catchable trout rows (≤ 3 fish/lb)** | **750 (69.4%)** | **79 (7.3%)** | 148 (13.7%) | 36 (3.3%) | 68 (6.3%) |
| 2026 catchable fish released | 76.3% | 10.3% | 8.2% | 2.3% | 2.9% |

## 6. The 20 MVP waters

| MVP water | stocking `release_location` | level | official entity | Geo Code |
|---|---|---|---|---|
| Battle Ground Lake | BATTLE GROUND LK (CLAR) | A | battle-ground-lake | L333 |
| Lacamas Lake | LACAMAS LK (CLAR) | A | lacamas-lake | L44874 |
| Klineline Pond | KLINELINE PD (CLAR) | A | klineline-pond | L38502 |
| Green Lake (King) | GREEN LK (KING) | A | green-lake-king | L1536 |
| Angle Lake | ANGLE LK (KING) | A | angle-lake | L91 |
| Lake Meridian | LK MERIDIAN (KING) | A | lake-meridian | L3273 |
| **Martha Lake (Snohomish)**, which is two official waters | MARTHA LK (AM) (SNOH) | **C** (review) | martha-alderwood-manor (suggested, correct) | L3217 |
| | MARTHA LK (WB) (SNOH) | **D** (review) | martha-lake-snohomish (listed, correct) | page L3218 ≠ stocking L3219 |
| Ward Lake | WARD LK (THUR) | A | ward-lake | L8939 |
| **Longs Pond** | LONGS PD (THUR) | **C** (review) | longs-pond (suggested, correct) | L2818, shared with LONG LK (THUR) |
| American Lake | AMERICAN LK (PIER) | A | american-lake | L35 |
| Alder Lake | ALDER LK (THUR/PIER) | A | alder-lake | L23 |
| Mineral Lake | MINERAL LK (LEWI) | A | mineral-lake | L3300 |
| Bradley Lake | BRADLEY LK (PIER) | B (word order) | lake-bradley | L35548 |
| Spanaway Lake | SPANAWAY LK (PIER) | A | spanaway-lake | L4266 |
| Lake Kapowsin | LK KAPOWSIN (PIER) | A | lake-kapowsin | L2668 |
| Lake Whitman | LK WHITMAN (PIER) | A | lake-whitman | L547 |
| Tanwax Lake | TANWAX LK (PIER) | A | tanwax-lake | L4578 |
| Clear Lake (Pierce) | CLEAR LK (PIER) | A | clear-lake-pierce | L4498 |
| Bonney Lake | BONNEY LK (PIER) | A | bonney-lake | L466 |
| Rapjohn Lake | RAPJOHN LK (PIER) | A | rapjohn-lake | L3838 |

All official URLs are `https://wdfw.wa.gov/fishing/locations/lowland-lakes/<slug>`.
Coordinates are in `samples/canonical_waters_sample.json`.

**18/20 automatic and correct, 2/20 review with the correct candidate,
0 wrong.** The MVP list's own "Martha Lake (Snohomish County)" needs a
product decision: WDFW has two Snohomish Martha lakes, Alderwood Manor
(47.85 N) and Warm Beach (48.17 N).

## 7. Stress test (83 audited items)

| Category | n | A | B | C | D | NONE |
|---|---|---|---|---|---|---|
| MVP rows | 21 | 17 | 1 | 2 | 1 | 0 |
| intentionally ambiguous / common names | 22 | 3 | 1 | 4 | 13 | 1 |
| blank county | 10 | 1 | 1 | 0 | 6 | 2 |
| malformed / encoding / problematic | 10 | 0 | 0 | 5 | 2 | 3 |
| random automated (A/B), drawn with seed 31102026 | 20 | 9 | 11 | 0 | 0 | 0 |
| **total** | **83** | 30 | 14 | 11 | 22 | 6 |

The ambiguous set covers:

- Clear Lake (Skagit T34/T36, Snohomish);
- Martha Lake (Grant);
- Silver Lake (Jefferson/Mason/Snohomish T28);
- Beaver Lake (Okanogan T34/T39, Snohomish);
- Mud Lake (King);
- Blue Lake (Okanogan T35);
- Green Lake (Pierce);
- American Lake (Yakima);
- Deer Lake (Lincoln);
- Duck Lake (1);
- Carney Lake (two-county);
- Long Lake (Thurston, Kitsap);
- Little Twin Lakes;
- Horseshoe Lake (King T21);
- Klineline Pond W.

Malformed examples: `SOUTHGATE CR 09?`; `KLINELINE PONDS` with the wrong
county and a geo_code holding three codes; `HOLMS DERBY PD`; `TENINO DERBY`;
`WARD LKS UPR+LWR`; `88 RD BP`; `PRAIRE MT LKS (1)`; `BEAVER LKS (KING) T24`;
`ROOSEVELT LK@KETTLE FALLS NP`; `TWIN LKS-LOWER(45)`.

### Audit outcomes (`audit_results.json`)

| Outcome | Count |
|---|---|
| exact correct (A) | 30 |
| correct via alias normalization (B) | 14 |
| correct match, but needing human review (C/D, the true entity suggested or listed) | 19 |
| routed to review, truth is "no official entity" | 8 |
| unresolved: undecidable from official data, safely in D | 6 (SILVER LK (MASO), BEAVER LK (SNOH), MUD LK (KING), DEER LK (LINC), DUCK LK (1), KLINELINE PONDS) |
| correctly left unmatched (NONE, no official entity) | 6 |
| **incorrect automated matches** | **0** |

## 8. False-positive rate

**0 / 44 automated matches = 0%** in the audited sample.

- With 44 trials, the 95% upper bound by the rule of three is about 6.8%.
  A larger random audit of A/B matches would tighten that.
- **During the audit one unsafe A match was found and fixed.** The parser
  read "(1)" in `DUCK LK (1) (GRAY)` as a WRIA number, which merged the
  numbered ponds into "Duck Lake". It now goes to D. The audit was rerun
  from scratch after the fix.
- Earlier, during development, a looser close-name rule had proposed wrong
  candidates such as `FISH LK (KING)` → "Fisher Lake" and `BEAVER LK (KING)` →
  "Bear Lake". Those were review-level only and never confirmed. The rule
  was tightened, and a name match whose code contradicts now goes to D.

## 9. Manual-review rate

- **Audited sample: 39.8%** (33/83) review, 53.0% automated, 7.2% NONE.
- **Statewide 2026 catchable trout: 17.0% of rows, 60 distinct locations.**
  That is a one-time review; decisions become stored aliases and are not
  re-reviewed on every refresh.
- All-years, all-species locations: 779 C/D out of 3,314.

## 10. Unresolved cases

Exact cases from the audited sample:

| location | why |
|---|---|
| SILVER LK (MASO) | carries `L3991`, a Jefferson County lake's code |
| BEAVER LK (SNOH) | carries `L3724`, which is Quail Lake (Adams) |
| MUD LK (KING) | `L3363` is in no official set; the official King Mud Lake is `L3362` |
| DEER LK (LINC) | shares `L1060` with Deer Springs Lake; same water or not is undocumented |
| DUCK LK (1) (GRAY) | numbered ponds share Duck Lake's `L1009` |
| KLINELINE PONDS | wrong county (Skamania), three codes in one field |

Review-required with the correct answer suggested or listed:

- MARTHA LK (AM) / (WB) (SNOH)
- LONGS PD (THUR) and LONG LK (THUR)
- CLEAR LK (SKAG) T34 / T36
- BEAVER LK (OKAN) T34 / T39
- BLUE LK (OKAN) T35
- SILVER LK (SNOH) T28
- TWIN LKS LTL (OKAN)
- MAYFIELD LK (26)
- LK ROOSEVELT (53)
- TENINO DERBY
- 88 RD BP (SKAM)
- PRAIRE MT LKS (1) (SKAG)
- BEAVER LKS (KING) T24
- ROOSEVELT LK@KETTLE FALLS NP
- SILVER LK (JEFF)

**Official-source gap:** 401 stocking locations carry an `L…` code with no
official entity, and 64 of them were stocked in 2026. Examples: Bonaparte
Lake, Molson Lake, Sidley Lake, Black Lake (Stevens), Lake Tahuya, Long Lake
(Spokane). They can be identified by code, but WDFW publishes no page or
coordinates for them.

## 11. Proposed canonical identity model (adapted to what the sources support)

```
waters
  internal_water_id     minted once (UUID); never derived, never reused
  canonical_name        official page title / GIS LakeMapName
  counties              ARRAY: several official lakes span 2–5 counties
  latitude, longitude   page "Center" (697/710 pages) or GIS centre; NULL if none
  official_source       wdfw_lowland_page | wdfw_gis_high_lake | stocking_code_only
  official_wdfw_url     page URL (NULL for most GIS high lakes and code-only waters)
  official_wdfw_slug    e.g. 'battle-ground-lake'   (unique where present)
  wdfw_geo_code         official page Geo Code / GIS GeometryID (unique among official
                        entities; NOT a safe key on the stocking side)
  gis_fishwa_id         layer-21 FishWAid where present
  match_status          official | official_unpaged | unlisted_code_only
  source_retrieved_at, created_at, updated_at

water_aliases                     -- one row per distinct release_location
  alias                 normalized release_location   (UNIQUE: one alias -> one water)
  raw_aliases           raw spellings seen
  water_id              FK waters, NULL while unresolved
  county_context        counties seen on the alias's rows + suffix county
  stocking_geo_code     geo_code carried by the alias's rows (watch for changes)
  level                 A | B | C_reviewed | D_reviewed | unresolved
  method, evidence      as produced by match.py
  reviewed_by, reviewed_at, review_note
  source                '6fex-3r7d release_location'
  active

stocking_events
  content_hash_id       SHA-256 of official columns + occurrence suffix (Step 1)
  alias                 FK water_aliases (water_id resolved through it; may be NULL)
  release_start_date, release_end_date, species, species_type, number_released,
  number_of_fish_per_pound, total_pounds, lifestage, facility,
  original_release_location, original_county, original_geo_code,
  record_kind='reported_plant', source_dataset, retrieved_at

identity_review_queue
  alias, level, candidates[], evidence, opened_at, decision, decided_by, decided_at
```

### Why it is durable and repeatable

- Events attach through `alias` (the release_location string), not through
  Socrata `:id`, which is regenerated on every refresh, and not through raw
  geo_code.
- A new stocking row with a known alias resolves deterministically.
- A new alias runs `match.py`: A/B is inserted automatically, and C/D goes to
  the review queue with its candidates. Nothing is promoted without a person.
- If an alias's `stocking_geo_code` or an official page's Geo Code changes,
  the alias is re-queued.
- Plan-sourced records (Step 1) stay in separate tables and can link to
  `waters` later.

## 12. Files created or changed (`validation/wdfw/`)

| File | Status |
|---|---|
| `identity/README.md` | new |
| `identity/IDENTITY_VALIDATION_REPORT.md` | new |
| `identity/build_inventory.py` | new |
| `identity/fetch_official_lakes.py` | new |
| `identity/match.py` | new |
| `identity/audit.py` | new |
| `identity/export_samples.py` | new |
| `identity/validation_sample.json` | new: 83 hand-labelled items with `truth_basis` |
| `identity/audit_results.json` | new |
| `identity/samples/canonical_waters_sample.json` | new |
| `identity/samples/aliases_sample.json` | new |
| `identity/samples/review_queue_sample.json` | new |
| `identity/samples/stocking_locations_sample.json` | new |
| `identity/samples/geo_code_profile.json` | new |
| `identity/samples/match_summary.json` | new |
| `monitor/daily_snapshot.py` | new |
| `monitor/MONITOR_LOG.md` | new |
| `monitor/snapshots/2026-10-31.json` | new: the baseline |
| `README.md` | links to Step 2 and the monitor |

Gitignored (`out/identity/`): the 756 cached pages, full official entity
files, full inventory, full matches and entities.

## 13. Commands and tests run

The pipeline:

```bash
cd validation/wdfw/identity && python3 build_inventory.py
```

```bash
python3 fetch_official_lakes.py --delay 1.5
```

That crawl made 756 requests with 0 failures; both GIS layers returned
(653 and 1,080 features).

```bash
python3 match.py
```

```bash
python3 audit.py
```

```bash
python3 export_samples.py
```

The audit exited 0, with 0 false confident matches.

```bash
cd validation/wdfw && python3 monitor/daily_snapshot.py
```

That was the baseline snapshot.

Probes and checks:

- WDFW lowland search, lake page, JS bundle (found the `geo_code` join),
  `/jsonapi`, `?_format=json`, `robots.txt`.
- ArcGIS webmap `fb6754c02ad444a6a8ef7a4d5d1c5fe5` item and data;
  MapServer layer metadata, counts and queries.
- Socrata catalog searches on data.wa.gov.
- `nbd2-vdmz` sample.
- `6fex-3r7d` column metadata.
- Ad-hoc profiling: geo_code uniqueness, official code uniqueness, GIS
  layer-2 URLs and counties, 2026 catchable coverage by level, NONE
  breakdown.

The matcher was revised during development:

- entity merge by code and dedup by slug;
- the qualifier rule;
- a stricter close-name rule;
- codes shared by a different water;
- WRIA vs pond-number parsing;
- a same-stem fallback to review.

Each revision was rerun before the final audit.

### Scheduled monitor

Scheduled task "WDFW stocking daily monitor (1 week)":

- runs daily at 14:13 America/Los_Angeles, first run 2026-10-31;
- each run starts a fresh cloud session, runs `monitor/daily_snapshot.py`
  and commits one snapshot to `claude/determined-mccarthy-ctlz3b`;
- it stops after 8 snapshots and then must be disabled.

It stores no connectors (none are needed). Each run has to attach the repo
itself, so the first run will show whether it can push.

## 14. Remaining risks

- **The truth labels were assigned by the validating agent** from official
  evidence (codes, page coordinates, names, counties). Some labels rely on
  the same evidence the matcher uses. **A human spot-check of
  `validation_sample.json` is recommended**, especially the 6 UNDECIDABLE
  items and Martha (WB).
- **WDFW source defects** (sections 2 and 10) mean the official pages'
  "recent plants" tables can be wrong themselves. Do not use page plant
  tables as ground truth.
- **Official coverage:** 64 waters stocked in 2026 have no page. If the
  product wants them, a non-WDFW geodata source, or a manually curated
  entity, is needed; that's a Step 3 question.
- **geo_code stability over time** isn't observed yet. Names have mapped
  1:1 to codes for 30 years in the current export, but codes may be
  re-applied at each export. The daily monitor tracks content-hash changes.
- **The HTML crawl is a dependency.** There is no API. The labelled-field
  parsing is simple, but it breaks if the page template changes. The crawl
  is cached, about 760 requests, and needs to rerun only weekly or monthly.
- **Sample size:** the 0% false-positive bound is about 6.8% at 95%
  confidence. A larger random A/B audit (e.g. 100) would tighten it.
- **Name parsing edge cases** remain: full county names in suffixes
  (`(STEVENS)`), embedded WRIA numbers (`LIBERTY LK (SPOK) (57)`) and
  combined waters (`WARD LKS UPR+LWR`). They currently fall to C/D/NONE,
  which is safe but costs automation.

## 15. Recommendation: proceed to Step 3, with one prerequisite

The identity layer is trustworthy in the sense that matters: **no false
confident matches**, every ambiguity is surfaced, and 77% of 2026
catchable-trout rows (87% of fish) attach automatically.

Before or during Step 3:

1. Have a person review the 2026 catchable C/D queue: 60 locations
   statewide, including the 2 MVP items. Store the decisions as reviewed
   aliases.
2. Decide which Snohomish Martha Lake the MVP means, or include both.
3. Spot-check the audit labels.

No further matcher development is needed to start Step 3.
