#!/usr/bin/env python3
"""Inventory of distinct release locations in the Fish Plants export.

Input: out/full_export.csv (bulk CSV from Step 1; display-name headers).
Outputs:
  out/identity/stocking_locations.json   every normalized location (gitignored)
  out/identity/geo_code_profile.json     geo_code statistics
  out/identity/county_suffix_map.json    name-suffix code -> county, derived from data

"Basic normalization" here is deliberately light: Unicode/whitespace
collapse + upper case. Nothing is merged across different strings.
"""
import collections
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out" / "identity"
EXPORT = HERE.parent / "out" / "full_export.csv"


def basic_norm(s):
    return " ".join(s.split()).upper()


def encoding_issue(raw):
    # '?' never appears legitimately in WDFW location names; U+FFFD / non-ASCII
    # are mojibake candidates.
    return "?" in raw or "�" in raw or any(ord(c) > 127 for c in raw)


SUFFIX = re.compile(r"\(([A-Z]{4})(?:/([A-Z]{4}))?\)")


def parse_date(s):
    return datetime.strptime(s.split()[0], "%m/%d/%Y").date().isoformat()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(EXPORT, newline="", encoding="utf-8")))
    locs = {}
    for r in rows:
        raw = r["Release Location"]
        key = basic_norm(raw)
        d = parse_date(r["Release Start Date"])
        L = locs.setdefault(key, {"location_key": key, "raw_names": collections.Counter(),
                                  "counties": collections.Counter(), "geo_codes": collections.Counter(),
                                  "species": collections.Counter(), "species_type": collections.Counter(),
                                  "first_date": d, "latest_date": d, "rows": 0})
        L["raw_names"][raw] += 1
        L["counties"][r["County"].strip()] += 1
        L["geo_codes"][r["Geo Code"].strip()] += 1
        L["species"][r["Species"]] += 1
        L["species_type"][r["Species Type"]] += 1
        L["first_date"] = min(L["first_date"], d)
        L["latest_date"] = max(L["latest_date"], d)
        L["rows"] += 1

    # county-suffix codes such as "(CLAR)" -> county, learned from rows that
    # carry both the suffix and a non-blank County value
    votes = collections.defaultdict(collections.Counter)
    for L in locs.values():
        m = SUFFIX.search(L["location_key"])
        if m and not m.group(2):
            for c, n in L["counties"].items():
                if c:
                    votes[m.group(1)][c] += n
    suffix_map = {}
    for code, cnt in sorted(votes.items()):
        (top, n), total = cnt.most_common(1)[0], sum(cnt.values())
        suffix_map[code] = {"county": top, "support": round(n / total, 4), "rows": total,
                            "other": dict(cnt.most_common()[1:4])}
    (OUT / "county_suffix_map.json").write_text(json.dumps(suffix_map, indent=1))

    for L in locs.values():
        m = SUFFIX.search(L["location_key"])
        codes = [g for g in (m.groups() if m else ()) if g]
        L["suffix_codes"] = codes
        L["suffix_counties"] = [suffix_map[c]["county"] for c in codes
                                if c in suffix_map and suffix_map[c]["support"] >= 0.9]
        L["nonblank_counties"] = sorted(c for c in L["counties"] if c)
        L["has_blank_county"] = "" in L["counties"]
        L["encoding_issue"] = any(encoding_issue(n) for n in L["raw_names"])

    # potential naming collisions: same name once the county suffix is removed
    stem = collections.defaultdict(list)
    for k in locs:
        stem[SUFFIX.sub("", k).strip()].append(k)
    for s, ks in stem.items():
        for k in ks:
            locs[k]["collision_group"] = s if len(ks) > 1 else None
            locs[k]["collision_members"] = sorted(ks) if len(ks) > 1 else []

    out = []
    for L in sorted(locs.values(), key=lambda x: x["location_key"]):
        out.append({**L, **{f: dict(L[f].most_common()) for f in
                            ("raw_names", "counties", "geo_codes", "species", "species_type")}})
    (OUT / "stocking_locations.json").write_text(json.dumps(out, indent=1))

    raw_names = {r["Release Location"] for r in rows}
    stats = {
        "rows": len(rows),
        "distinct_raw_release_location": len(raw_names),
        "distinct_after_basic_normalization": len(locs),
        "locations_in_multiple_nonblank_counties": sum(1 for L in out if len(L["nonblank_counties"]) > 1),
        "locations_with_any_blank_county": sum(1 for L in out if L["has_blank_county"]),
        "locations_with_only_blank_county": sum(1 for L in out if not L["nonblank_counties"]),
        "locations_only_blank_county_but_suffix_gives_county": sum(
            1 for L in out if not L["nonblank_counties"] and L["suffix_counties"]),
        "locations_with_encoding_issue": sum(1 for L in out if L["encoding_issue"]),
        "locations_in_name_collision_groups": sum(1 for L in out if L["collision_group"]),
        "name_collision_groups": sum(1 for s, ks in stem.items() if len(ks) > 1),
        "locations_with_county_suffix": sum(1 for L in out if L["suffix_codes"]),
        "locations_with_two_county_suffix": sum(1 for L in out if len(L["suffix_codes"]) == 2),
        "locations_with_lake_or_pond_word": sum(1 for L in out if re.search(r"\b(LK|LKS|LAKE|PD|POND|RES)\b", L["location_key"])),
    }

    # geo_code profile
    g2n, g2c = collections.defaultdict(set), collections.defaultdict(set)
    for L in out:
        for g in L["geo_codes"]:
            if g:
                g2n[g].add(L["location_key"])
                g2c[g].update(L["nonblank_counties"])
    blank = sum(1 for r in rows if not r["Geo Code"].strip())
    pat = collections.Counter()
    for g in g2n:
        pat["L<digits>" if re.fullmatch(r"L\d+", g) else
            "NN.NNNN" if re.fullmatch(r"\d{2}\.\d{4}[A-Z]?", g) else
            "G<digits>" if re.fullmatch(r"G\d+", g) else "other"] += 1
    geo = {
        "rows_blank_geo_code": blank, "blank_rate": round(blank / len(rows), 4),
        "distinct_geo_codes": len(g2n), "patterns": dict(pat),
        "geo_codes_mapping_to_multiple_location_names": sum(1 for s in g2n.values() if len(s) > 1),
        "geo_codes_spanning_multiple_nonblank_counties": sum(1 for s in g2c.values() if len(s) > 1),
        "location_names_mapping_to_multiple_geo_codes": sum(1 for L in out if len([g for g in L["geo_codes"] if g]) > 1),
        "locations_mixing_blank_and_nonblank_geo_code": sum(1 for L in out if "" in L["geo_codes"] and len(L["geo_codes"]) > 1),
        "multi_name_codes": {g: sorted(s) for g, s in sorted(g2n.items()) if len(s) > 1},
        "multi_county_codes": {g: sorted(s) for g, s in sorted(g2c.items()) if len(s) > 1},
    }
    (OUT / "geo_code_profile.json").write_text(json.dumps({"stats": stats, "geo_code": geo}, indent=1))
    print(json.dumps(stats, indent=1))
    print(json.dumps({k: v for k, v in geo.items() if not k.startswith("multi_")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
