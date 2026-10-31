#!/usr/bin/env python3
"""Validation-only matcher: stocking release_location -> official WDFW water.

Inputs (from build_inventory.py and fetch_official_lakes.py, in out/identity/):
  stocking_locations.json, official_lowland_lakes.json, gis_high_lakes.json,
  gis_lowland_lakes.json
Output:
  out/identity/matches.json   one decision per stocking location (gitignored)

Evidence levels (weakest wins; nothing is ever promoted automatically):
  A  deterministic: exact name key + county agrees + exactly one official
     entity with that name key in that county + the stocking geo_code equals
     the entity's official Geo Code (stricter than "does not contradict":
     a blank stocking geo_code drops the match to C).
  B  deterministic alias: the stocking row's geo_code equals the entity's
     official Geo Code (the key WDFW's own lake page uses to list these
     plants), the code is unshared, the county agrees, the entity is unique,
     and the names agree after a listed alias rule: word order, "@ sub-site"
     on the same water, generic word omitted ("Wagner" = "WAGNER LK"),
     spacing ("Souphole" = "SOUP HOLE LK").
  C  strong candidate, REVIEW REQUIRED: exactly one plausible entity, but the
     evidence is weaker (geo_code agrees but names differ; or close name with
     county agreement and no code confirmation).
  D  ambiguous, REVIEW REQUIRED: several plausible entities, missing county,
     a geo_code shared by several stocking names, or conflicting evidence.
  NONE  no official water entity found (streams, rivers, unlisted waters).
Only A and B are "automated"; C and D are never treated as confirmed.
"""
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out" / "identity"

ABBR = {
    "LK": "LAKE", "LKS": "LAKES", "PD": "POND", "PDS": "PONDS", "CR": "CREEK", "RES": "RESERVOIR",
    "LTL": "LITTLE", "LWR": "LOWER", "UPR": "UPPER", "UP": "UPPER", "N": "NORTH", "S": "SOUTH",
    "E": "EAST", "W": "WEST", "MT": "MOUNT", "PRK": "PARK", "SPRS": "SPRINGS", "SPR": "SPRING",
    "R": "RIVER", "SL": "SLOUGH", "FK": "FORK", "MDL": "MIDDLE", "MID": "MIDDLE", "PT": "POINT",
    "IS": "ISLAND", "CYN": "CANYON", "CTR": "CENTER", "LO": "LOWER", "&": "AND", "NO": "NUMBER",
}
GENERIC = {"LAKE", "LAKES", "POND", "PONDS", "RESERVOIR", "THE", "OF", "AND", "NUMBER"}
# tokens that distinguish neighbouring waters; a mismatch blocks any alias/close match
QUALIFIERS = {"NORTH", "SOUTH", "EAST", "WEST", "UPPER", "LOWER", "LITTLE", "BIG", "MIDDLE", "GREAT",
              "1", "2", "3", "4", "5", "6", "7", "8", "9", "I", "II", "III", "AM", "WB"}
VALID_CODE = re.compile(r"^(L\d+|\d{2}\.\d{4}[A-Z]?|G\d+|P\d+)$")


def qualifiers(core):
    return {t for t in core if t in QUALIFIERS}


def squash(core):
    return "".join(sorted(core)).replace(" ", "")
SUFFIX = re.compile(r"\(([A-Z]{4})(?:/([A-Z]{4}))?\)")
OFFICIAL_COUNTY = re.compile(r"\(([A-Za-z .]+?) County\)\s*$", re.I)


def tokens(s):
    s = s.upper().replace("'", "").replace("’", "")
    s = re.sub(r"[.,#\-–/()]+", " ", s)
    return [ABBR.get(t, t) for t in s.split()]


def parse_stocking(key):
    """Split a normalized release_location into comparable parts."""
    s = key
    sub = None
    if "@" in s:
        s, sub = (x.strip() for x in s.split("@", 1))
    suffix = [g for g in (SUFFIX.search(s).groups() if SUFFIX.search(s) else ()) if g]
    s = SUFFIX.sub(" ", s)
    wria = re.findall(r"\((\d{1,2})\)\s*$", s)            # e.g. "LK ABERDEEN (22)"
    s = re.sub(r"\(\d{1,2}\)\s*$", " ", s)
    township = re.findall(r"\bT(\d{2})\b", s)              # e.g. "CLEAR LK (SKAG) T34"
    s = re.sub(r"\bT\d{2}\b", " ", s)
    stream_no = re.findall(r"\b\d{2}\.\d{4}[A-Z]?\b", s)    # stream catalog number
    s = re.sub(r"\b\d{2}\.\d{4}[A-Z]?\b", " ", s)
    numbered = re.findall(r"\((\d)\)", s)                  # "DUCK LK (1)"
    s = re.sub(r"\((\d)\)", r" \1 ", s)
    t = tokens(s)
    return {"name_key": " ".join(t), "sorted_key": " ".join(sorted(t)), "core": set(t) - GENERIC,
            "subsite": sub, "suffix_codes": suffix, "wria_hint": wria, "township_hint": township,
            "stream_catalog_no": stream_no, "numbered": numbered,
            "is_derby": "DERBY" in t}


