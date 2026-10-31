#!/usr/bin/env python3
"""Assemble the static/curated data layer from the validated Step 2-3 outputs.

Run when curated facts change (not on every refresh). Writes to mvp/data/:
  waters.json                  canonical waters (20 validated MVP waters)
  aliases.json                 stocking release_location -> water, plus explicit exclusions
  access_facts.json            Step 3 verified access facts (per access point, with provenance)
  access_page_baselines.json   normalised-hash baselines of every access source page at review time
  places.json                  US Census Gazetteer places within 100 km of a validated water
Needs the Step 2/3 caches under validation/wdfw/out/ (page caches, stocking_locations.json).
"""
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import DATA, MVP, VALIDATION, main_text, save  # noqa: E402

REVIEWED_AT = "2026-10-31"
SITE = {  # site slug, display name; WDFW slugs kept as the official id
    "wa-w-battle-ground-lake": ("battle-ground-lake", "Battle Ground Lake"),
    "wa-w-lacamas-lake": ("lacamas-lake", "Lacamas Lake"),
    "wa-w-klineline-pond": ("klineline-pond", "Klineline Pond"),
    "wa-w-green-lake-king": ("green-lake-seattle", "Green Lake (Seattle)"),
    "wa-w-angle-lake": ("angle-lake", "Angle Lake"),
    "wa-w-lake-meridian": ("lake-meridian", "Lake Meridian"),
    "wa-w-martha-alderwood-manor": ("martha-lake-lynnwood", "Martha Lake (Lynnwood)"),
    "wa-w-ward-lake": ("ward-lake", "Ward Lake"),
    "wa-w-longs-pond": ("longs-pond", "Long's Pond"),
    "wa-w-american-lake": ("american-lake", "American Lake"),
    "wa-w-alder-lake": ("alder-lake", "Alder Lake"),
    "wa-w-mineral-lake": ("mineral-lake", "Mineral Lake"),
    "wa-w-lake-bradley": ("bradley-lake", "Bradley Lake"),
    "wa-w-spanaway-lake": ("spanaway-lake", "Spanaway Lake"),
    "wa-w-lake-kapowsin": ("lake-kapowsin", "Lake Kapowsin"),
    "wa-w-lake-whitman": ("lake-whitman", "Lake Whitman"),
    "wa-w-tanwax-lake": ("tanwax-lake", "Tanwax Lake"),
    "wa-w-clear-lake-pierce": ("clear-lake-pierce-county", "Clear Lake (Pierce County)"),
    "wa-w-bonney-lake": ("bonney-lake", "Bonney Lake"),
    "wa-w-rapjohn-lake": ("rapjohn-lake", "Rapjohn Lake"),
}
# Known non-MVP release_locations that collide with MVP waters by geo_code or name.
# They must NEVER be attached to the MVP water (Step 2/3 findings).
EXCLUSIONS = [
    {"alias": "LONG LK (THUR)", "collides_with": "wa-w-longs-pond", "reason": "Carries Long's Pond's geo_code L2818 but is Long Lake (Thurston), 308 acres; manual override to long-lake-thurston (not in MVP)."},
    {"alias": "LACEY DERBY (LACEY)", "collides_with": None, "reason": "Event name; carries Long Lake's code L2807. Not an MVP water."},
    {"alias": "MARTHA LK (WB) (SNOH)", "collides_with": "wa-w-martha-alderwood-manor", "reason": "Warm Beach Lake Martha (page code L3218, stocking code L3219); a different water from the Lynnwood Martha Lake."},
    {"alias": "MORTON DERBY (LEWI)", "collides_with": "wa-w-mineral-lake", "reason": "Derby event sharing Mineral Lake's geo_code L3300; not attributed to Mineral Lake without review."},
    {"alias": "KLINELINE PD E (CLAR)", "collides_with": "wa-w-klineline-pond", "reason": "Separate pond (code L38454), no official page."},
    {"alias": "KLINELINE PD W (CLAR)", "collides_with": "wa-w-klineline-pond", "reason": "Separate pond (code L38533), no official page."},
    {"alias": "KLINELINE PONDS", "collides_with": "wa-w-klineline-pond", "reason": "Malformed record: county Skamania and three codes in one geo_code field."},
    {"alias": "GREEN LK (PIER)", "collides_with": "wa-w-green-lake-king", "reason": "Different Green Lake (Pierce, L1537)."},
    {"alias": "AMERICAN LK (YAKI)", "collides_with": "wa-w-american-lake", "reason": "Different American Lake (Yakima, L36)."},
    {"alias": "MARTHA LK (GRAN)", "collides_with": "wa-w-martha-alderwood-manor", "reason": "Different Martha Lake (Grant, L3070)."},
]


def km(a, b, c, d):
    return math.hypot((a - c) * 111.0, (b - d) * 111.0 * math.cos(math.radians(a)))


