#!/usr/bin/env python3
"""Build the official canonical-water candidate set from WDFW's own sources.

Sources (all public, no token):
  1. WDFW lowland-lakes search listing (Drupal view, HTML table):
       https://wdfw.wa.gov/fishing/locations/lowland-lakes?name=&page=N
     -> name, page slug, county, acres, elevation, lat/lon
  2. Each lowland-lake profile page:
       https://wdfw.wa.gov/fishing/locations/lowland-lakes/<slug>
     -> "Geo Code", county, center lat/lon, species, and the page's own
        drupalSettings.wdfwSocrataTable.geo_id (the key WDFW's page uses to
        query dataset 6fex-3r7d for "recent fish plants in this lake").
        The page also embeds WDFW's Socrata app token; it is NOT used here.
  3. WDFW GIS (FishWA_2014_AllLakes_PROD MapServer), layers 2 (Lowland
     Lakes) and 21 (High Lakes): structured name/county/point/URL, and for
     high lakes an LCodeWebUse code.

Pages are cached under out/identity/pages/ so re-runs do not re-fetch.

Outputs (gitignored, out/identity/):
  official_lowland_lakes.json   one record per profile page
  gis_lowland_lakes.json        GIS layer 2 features
  gis_high_lakes.json           GIS layer 21 features
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _http  # noqa: E402

BASE = "https://wdfw.wa.gov"
LISTING = BASE + "/fishing/locations/lowland-lakes"
GIS = ("https://geodataservices.wdfw.wa.gov/arcgis/rest/services/"
       "ApplicationServices/FishWA_2014_AllLakes_PROD/MapServer")
OUT = Path(__file__).resolve().parent.parent / "out" / "identity"
PAGES = OUT / "pages"


def cached_get(url, delay):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", url.split("://", 1)[1])[:180] + ".html"
    path = PAGES / name
    if path.exists():
        return path.read_text(encoding="utf-8"), None
    time.sleep(delay)
    res = _http.get(url, accept="text/html")
    if res["status"] != 200:
        return None, res
    text = res["body"].decode("utf-8", "replace")
    path.write_text(text, encoding="utf-8")
    return text, res


def strip(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def parse_listing(text):
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", text, re.S):
        a = re.search(r'href="(/fishing/locations/lowland-lakes/[^"]+)"[^>]*>(.*?)</a>', tr, re.S)
        if not a:
            continue
        cells = {m.group(1): strip(m.group(2)) for m in
                 re.finditer(r'<td headers="view-([a-z-]+?)-table-column"[^>]*>(.*?)</td>', tr, re.S)}
        lat = re.search(r'latlon-lat">([-\d.]+)<', tr)
        lon = re.search(r'latlon-lon">([-\d.]+)<', tr)
        rows.append({"url_path": a.group(1), "listing_name": strip(a.group(2)),
                     "listing_county": cells.get("name"), "listing_acres": cells.get("field-acres"),
                     "listing_elevation": cells.get("field-elevation"),
                     "listing_lat": float(lat.group(1)) if lat else None,
                     "listing_lon": float(lon.group(1)) if lon else None})
    last = max((int(p) for p in re.findall(r"[?&;]page=(\d+)", text)), default=0)
    return rows, last


def stat(text, label):
    m = re.search(r"<strong>" + re.escape(label) + r":</strong>\s*(.*?)<br>", text, re.S)
    return strip(m.group(1)) if m else None


def parse_detail(text):
    title = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
    settings = re.search(r'"wdfwSocrataTable":\{"geo_id":"([^"]*)","is_lowland":(true|false)', text)
    center = stat(text, "Center")
    lat = lon = None
    if center and "," in center:
        try:
            lat, lon = (float(x) for x in center.split(",")[:2])
        except ValueError:
            pass
    species = re.search(r'class="species-list">(.*?)</ul>', text, re.S)
    return {
        "page_title": strip(title.group(1)) if title else None,
        "county": stat(text, "County"),
        "acreage": stat(text, "Acreage"),
        "elevation": stat(text, "Elevation"),
        "geo_code": stat(text, "Geo Code"),
        "page_query_geo_id": settings.group(1) if settings else None,
        "page_query_is_lowland": (settings.group(2) == "true") if settings else None,
        "lat": lat, "lon": lon,
        "species": [strip(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", species.group(1), re.S)] if species else [],
        "canonical_link": (re.search(r'<link rel="canonical" href="([^"]+)"', text) or [None, None])[1],
    }


def gis_layer(layer, out_fields="*"):
    feats, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "1=1", "outFields": out_fields, "returnGeometry": "true",
                                    "outSR": 4326, "f": "json", "resultOffset": offset,
                                    "resultRecordCount": 1000, "orderByFields": "OBJECTID"})
        res, data = _http.get_json(f"{GIS}/{layer}/query?{q}")
        if data is not None and "error" in data:
            # joined-view layers (e.g. High Lakes) reject paging/ordering; their row
            # count is below maxRecordCount (2000), so one plain query suffices
            q = urllib.parse.urlencode({"where": "1=1", "outFields": out_fields, "returnGeometry": "true",
                                        "outSR": 4326, "f": "json"})
            res, data = _http.get_json(f"{GIS}/{layer}/query?{q}")
            if data and data.get("exceededTransferLimit"):
                raise SystemExit(f"GIS layer {layer}: unpaged query truncated")
        if not data or "features" not in data:
            raise SystemExit(f"GIS layer {layer} query failed: {res['status']} {res['error']}")
        for f in data["features"]:
            attrs = {k.split(".")[-1]: v for k, v in f["attributes"].items()}
            g = f.get("geometry") or {}
            feats.append({**attrs, "_lon": g.get("x"), "_lat": g.get("y")})
        if not data.get("exceededTransferLimit"):
            return feats
        offset += len(data["features"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--max-detail", type=int, default=0, help="0 = all")
    args = ap.parse_args()
    PAGES.mkdir(parents=True, exist_ok=True)
    started = _http.now_iso()

    listing, failures, page, last = [], [], 0, 0
    while page <= last:
        url = f"{LISTING}?{urllib.parse.urlencode({'name': '', 'page': page})}"
        text, res = cached_get(url, args.delay)
        if text is None:
            failures.append(_http.loggable(res))
            break
        rows, last = parse_listing(text)
        listing += rows
        page += 1
    print(f"listing: {len(listing)} rows from {page} pages (last index {last})")

    lakes = []
    todo = listing[: args.max_detail] if args.max_detail else listing
    for i, row in enumerate(todo):
        url = BASE + row["url_path"]
        text, res = cached_get(url, args.delay)
        if text is None:
            failures.append(_http.loggable(res))
            continue
        lakes.append({"official_url": url, "slug": row["url_path"].rsplit("/", 1)[-1], **row,
                      **parse_detail(text)})
        if (i + 1) % 50 == 0:
            print(f"  detail {i + 1}/{len(todo)}")

    meta = {"retrieved_started_at": started, "retrieved_finished_at": _http.now_iso(),
            "listing_url": LISTING, "failures": failures}
    (OUT / "official_lowland_lakes.json").write_text(json.dumps({**meta, "lakes": lakes}, indent=1))
    for layer, name in ((2, "gis_lowland_lakes"), (21, "gis_high_lakes")):
        feats = gis_layer(layer)
        (OUT / f"{name}.json").write_text(json.dumps(
            {"retrieved_at": _http.now_iso(), "source_url": f"{GIS}/{layer}", "features": feats}, indent=1))
        print(f"GIS layer {layer}: {len(feats)} features")
    print(f"detail pages parsed: {len(lakes)}; failures: {len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
