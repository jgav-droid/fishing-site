# Washington Stocked Lake Finder: MVP v0.1

Answers: **"Which recently stocked lake can I realistically fish from shore, and what
do I need to know before driving there?"**

Coverage is the 20 validated waters from Steps 1–3. Pages are static and
server-rendered (indexable HTML), with a small JS enhancement for the trip
finder.

## Routes

| Route | What it is |
|---|---|
| `/` | Trip finder: server-rendered results for today, re-sorted and filtered client-side (place, date, distance, shore, dock, restricted waters). State is kept in `#fragment`, so no crawlable parameter URLs |
| `/recently-stocked/` | Catchable plants in the last 30 days; fry and size-unknown releases in a separate, uncounted table |
| `/lakes/` | Index of the 20 validated lakes |
| `/lakes/<slug>/` | One canonical page per lake (20) |
| `/near/{seattle,tacoma,vancouver,olympia}/` | Area pages that passed the thin-page rules. Puyallup was **not** published: 92% overlap with Tacoma |
| `/methodology/` | Eligibility logic, sources, unknown handling, freshness |
| `/data-quality/` | Known conflicts, records deliberately not attached, review items, corrections contact |
| `/404.html`, `/sitemap.xml`, `/robots.txt` | |

## Data layer (`mvp/data/`), kept as separate files

| File | Kind | Produced by |
|---|---|---|
| `waters.json` | canonical waters | `pipeline/build_data.py` (from Step 2/3) |
| `aliases.json` | release_location → water: 20 confirmed (A/B or reviewed), 10 explicit **exclusions** | `build_data.py` + Step 3 `identity_review_decisions.json` |
| `access_facts.json` | static/periodic access facts per access point, with verbatim-quote provenance (verified in Step 3) | `build_data.py` (copy of the Step 3 dataset) |
| `curated_notices.json` | dated manager notices (each quote must match a verified Step 3 quote; tested) | hand-curated |
| `access_page_baselines.json` | normalized-hash baselines of all 49 cited pages | `build_data.py` |
| `places.json` | US Census 2024 Gazetteer place points within 100 km | `build_data.py` |
| `stocking_events.json` | completed plants (content-hash IDs) | `pipeline/refresh_stocking.py` |
| `notices.json` | regulations (WDFW emergency rules), health (Ecology algae), State Parks alerts, source changes | `pipeline/refresh_notices.py` |
| `source_status.json` | per-source last_attempt / last_success / status | both refreshers |
| `review_queue.json` | unmapped stocking names, advisory name matches, changed or unreachable source pages | both refreshers |

### Reused validation code (not re-implemented)

- `validation/wdfw/_http.py`: Step 1 HTTP helper.
- `validation/wdfw/identity/match.py` `parse_official`: Step 2 name keys.
- `validation/wdfw/access/trip_decision.py` `window`: Step 3 season windows.
- `validation/wdfw/access/probes/change_detection.py` `main_text`: Step 3 normalizer.
- Step 3's verified `access_dataset.json` and `identity_review_decisions.json`.

## Eligibility logic (`pipeline/eligibility.py`)

**Recent catchable stocking** means all of:

- a completed plant from WDFW Fish Plants (`record_kind == reported_plant`; anything else raises an error);
- species_type `Trout/Kokanee`;
- `0 < number_of_fish_per_pound ≤ 3.0`. This is WDFW's own "catchable" threshold, used in its lake-page script;
- `number_released > 0`;
- released within **30 days before the trip date** (a planning window, not a biological claim).

Fish/lb that is missing, 0 or ≥ 999999 is classed "size not reported" and never
counted. Lifestage labels are not used.

A lake **appears in results** when it has recent catchable stocking **and**
documented public shore access (YES or LIMITED).

**Flags** are shown, never merged into OPEN/CLOSED:

- regulation (season windows, juvenile-only waters, emergency rules);
- physical access (access-area seasons, dated closures, State Parks alerts);
- health (Ecology algae listing);
- data (source changed since review, conflicts).

Blocking flags rank a lake lower; they never hide it.

## Unknowns and ambiguity

- `UNKNOWN` renders as **"Not stated by <manager>"**, never "No" or "Free".
- Conflicts render as **"Unclear: official sources conflict"**.
- A NO needs an explicit official statement. Example: Lacamas has no day-use fee because it is absent from Clark County's closed list of fee parks.
- A pier that exists but is closed renders **"Closed"**, not "Yes".
- Stocking is selected by **exact confirmed release-location names**, never by geo_code.
- New names that carry an MVP lake's code go to the review queue, unattached.
- Ecology advisories attach by SiteID. A name match is allowed only if the name is held by exactly one official WDFW water, and is labelled "matched by lake name". Ambiguous names ("Green Lake", "Clear Lake") go to review.

## Freshness

- **Stocking:** WDFW publication time plus our last successful check.
- **Notices:** last successful check per source.
- **Access:** "last reviewed Oct 31, 2026 (static facts; not live reporting)", plus "official page changed since our review" when change detection fires.
- **Change detection** compares the normalized main text and confirms any mismatch with a second fetch, after one transient false positive was seen.
- **Failed refresh:** last-known data is kept; `last_success` does not move; pages show **STALE** with the failure time.
- **Stale after:** stocking, rules and algae 36 h; State Parks 72 h; access-page checks 8 days.

## Commands

The build uses Python ≥ 3.12, stdlib only. Run from the repo root.

Rebuild the static layer (needs the Step 2/3 caches under `validation/wdfw/out/`):

```bash
python3 mvp/pipeline/build_data.py
```

Refresh, test and build:

```bash
python3 mvp/run.py
```

Production build (needs `config.json` filled in):

```bash
python3 mvp/run.py --production
```

Tests only:

```bash
python3 -m unittest discover -s mvp/tests -v
```

Phone-width check:

```bash
(cd mvp/dist && python3 -m http.server 8811) & node mvp/tests/mobile_check.js http://127.0.0.1:8811
```

Deployment: `.github/workflows/mvp-site.yml` refreshes, tests, builds and
deploys to GitHub Pages every 6 hours. See `LAUNCH_CHECKLIST.md`.
