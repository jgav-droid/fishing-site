#!/usr/bin/env python3
"""Refresh completed stocking events for the validated waters (Step 1 window strategy).

* Rows are selected by the exact official release_location strings of CONFIRMED aliases,
  never by geo_code: geo_code contamination (e.g. LONG LK (THUR) carries Long's Pond's
  L2818) can therefore never attach stocking to the wrong water.
* A second query looks for NEW release_location names carrying an MVP water's geo_code;
  those go to the review queue, unattached.
* Source: WDFW Fish Plants (6fex-3r7d) = reported/completed plants only. Planned
  stocking (the annual plan PDF) is not ingested at all.
* On failure the previous stocking_events.json is kept and source_status marks the
  failure; last_success does not move (no false freshness).
"""
import argparse
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import METADATA, SODA, _http, content_hash_ids, load, now_iso, save, update_source_status  # noqa: E402

FIELDS = ["release_start_date", "release_end_date", "release_location", "county", "species_type", "species",
          "number_released", "number_of_fish_per_pound", "total_pounds", "lifestage", "facility", "geo_code",
          "agency", "stock", "origin", "run", "brood_year", "release_year", "release_month"]


def q(s):
    return "'" + s.replace("'", "''") + "'"


def soda(params):
    url = SODA + "?" + urllib.parse.urlencode(params)
    res, data = _http.get_json(url, timeout=120)
    if data is None:
        raise RuntimeError(f"{res['status']} {res['error']} for {url[:200]}")
    return data, url


def norm(s):
    return " ".join((s or "").split()).upper()


def main(data_dir=None, window_days=400, today=None):
    today = today or date.today()
    aliases = load("aliases.json", data_dir)
    confirmed = {norm(r): a for a in aliases if a["status"] == "confirmed" for r in a["raw_names"]}
    known = {norm(r) for a in aliases for r in a["raw_names"]} | {norm(a["alias"]) for a in aliases}
    codes = sorted({c for a in aliases if a["status"] == "confirmed" for c in a["stocking_geo_codes"]}
                   | {w["wdfw_geo_code"] for w in load("waters.json", data_dir) if w["wdfw_geo_code"]})
    since = (today - timedelta(days=window_days)).isoformat()
    try:
        meta_res, meta = _http.get_json(METADATA, timeout=60)
        if meta is None:
            raise RuntimeError(f"metadata {meta_res['status']} {meta_res['error']}")
        raws = sorted({r for a in aliases if a["status"] == "confirmed" for r in a["raw_names"]})
        # all official columns (no $select): the content hash must use the same columns as
        # Step 1's normalize.py so IDs are comparable across pipelines
        rows, url = soda({"$where": f"release_location in ({','.join(q(r) for r in raws)}) AND release_start_date >= '{since}'",
                          "$order": "release_start_date DESC", "$limit": 50000})
        others, _ = soda({"$select": "release_location, geo_code, county, max(release_start_date) as latest, count(*) as n",
                          "$where": f"geo_code in ({','.join(q(c) for c in codes)}) AND release_start_date >= '{since}'",
                          "$group": "release_location, geo_code, county", "$limit": 5000})
    except Exception as e:  # keep last-known data
        update_source_status(data_dir, "stocking", False, e)
        print("stocking refresh FAILED; keeping last-known data:", e)
        return 1
    retrieved = now_iso()
    events = []
    for row, cid in zip(rows, content_hash_ids(rows)):
        a = confirmed.get(norm(row["release_location"]))
        if a is None:            # cannot happen given the query, but never attach by guess
            continue
        events.append({"content_hash_id": cid, "water_id": a["water_id"], "alias": a["alias"],
                       "record_kind": "reported_plant", "source_dataset": "data.wa.gov/6fex-3r7d",
                       "release_start_date": row.get("release_start_date", "")[:10],
                       "release_end_date": (row.get("release_end_date") or "")[:10] or None,
                       "species": row.get("species"), "species_type": row.get("species_type"),
                       "number_released": int(float(row.get("number_released") or 0)),
                       "number_of_fish_per_pound": float(row["number_of_fish_per_pound"]) if row.get("number_of_fish_per_pound") not in (None, "") else None,
                       "total_pounds": float(row["total_pounds"]) if row.get("total_pounds") not in (None, "") else None,
                       "lifestage": row.get("lifestage"), "facility": row.get("facility"),
                       "official_release_location": row.get("release_location"), "official_geo_code": row.get("geo_code"),
                       "retrieved_at": retrieved})
    save("stocking_events.json", {"retrieved_at": retrieved, "window_start": since, "source_query_url": url,
                                  "source_page": "https://data.wa.gov/dataset/WDFW-Fish-Plants/6fex-3r7d",
                                  "dataset_rows_updated_at": meta.get("rowsUpdatedAt"), "events": events}, data_dir)
    queue = load("review_queue.json", data_dir) or {"items": []}
    queue["items"] = [i for i in queue["items"] if i.get("kind") != "unmapped_release_location"]
    for o in others:
        if norm(o["release_location"]) not in known:
            queue["items"].append({"kind": "unmapped_release_location", "release_location": o["release_location"],
                                   "geo_code": o.get("geo_code"), "county": o.get("county"), "latest": (o.get("latest") or "")[:10],
                                   "rows": int(o["n"]), "detected_at": retrieved,
                                   "note": "Carries an MVP water's geo_code but is not a confirmed alias: NOT attached. Review before mapping."})
    save("review_queue.json", queue, data_dir)
    update_source_status(data_dir, "stocking", True, extra={"rows_in_window": len(events),
                                                            "dataset_rows_updated_at": meta.get("rowsUpdatedAt")})
    print(f"stocking: {len(events)} events since {since}; review items: "
          f"{sum(i['kind'] == 'unmapped_release_location' for i in queue['items'])}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir")
    ap.add_argument("--window-days", type=int, default=400)
    a = ap.parse_args()
    sys.exit(main(a.data_dir, a.window_days))