def parse_official(name):
    m = OFFICIAL_COUNTY.search(name)
    base = OFFICIAL_COUNTY.sub("", name) if m else name
    t = tokens(base)
    return {"name_key": " ".join(t), "sorted_key": " ".join(sorted(t)), "core": set(t) - GENERIC,
            "name_county_qualifier": m.group(1).strip() if m else None}


def load():
    locs = json.loads((OUT / "stocking_locations.json").read_text())
    low = json.loads((OUT / "official_lowland_lakes.json").read_text())["lakes"]
    high = json.loads((OUT / "gis_high_lakes.json").read_text())["features"]
    ents = []
    # the listing has one row per (lake, county): a lake spanning counties appears
    # several times under one slug. One entity per slug, with a county set.
    by_slug = {}
    for L in low:
        by_slug.setdefault(L["slug"], []).append(L)
    for slug, group in by_slug.items():
        L = group[0]
        counties = sorted({g.get("listing_county") for g in group if g.get("listing_county")}
                          | {g.get("county") for g in group if g.get("county")})
        name = L.get("page_title") or L["listing_name"]
        ents.append({"entity_id": f"wdfw-lowland:{L['slug']}", "source": "wdfw_lowland_lake_page",
                     "canonical_name": name, "county": ", ".join(counties), "counties": counties,
                     "geo_code": L.get("geo_code") or L.get("page_query_geo_id"),
                     "official_url": L["official_url"], "lat": L.get("lat"), "lon": L.get("lon"),
                     **parse_official(name)})
    seen = set()
    low_by_code = {e["geo_code"]: e for e in ents if e["geo_code"]}
    for f in high:
        gid = f.get("GeometryID")
        if not gid or gid in seen:   # one feature per (GeometryID, WebUse) — keep first
            continue
        seen.add(gid)
        if gid in low_by_code:
            # same official code as a lowland-lake page: one water, two sources
            low_by_code[gid].setdefault("corroborating_sources", []).append(
                {"source": "wdfw_gis_high_lakes_layer21", "GeometryID": gid, "name": f.get("LakeMapName"),
                 "county": f.get("CountyName"), "FishWAid": f.get("FishWAid")})
            continue
        name = f.get("LakeMapName") or ""
        ents.append({"entity_id": f"wdfw-gis-highlake:{gid}", "source": "wdfw_gis_high_lakes_layer21",
                     "canonical_name": name, "county": f.get("CountyName"),
                     "counties": [f.get("CountyName")] if f.get("CountyName") else [], "geo_code": gid,
                     "official_url": f.get("WebsiteURL") or None,
                     "lat": f.get("LatitudeCenter"), "lon": f.get("LongitudeCenter"),
                     "fishwa_id": f.get("FishWAid"), **parse_official(name)})
    return locs, ents


