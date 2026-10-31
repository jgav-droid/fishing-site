#!/usr/bin/env python3
"""Join WDFW ShoreFishingSites points and Public Fishing Piers to the MVP lakes.

A point joins a lake only if (a) its LakeName's core tokens are contained in the
lake's name, (b) its County is one of the lake's counties and (c) it lies within
4 km of the official lake centre. Distance alone is unsafe: Long Lake's access is
2 km from Long's Pond. Output: out/access/wdfw_gis_shore_mvp.json
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERIC = {"lake", "lakes", "pond", "county", "the", "access", "area", "alderwood", "manor"}


def core(n):
    return set(re.findall(r"[a-z]+", (n or "").lower().replace("'", ""))) - GENERIC


def km(a, b, c, d):
    return math.hypot((a - c) * 111, (b - d) * 111 * math.cos(math.radians(a)))


def main():
    ents = {e["entity_id"]: e for e in json.loads((ROOT / "out/identity/entities.json").read_text())}
    mvp = json.loads((ROOT / "access/mvp_waters.json").read_text())
    shore = json.loads((ROOT / "out/access/shore_fishing_sites.json").read_text())["features"]
    piers = [{k.split(".")[-1]: v for k, v in f.items()} for f in json.loads((ROOT / "out/access/public_fishing_piers.json").read_text())["features"]]
    out = {}
    for w in mvp:
        e = ents[w["entity_id"]]
        lake_core = core(w["name"]) | core(e["canonical_name"])
        hits = [{"AccessSiteID": f["AccessSiteID"], "LakeName": f["LakeName"], "County": f["County"],
                 "Description": f["Description"], "lat": f["_lat"], "lon": f["_lon"],
                 "km": round(km(e["lat"], e["lon"], f["_lat"], f["_lon"]), 2)}
                for f in shore if f["_lat"] is not None and core(f["LakeName"]) and core(f["LakeName"]) <= lake_core
                and f["County"] in e["counties"] and km(e["lat"], e["lon"], f["_lat"], f["_lon"]) <= 4]
        near_piers = [{"name": p["PierName"], "url": p["WebsiteURL"], "km": round(km(e["lat"], e["lon"], p["_lat"], p["_lon"]), 2)}
                      for p in piers if km(e["lat"], e["lon"], p["_lat"], p["_lon"]) <= 2]
        out[w["water_id"]] = {"shore_sites": hits, "public_piers_layer": near_piers}
        print(f"{w['name']:30} shore points={len(hits)} piers-layer={len(near_piers)}")
    (ROOT / "out/access/wdfw_gis_shore_mvp.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
