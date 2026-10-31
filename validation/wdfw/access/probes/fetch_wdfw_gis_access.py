#!/usr/bin/env python3
"""Fetch WDFW access-related GIS layers (ArcGIS REST, public, no token) to out/access/.

  ShoreFishingSites/MapServer/0       shore fishing points (LakeName, County, Description)
  MajorFishingArea/MapServer/0        WDFW Water Access Sites (OpenDates, Restrooms, Launch, ADA*, PublicNotes)
  MajorFishingArea/MapServer/1        Public Fishing Pier
"""
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _http  # noqa: E402

G = "https://geodataservices.wdfw.wa.gov/arcgis/rest/services/"
LAYERS = {"shore_fishing_sites": G + "FP_FishMaps/ShoreFishingSites/MapServer/0",
          "water_access_sites": G + "FP_Projects/MajorFishingArea/MapServer/0",
          "public_fishing_piers": G + "FP_Projects/MajorFishingArea/MapServer/1"}


def main():
    out = ROOT / "out" / "access"
    out.mkdir(parents=True, exist_ok=True)
    for name, url in LAYERS.items():
        meta_res, meta = _http.get_json(url + "?f=json")
        q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": 4326, "f": "json"})
        res, data = _http.get_json(f"{url}/query?{q}")
        feats = [{**f["attributes"], "_lon": (f.get("geometry") or {}).get("x"), "_lat": (f.get("geometry") or {}).get("y")}
                 for f in (data or {}).get("features", [])]
        (out / f"{name}.json").write_text(json.dumps({
            "source_url": url, "retrieved_at": res["requested_at"], "status": res["status"],
            "exceededTransferLimit": (data or {}).get("exceededTransferLimit"),
            "fields": [f["name"] for f in (meta or {}).get("fields") or []],
            "editing_info": (meta or {}).get("editingInfo"), "features": feats}, indent=1))
        print(name, res["status"], len(feats), "truncated" if (data or {}).get("exceededTransferLimit") else "")


if __name__ == "__main__":
    main()