def decide(loc, ents, by_code, by_key, by_sorted, code_owners, county_of):
    p = parse_stocking(loc["location_key"])
    county_ev = set(loc["nonblank_counties"]) | set(loc["suffix_counties"])
    codes = [g for g in loc["geo_codes"] if g]
    code = codes[0] if codes else None
    malformed_code = code if code and not VALID_CODE.match(code) else None
    if malformed_code:
        code = None
    sharers = code_owners[code] - {loc["location_key"]} if code else set()
    shared_code = bool(sharers)
    # a sharer is "conflicting" when it names a different water: its county
    # evidence is disjoint from ours, or its core name differs and it is not an
    # "@ site" on a water or a derby event (e.g. LONG LK vs LONGS PD, both L2818)
    def distinct_water(k):
        if county_of[k] and county_ev and not (county_of[k] & county_ev):
            return True
        q = parse_stocking(k)
        return q["core"] != p["core"] and q["subsite"] is None and not q["is_derby"] and p["subsite"] is None and not p["is_derby"]
    shared_conflicting = sorted(k for k in sharers if distinct_water(k))
    out = {"location_key": loc["location_key"], "parsed": {k: (sorted(v) if isinstance(v, set) else v)
                                                           for k, v in p.items()},
           "county_evidence": sorted(county_ev), "geo_code": code, "malformed_geo_code": malformed_code,
           "geo_code_shared_with": sorted(sharers),
           "rows": loc["rows"], "latest_date": loc["latest_date"]}

    def county_ok(e):
        return bool(county_ev) and bool(set(e["counties"]) & county_ev)

    def result(level, ent, method, why, cands=()):
        out.update({"level": level, "review_required": level in ("C", "D"),
                    "automated": level in ("A", "B"), "method": method, "evidence": why,
                    "candidates": [{"entity_id": c["entity_id"], "canonical_name": c["canonical_name"],
                                    "county": c["county"], "geo_code": c["geo_code"],
                                    "official_url": c["official_url"]} for c in cands]})
        if ent:
            out.update({"entity_id": ent["entity_id"], "canonical_name": ent["canonical_name"],
                        "county": ent["county"], "official_url": ent["official_url"],
                        "lat": ent["lat"], "lon": ent["lon"], "entity_geo_code": ent["geo_code"],
                        "entity_source": ent["source"]})
        return out

    code_ents = by_code.get(code, []) if code else []
    name_ents = by_key.get(p["name_key"], [])
    name_cty = [e for e in name_ents if county_ok(e)]
    # official same-name lakes in the evidenced county(ies): >1 means the name alone cannot decide
    multi_county_conflict = len(loc["nonblank_counties"]) > 1 and len(p["suffix_codes"]) < 2

    if multi_county_conflict:
        cands = {e["entity_id"]: e for e in name_ents + code_ents}.values()
        return result("D", None, "conflict", "stocking rows carry more than one county", list(cands))
    if not county_ev:
        cands = list({e["entity_id"]: e for e in name_ents + code_ents}.values())
        return result("D", None, "missing_county",
                      "no county in County column or name suffix; never auto-confirmed", cands)

    # LEVEL A
    if len(name_cty) == 1:
        e = name_cty[0]
        if code and e["geo_code"] and code != e["geo_code"]:
            other = [x for x in code_ents if x is not e]
            return result("D", None, "conflict", f"name+county -> {e['entity_id']} but geo_code {code} -> "
                          f"{[x['entity_id'] for x in other] or 'no entity'}", [e] + other)
        if not code or code != e["geo_code"]:
            why = "malformed geo_code " + malformed_code if malformed_code else "no geo_code on stocking rows" if not code else "entity has no geo_code"
            return result("C", e, "exact_name_county_no_code_confirmation", f"exact name+county, unique, but {why}", [e])
        if shared_conflicting:
            return result("C", e, "exact_name_county_conflicting_shared_code",
                          f"geo_code {code} is also used by {shared_conflicting} (a different water)", [e])
        if p["township_hint"] or p["numbered"]:
            return result("C", e, "exact_name_county_with_disambiguator",
                          "name carries a township/number disambiguator; confirm it is this water", [e])
        if p["subsite"] is not None:
            return result("B", e, "geo_code_plus_alias:at_subsite",
                          f"'@ {p['subsite']}' is a site on this water; geo_code, name and county agree", [e])
        return result("A", e, "exact_name_county_geo_code",
                      "exact name key, county agrees, unique entity, geo_code equals official Geo Code", [e])
    same_core = [e for e in ents if county_ok(e) and e["core"] and e["core"] == p["core"]]
    if len(name_cty) > 1 or len(same_core) > 1:
        group = {e["entity_id"]: e for e in name_cty + same_core}
        pick = [e for e in code_ents if county_ok(e)]
        if len(pick) == 1 and len({e["geo_code"] for e in group.values()}) == len(group):
            # several same-name waters in the county; only the code singles one out
            return result("C", pick[0], "geo_code_disambiguates_same_name",
                          f"{len(group)} official same-name waters in {sorted(county_ev)}; geo_code {code} "
                          f"selects {pick[0]['entity_id']}", list(group.values()))
        return result("D", None, "multiple_same_name_in_county",
                      f"{len(group)} official entities named like '{p['name_key']}' in {sorted(county_ev)}",
                      list(group.values()))

    # LEVEL B — geo_code join with an alias rule on the name
    if len(code_ents) == 1:
        e = code_ents[0]
        rules = []
        same_q = qualifiers(p["core"]) == qualifiers(e["core"])
        if p["sorted_key"] == e["sorted_key"]:
            rules.append("word_order")
        elif same_q and p["core"] and p["core"] == e["core"]:
            rules.append("generic_word_omitted")
        elif same_q and p["core"] and squash(p["core"]) == squash(e["core"]):
            rules.append("spacing")
        if p["subsite"] is not None and rules:
            rules.append("at_subsite")
        partial = (not rules and e["core"] and (e["core"] <= p["core"] or p["core"] <= e["core"]))
        if not county_ok(e):
            return result("D", None, "conflict", f"geo_code -> {e['entity_id']} ({e['county']}) but county "
                          f"evidence is {sorted(county_ev)}", [e])
        if shared_code:
            return result("D", None, "shared_geo_code",
                          f"geo_code {code} is shared with {sorted(code_owners[code] - {loc['location_key']})}", [e])
        if rules and (p["township_hint"] or p["numbered"]) and not same_q:
            rules = []
        if rules:
            return result("B", e, "geo_code_plus_alias:" + "+".join(rules),
                          "official Geo Code equals stocking geo_code; county agrees; names agree after alias rule", [e])
        if partial:
            return result("C", e, "geo_code_plus_partial_name",
                          f"geo_code agrees and county agrees, but names only partly agree "
                          f"('{p['name_key']}' vs '{e['name_key']}')", [e])
        return result("C", e, "geo_code_only", f"geo_code and county agree but names differ "
                      f"('{p['name_key']}' vs '{e['name_key']}')", [e])
    if len(code_ents) > 1:
        return result("D", None, "geo_code_multiple_entities", f"{len(code_ents)} official entities carry {code}", code_ents)

    # LEVEL C — close name, county agrees, one plausible entity, no code confirmation
    pool = [e for e in ents if county_ok(e)]
    def close_enough(e):
        if qualifiers(e["core"]) != qualifiers(p["core"]) or not e["core"] or not p["core"]:
            return False
        if e["sorted_key"] == p["sorted_key"] or e["core"] == p["core"] or squash(e["core"]) == squash(p["core"]):
            return True
        a, b = " ".join(sorted(e["core"])), " ".join(sorted(p["core"]))
        return min(len(a), len(b)) >= 8 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.92
    close = [e for e in pool if close_enough(e)]
    if close and code and all(e["geo_code"] and e["geo_code"] != code for e in close):
        return result("D", None, "name_suggests_other_code",
                      f"close official name(s) exist but carry other code(s) "
                      f"{sorted(e['geo_code'] for e in close)}; stocking geo_code {code} has no official entity "
                      "(likely a different, unlisted same-name water)", close)
    if len(close) == 1:
        return result("C", close[0], "close_name_county", "close name and county agree; no geo_code confirmation", close)
    if len(close) > 1:
        return result("D", None, "multiple_close_names", "several close official names in county", close)
    return result("NONE", None, "no_candidate", "no official lowland-lake page or GIS high-lake entity matched", [])


