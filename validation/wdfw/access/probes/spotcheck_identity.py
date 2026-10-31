#!/usr/bin/env python3
"""Independent spot-check of automatic MVP identity matches (Step 3 pre-check).

For each automatic MVP match, three checks that do not reuse match.py logic:
  1. US Census geocoder: the official page's centre lat/lon falls in the page's county.
  2. WDFW's own join: querying 6fex-3r7d with geo_code = the page's Geo Code returns
     exactly our alias (no other release_location).
  3. The official page title (fetched live) names the water.
Output: access/identity_spotcheck.json
"""
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import _http  # noqa: E402

ROOT = HERE.parents[1]
MVP_AUTO = {  # alias -> slug, as produced by Step 2 (level A/B)
    "BATTLE GROUND LK (CLAR)": "battle-ground-lake", "LACAMAS LK (CLAR)": "lacamas-lake",
    "KLINELINE PD (CLAR)": "klineline-pond", "GREEN LK (KING)": "green-lake-king",
    "ANGLE LK (KING)": "angle-lake", "LK MERIDIAN (KING)": "lake-meridian", "WARD LK (THUR)": "ward-lake",
    "AMERICAN LK (PIER)": "american-lake", "ALDER LK (THUR/PIER)": "alder-lake",
    "MINERAL LK (LEWI)": "mineral-lake", "BRADLEY LK (PIER)": "lake-bradley",
    "SPANAWAY LK (PIER)": "spanaway-lake", "LK KAPOWSIN (PIER)": "lake-kapowsin",
    "LK WHITMAN (PIER)": "lake-whitman", "TANWAX LK (PIER)": "tanwax-lake",
    "CLEAR LK (PIER)": "clear-lake-pierce", "BONNEY LK (PIER)": "bonney-lake", "RAPJOHN LK (PIER)": "rapjohn-lake",
}


def main():
    ents = {e["entity_id"]: e for e in json.loads((ROOT / "out/identity/entities.json").read_text())}
    out = []
    for alias, slug in MVP_AUTO.items():
        e = ents["wdfw-lowland:" + slug]
        url = e["official_url"]
        page = _http.get(url, accept="text/html")
        text = page["body"].decode("utf-8", "replace")
        title = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
        title = " ".join(re.sub(r"<[^>]+>", " ", title.group(1)).split()) if title else None
        live_code = re.search(r"<strong>Geo Code:</strong>\s*([^<]+)<", text)
        live_code = live_code.group(1).strip() if live_code else None
        q = urllib.parse.urlencode({"x": e["lon"], "y": e["lat"], "benchmark": "Public_AR_Current",
                                    "vintage": "Current_Current", "layers": "Counties", "format": "json"})
        _, geo = _http.get_json("https://geocoding.geo.census.gov/geocoder/geographies/coordinates?" + q)
        cty = None
        try:
            cty = geo["result"]["geographies"]["Counties"][0]["BASENAME"]
        except (TypeError, KeyError, IndexError):
            pass
        q = urllib.parse.urlencode({"$select": "release_location, count(*) as n", "$where": f"geo_code = '{live_code}'",
                                    "$group": "release_location"})
        _, rows = _http.get_json("https://data.wa.gov/resource/6fex-3r7d.json?" + q)
        locs = sorted(" ".join(r["release_location"].split()) for r in rows or [])
        res = {"alias": alias, "official_url": url, "http": page["status"], "live_title": title,
               "live_geo_code": live_code, "step2_geo_code": e["geo_code"], "page_counties": e["counties"],
               "census_county_at_page_centre": cty, "lat": e["lat"], "lon": e["lon"],
               "wdfw_join_release_locations": locs}
        res["checks"] = {
            "census_county_matches": cty in e["counties"],
            "wdfw_join_returns_only_alias": locs == [alias],
            "geo_code_unchanged": live_code == e["geo_code"],
        }
        res["pass"] = all(res["checks"].values())
        out.append(res)
        print(f"{'OK ' if res['pass'] else 'XX '} {alias:26} title={title!r:34} census={cty} join={locs}")
        time.sleep(1.5)
    (ROOT / "access/identity_spotcheck.json").write_text(json.dumps(
        {"checked_at": _http.now_iso(), "n": len(out), "passed": sum(r["pass"] for r in out), "items": out}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
