#!/usr/bin/env python3
"""Proof-of-concept parser for WDFW water access site pages (one template, 472 sites).

  listing: https://wdfw.wa.gov/places-to-go/water-access-sites?combine=&page=N  (19 pages)
  detail:  https://wdfw.wa.gov/places-to-go/water-access-sites/<name>-<id>

Parses: title, county, "Access area open", ramps, ramp surface, ADA loading platform,
boarding float, hand launches, fishing platforms, parking lots, restrooms, ADA restrooms,
camping, lat/lon. Fetches detail pages only for sites within --km of an MVP lake centre.
Cached under out/access/pages/. Output: out/access/wdfw_access_sites_mvp.json
"""
import argparse
import html
import json
import math
import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _http  # noqa: E402

BASE = "https://wdfw.wa.gov"
CACHE = ROOT / "out" / "access" / "pages"
LABELS = ["Access area open", "Number of ramps", "Ramp surface", "ADA loading platform", "Boarding float",
          "Hand launches", "Fishing platforms", "Parking lots", "Restrooms", "ADA restrooms", "Camping allowed"]


GENERIC = {"lake", "lakes", "pond", "county", "the", "access", "area"}


def cached(url, delay=1.5):
    p = CACHE / (re.sub(r"[^A-Za-z0-9_.-]+", "_", url.split("://", 1)[1])[:180] + ".html")
    if p.exists():
        return p.read_text(encoding="utf-8")
    time.sleep(delay)
    r = _http.get(url, accept="text/html")
    if r["status"] != 200:
        raise SystemExit(f"{r['status']} {r['error']} {url}")
    t = r["body"].decode("utf-8", "replace")
    p.write_text(t, encoding="utf-8")
    return t


def text_lines(s):
    b = re.search(r"<main.*?</main>", s, re.S).group(0)
    b = re.sub(r"<script.*?</script>|<style.*?</style>", "", b, flags=re.S)
    return [x.strip() for x in html.unescape(re.sub(r"<[^>]+>", "\n", b)).split("\n") if x.strip()]


def parse_detail(s):
    lines = text_lines(s)
    rec = {"title": lines[0] if lines else None, "county": lines[1] if len(lines) > 1 else None}
    for lab in LABELS:
        for i, ln in enumerate(lines):
            if ln.rstrip(":") == lab and i + 1 < len(lines):
                rec[lab] = lines[i + 1]
                break
    lat = re.search(r'"lat":(-?[\d.]+)', s)
    lon = re.search(r'"lon":(-?[\d.]+)', s)
    rec["lat"], rec["lon"] = (float(lat.group(1)) if lat else None), (float(lon.group(1)) if lon else None)
    return rec


def km(a, b, c, d):
    return math.hypot((a - c) * 111.0, (b - d) * 111.0 * math.cos(math.radians(a)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--km", type=float, default=4.0)
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    sites, page, last = {}, 0, 0
    while page <= last:
        s = cached(f"{BASE}/places-to-go/water-access-sites?{urllib.parse.urlencode({'combine': '', 'page': page})}")
        for href, name in re.findall(r'href="(/places-to-go/water-access-sites/[^"]+)" hreflang="en">([^<]+)<', s):
            sites[href] = html.unescape(name)
        last = max([last] + [int(x) for x in re.findall(r"page=(\d+)", s)])
        page += 1
    print("listing:", len(sites), "sites over", page, "pages")
    ents = {e["entity_id"]: e for e in json.loads((ROOT / "out/identity/entities.json").read_text())}
    mvp = json.loads((ROOT / "access/mvp_waters.json").read_text())
    out = {}
    for w in mvp:
        e = ents[w["entity_id"]]
        # name agreement is required, not just proximity: the site's core name must be
        # contained in the lake's (Long Lake's access site is 2 km from Long's Pond)
        core = lambda n: set(re.findall(r"[a-z]+", n.lower().replace("'", ""))) - GENERIC
        lake_core = core(w["name"])
        cands = [h for h, n in sites.items() if core(n) and core(n) <= lake_core]
        found = []
        for h in cands:
            rec = parse_detail(cached(BASE + h))
            if rec["lat"] is None:
                continue
            d = km(e["lat"], e["lon"], rec["lat"], rec["lon"])
            if d <= args.km:
                found.append({"url": BASE + h, "distance_km_from_lake_centre": round(d, 2), **rec})
        out[w["water_id"]] = found
        print(f"{w['name']:30} {len(found)} site(s): {[(f['title'], f.get('Access area open'), f['distance_km_from_lake_centre']) for f in found]}")
    (ROOT / "out/access/wdfw_access_sites_mvp.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