def main():
    locs, ents = load()
    by_code, by_key, by_sorted = defaultdict(list), defaultdict(list), defaultdict(list)
    for e in ents:
        if e["geo_code"]:
            by_code[e["geo_code"]].append(e)
        by_key[e["name_key"]].append(e)
        by_sorted[e["sorted_key"]].append(e)
    code_owners = defaultdict(set)
    county_of = {}
    for L in locs:
        county_of[L["location_key"]] = set(L["nonblank_counties"]) | set(L["suffix_counties"])
        for g in L["geo_codes"]:
            if g:
                code_owners[g].add(L["location_key"])
    decisions = [decide(L, ents, by_code, by_key, by_sorted, code_owners, county_of) for L in locs]
    (OUT / "matches.json").write_text(json.dumps(decisions, indent=1))
    (OUT / "entities.json").write_text(json.dumps(
        [{k: (sorted(v) if isinstance(v, set) else v) for k, v in e.items()} for e in ents], indent=1))
    from collections import Counter
    lv = Counter(d["level"] for d in decisions)
    rows = Counter()
    for d in decisions:
        rows[d["level"]] += d["rows"]
    print("locations by level:", dict(sorted(lv.items())))
    print("stocking rows by level:", dict(sorted(rows.items())))
    print("methods:", Counter(d["method"] for d in decisions).most_common())
    return 0


if __name__ == "__main__":
    sys.exit(main())