def main():
    access = json.loads((VALIDATION / "access/access_dataset.json").read_text())
    mvp_list = {w["water_id"]: w for w in json.loads((VALIDATION / "access/mvp_waters.json").read_text())}
    decisions = {d["alias"]: d for d in json.loads((VALIDATION / "access/identity_review_decisions.json").read_text())["decisions"]}
    locs = {L["location_key"]: L for L in json.loads((VALIDATION / "out/identity/stocking_locations.json").read_text())}
    matches = {m["location_key"]: m for m in json.loads((VALIDATION / "out/identity/matches.json").read_text())}

    ents = json.loads((VALIDATION / "out/identity/entities.json").read_text())
    sys.path.insert(0, str(VALIDATION / "identity"))
    from match import parse_official  # Step 2 name normaliser
    key_count = {}
    for e in ents:
        key_count[e["name_key"]] = key_count.get(e["name_key"], 0) + 1
    waters, aliases = [], []
    for rec in access:
        wid = rec["water_id"]
        slug, name = SITE[wid]
        prim = next(a for a in rec["access_points"] if a["primary"])
        waters.append({
            "water_id": wid, "slug": slug, "display_name": name, "wdfw_name": rec["canonical_name"],
            "counties": rec["counties"], "wdfw_geo_code": rec["wdfw_geo_code"],
            "official_wdfw_url": rec["official_wdfw_url"], "lake_centre": rec["lake_centre"],
            "primary_access_manager": prim["manager"], "access_reviewed_at": REVIEWED_AT,
            "emergency_rules_url": rec["fishing_rule_sources"]["emergency_rules_for_this_lake"],
            "identity_status": "confirmed",
            # names that may attach an external advisory (e.g. Ecology algae table) by name:
            # only if the normalised name is held by exactly one of all official entities
            "unique_name_keys": sorted({k for k in (parse_official(rec["canonical_name"])["name_key"],
                                                    parse_official(name)["name_key"]) if key_count.get(k, 0) == 1}),
            "ambiguous_name_keys": sorted({k for k in (parse_official(rec["canonical_name"])["name_key"],
                                                       parse_official(name)["name_key"]) if key_count.get(k, 0) != 1}),
        })
        for a in mvp_list[wid]["stocking_aliases"]:
            m = matches[a]
            d = decisions.get(a)
            level = d["level"] if d else m["level"]
            if level not in ("A", "B") and not (d and d["decision"] == "wdfw-lowland:" + rec["official_wdfw_url"].rsplit("/", 1)[1]):
                raise SystemExit(f"alias {a} is not confirmed (level {level}); refusing to publish")
            aliases.append({"alias": a, "water_id": wid, "raw_names": sorted(locs[a]["raw_names"]),
                            "stocking_geo_codes": sorted(g for g in locs[a]["geo_codes"] if g),
                            "status": "confirmed", "level": level,
                            "method": d["level"] if d else m["method"],
                            "evidence": d["evidence"] if d else [m["evidence"]]})
    for x in EXCLUSIONS:
        x = dict(x, raw_names=sorted(locs[x["alias"]]["raw_names"]) if x["alias"] in locs else [],
                 stocking_geo_codes=sorted(g for g in locs.get(x["alias"], {}).get("geo_codes", {}) if g))
        aliases.append({**x, "water_id": None, "status": "excluded"})
    save("waters.json", waters)
    save("aliases.json", aliases)
    save("access_facts.json", {"reviewed_at": REVIEWED_AT, "source": "validation/wdfw/access/access_dataset.json",
                               "waters": access})

    # baselines for change detection: every page cited by the access facts
    base = {}
    for rec in access:
        urls = set()
        for f in ("bank_fishing_status", "fishing_pier_or_dock"):
            urls |= {p["source_url"] for p in rec[f]["provenance"]}
        for a in rec["access_points"]:
            for v in a.values():
                if isinstance(v, dict) and "provenance" in v:
                    urls |= {p["source_url"] for p in v["provenance"]}
        for n in rec["current_notices"] + rec["rule_notes"]:
            urls.add(n["source_url"])
        for u in sorted(urls):
            if "MapServer" in u or not u.startswith("http"):
                continue
            path = cache_path(u)
            if path is None:
                print("no cached copy for baseline:", u)
                continue
            text = main_text(path.read_text(encoding="utf-8"))
            base.setdefault(u, {"hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                                "baseline_at": REVIEWED_AT, "water_ids": []})
            base[u]["water_ids"].append(rec["water_id"])
    save("access_page_baselines.json", base)

    places = []
    with open(MVP / "data/raw/gaz_places_wa.txt", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            r = {k.strip(): (v or "").strip() for k, v in r.items()}
            lat, lon = float(r["INTPTLAT"]), float(r["INTPTLONG"])
            if any(km(lat, lon, w["lake_centre"]["lat"], w["lake_centre"]["lon"]) <= 100 for w in waters):
                name = re.sub(r" (city|town|CDP)$", "", r["NAME"])
                places.append({"name": name, "kind": r["NAME"].rsplit(" ", 1)[-1], "lat": lat, "lon": lon, "geoid": r["GEOID"]})
    places.sort(key=lambda p: p["name"])
    save("places.json", {"source": "US Census Bureau 2024 Gazetteer, places, Washington (internal points)",
                         "source_url": "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_gaz_place_53.txt",
                         "places": places})
    print(f"waters {len(waters)}, aliases {sum(a['status'] == 'confirmed' for a in aliases)} confirmed / "
          f"{sum(a['status'] == 'excluded' for a in aliases)} excluded, baselines {len(base)}, places {len(places)}")


def cache_path(url):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", url.split("://", 1)[1])[:180] + ".html"
    for d in (VALIDATION / "out/access/pages", VALIDATION / "out/identity/pages"):
        if (d / name).exists():
            return d / name
    if url.rstrip("/") == "https://wdfw.wa.gov/places-to-go/water-access-sites":
        return VALIDATION / "out/access/was_list.html"
    if url.startswith("https://www.nwtoxicalgae.org"):
        return VALIDATION / "out/access/algae.html"
    return None


if __name__ == "__main__":
    main()
