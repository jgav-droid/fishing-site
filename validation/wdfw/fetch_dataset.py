#!/usr/bin/env python3
"""Probe the WDFW Fish Plants dataset (data.wa.gov, id 6fex-3r7d).

Every request goes to an ordinary, documented public Socrata endpoint and is
logged (status, redirects, content type, size, headers). Nothing is assumed
about the schema: column names are read from the dataset metadata.

Outputs:
  out/probe_log.jsonl          every request (gitignored)
  out/dataset_probe.json       machine summary of the run (gitignored)
  samples/schema_6fex-3r7d.json  column list from the metadata endpoint
  samples/raw_sample.json      newest N rows, verbatim, with retrieval context
  samples/raw_sample.csv       same query as CSV, verbatim

Usage:
  python3 fetch_dataset.py [--date-field FIELD] [--sample 200] [--repeat 3]
                           [--full-bulk]   # also download the whole export
"""
import argparse
import csv
import hashlib
import io
import json
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import os

import _http

# WDFW_TEST_BASE: point at a local mock for smoke-testing the script only.
DOMAIN = os.environ.get("WDFW_TEST_BASE", "https://data.wa.gov")
DATASET = "6fex-3r7d"
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SAMPLES = HERE / "samples"

ENDPOINTS = {
    "metadata": f"{DOMAIN}/api/views/{DATASET}.json",
    "soda_json": f"{DOMAIN}/resource/{DATASET}.json",
    "soda_csv": f"{DOMAIN}/resource/{DATASET}.csv",
    "bulk_csv": f"{DOMAIN}/api/views/{DATASET}/rows.csv?accessType=DOWNLOAD",
    "bulk_json_v2": f"{DOMAIN}/api/views/{DATASET}/rows.json?accessType=DOWNLOAD",
    "bulk_json_v3": f"{DOMAIN}/api/v3/views/{DATASET}/query.json?accessType=DOWNLOAD",
}
DATE_TYPES = {"calendar_date", "floating_timestamp", "date", "fixed_timestamp"}

log_fh = None


def log(step, res, **extra):
    entry = {"step": step, **_http.loggable(res), **extra}
    log_fh.write(json.dumps(entry) + "\n")
    log_fh.flush()
    status = res["status"] if res["status"] is not None else res["error_kind"]
    print(f"[{step}] {status} {res['bytes_read']}B {res['content_type'] or ''} {res['url']}")
    return entry


def soql(base, **params):
    return base + "?" + urllib.parse.urlencode({f"${k}": v for k, v in params.items()})


def epoch_iso(v):
    if v in (None, ""):
        return None
    return datetime.fromtimestamp(int(v), timezone.utc).isoformat()


def schema_hash(fields):
    return hashlib.sha256(",".join(fields).encode()).hexdigest()[:16]


def main():
    global log_fh
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-field", help="stocking-date column (fieldName); auto if exactly one date column")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--repeat-interval", type=float, default=10.0)
    ap.add_argument("--bulk-cap-mb", type=float, default=2.0, help="bytes read from bulk exports unless --full-bulk")
    ap.add_argument("--full-bulk", action="store_true", help="download full bulk CSV into out/ (not committed)")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    SAMPLES.mkdir(exist_ok=True)
    log_fh = open(OUT / "probe_log.jsonl", "a")
    run = {"run_started_at": _http.now_iso(), "dataset": DATASET, "endpoints": ENDPOINTS, "steps": {}}
    steps = run["steps"]

    # 1. Metadata / schema -------------------------------------------------
    res, meta = _http.get_json(ENDPOINTS["metadata"])
    steps["metadata"] = log("metadata", res)
    if meta is None:
        run["fatal"] = f"metadata unavailable: {res['error_kind']} {res['error']}"
        (OUT / "dataset_probe.json").write_text(json.dumps(run, indent=2))
        print("FATAL:", run["fatal"], file=sys.stderr)
        return 2
    columns = [
        {
            "fieldName": c.get("fieldName"),
            "name": c.get("name"),
            "dataTypeName": c.get("dataTypeName"),
            "description": c.get("description"),
            "cachedContents": {
                k: c.get("cachedContents", {}).get(k)
                for k in ("non_null", "null", "smallest", "largest", "cardinality")
                if k in c.get("cachedContents", {})
            },
        }
        for c in meta.get("columns", [])
    ]
    row_id_col = meta.get("rowIdentifierColumnId")
    row_id_field = next((c.get("fieldName") for c in meta.get("columns", []) if c.get("id") == row_id_col), None)
    timestamps = {
        k: epoch_iso(meta.get(k))
        for k in ("createdAt", "publicationDate", "rowsUpdatedAt", "viewLastModified", "indexUpdatedAt")
    }
    run["metadata"] = {
        "name": meta.get("name"),
        "attribution": meta.get("attribution"),
        "description": meta.get("description"),
        "category": meta.get("category"),
        "timestamps_utc": timestamps,
        "row_identifier_field": row_id_field,
        "update_frequency": (meta.get("metadata", {}).get("custom_fields", {}) or {}),
        "column_count": len(columns),
    }
    (SAMPLES / f"schema_{DATASET}.json").write_text(
        json.dumps({"retrieved_at": res["requested_at"], "source_url": ENDPOINTS["metadata"],
                    "timestamps_utc": timestamps, "row_identifier_field": row_id_field,
                    "columns": columns}, indent=2)
    )
    field_names = [c["fieldName"] for c in columns]
    date_fields = [c["fieldName"] for c in columns if c["dataTypeName"] in DATE_TYPES]
    run["date_fields"] = date_fields

    if args.date_field:
        if args.date_field not in field_names:
            print(f"--date-field {args.date_field} not in schema {field_names}", file=sys.stderr)
            return 2
        date_field, how = args.date_field, "explicit"
    elif len(date_fields) == 1:
        date_field, how = date_fields[0], "only date column"
    elif date_fields:
        date_field, how = date_fields[0], f"UNCONFIRMED first of {date_fields}; rerun with --date-field"
    else:
        date_field, how = None, "no date-typed column found"
    run["date_field"] = {"field": date_field, "chosen_by": how}
    print(f"date field: {date_field} ({how})")

    # 2. Row count ---------------------------------------------------------
    res, data = _http.get_json(soql(ENDPOINTS["soda_json"], select="count(*) as n"))
    steps["count"] = log("count", res)
    run["row_count"] = int(data[0]["n"]) if data else None

    # 3. Date coverage, per date column ------------------------------------
    today = date.today().isoformat()
    run["date_coverage"] = {}
    for f in date_fields:
        res, data = _http.get_json(soql(ENDPOINTS["soda_json"],
                                        select=f"min({f}) as min, max({f}) as max, count({f}) as n"))
        log(f"coverage:{f}", res)
        cov = data[0] if data else None
        res, data = _http.get_json(soql(ENDPOINTS["soda_json"], select="count(*) as n",
                                        where=f"{f} > '{today}T23:59:59'"))
        log(f"future:{f}", res)
        if cov is not None:
            cov["rows_after_today"] = int(data[0]["n"]) if data else None
        run["date_coverage"][f] = cov

    # 4. Newest-N sample, JSON (with Socrata system fields) and CSV ---------
    order = f"{date_field} DESC, :id" if date_field else ":id"
    json_url = soql(ENDPOINTS["soda_json"], select=":*, *", order=order, limit=args.sample)
    res, rows = _http.get_json(json_url)
    steps["sample_json"] = log("sample_json", res, rows=len(rows) if rows else 0)
    if rows:
        (SAMPLES / "raw_sample.json").write_text(json.dumps(
            {"retrieved_at": res["requested_at"], "source_url": json_url,
             "soda2_fields_header": res["headers"].get("x-soda2-fields"),
             "rows": rows}, indent=2))
    csv_url = soql(ENDPOINTS["soda_csv"], order=order, limit=args.sample)
    res = _http.get(csv_url, accept="text/csv")
    csv_rows = list(csv.DictReader(io.StringIO(res["body"].decode("utf-8", "replace")))) if res["status"] == 200 else []
    steps["sample_csv"] = log("sample_csv", res, rows=len(csv_rows))
    if res["status"] == 200:
        (SAMPLES / "raw_sample.csv").write_bytes(res["body"])
        run["csv_header"] = list(csv_rows[0].keys()) if csv_rows else None
        run["csv_header_matches_schema"] = sorted(run["csv_header"] or []) == sorted(field_names)

    # 5. Pagination behaviour ----------------------------------------------
    res, data = _http.get_json(ENDPOINTS["soda_json"])  # no $limit
    steps["default_page"] = log("default_page", res, rows=len(data) if data else 0)
    run["default_page_rows"] = len(data) if data else None
    pages = []
    for off in (0, 100):
        res, data = _http.get_json(soql(ENDPOINTS["soda_json"], select=":id", order=":id", limit=100, offset=off))
        log(f"page_offset_{off}", res)
        pages.append({r[":id"] for r in data} if data else set())
    run["offset_paging"] = {"page_sizes": [len(p) for p in pages], "overlap": len(pages[0] & pages[1])}

    # 6. Incremental-query feasibility --------------------------------------
    since = (date.today() - timedelta(days=30)).isoformat()
    inc = {}
    if date_field:
        url = soql(ENDPOINTS["soda_json"], select="count(*) as n", where=f"{date_field} >= '{since}'")
        res, data = _http.get_json(url)
        log("incremental_by_date", res)
        inc["by_stocking_date_since"] = {"since": since, "url": url, "rows": int(data[0]["n"]) if data else None,
                                         "status": res["status"], "bytes": res["bytes_read"]}
    url = soql(ENDPOINTS["soda_json"], select="count(*) as n", where=f":updated_at >= '{since}'")
    res, data = _http.get_json(url)
    log("incremental_by_updated_at", res)
    inc["by_system_updated_at_since"] = {"since": since, "url": url, "rows": int(data[0]["n"]) if data else None,
                                         "status": res["status"], "error": res["error"]}
    res, data = _http.get_json(soql(ENDPOINTS["soda_json"], select="max(:updated_at) as u, min(:updated_at) as l"))
    log("updated_at_range", res)
    inc["system_updated_at_range"] = data[0] if data else None
    run["incremental"] = inc

    # 7. Bulk exports (capped unless --full-bulk) -----------------------------
    cap = int(args.bulk_cap_mb * 1024 * 1024)
    run["bulk"] = {}
    for key in ("bulk_csv", "bulk_json_v2", "bulk_json_v3"):
        if key == "bulk_csv" and args.full_bulk:
            with open(OUT / "full_export.csv", "wb") as fh:
                res = _http.get(ENDPOINTS[key], sink=fh, timeout=600)
            with open(OUT / "full_export.csv", newline="", encoding="utf-8", errors="replace") as fh:
                n = sum(1 for _ in csv.reader(fh)) - 1
            log(key, res, full=True, rows=n)
            run["bulk"][key] = {"status": res["status"], "bytes": res["bytes_read"], "rows": n,
                                "content_type": res["content_type"], "error": res["error"]}
        else:
            res = _http.get(ENDPOINTS[key], max_bytes=cap)
            log(key, res, capped_at=cap)
            run["bulk"][key] = {"status": res["status"], "bytes_read": res["bytes_read"],
                                "truncated": res["truncated"], "content_length": res["content_length_header"],
                                "content_type": res["content_type"], "redirects": res["redirects"],
                                "error": res["error"], "preview": res["body"][:200].decode("utf-8", "replace")}

    # 8. Repeated reads: stability -----------------------------------------
    run["repeats"] = []
    for i in range(args.repeat):
        if i:
            time.sleep(args.repeat_interval)
        r1, m = _http.get_json(ENDPOINTS["metadata"])
        log(f"repeat{i}:metadata", r1)
        r2, c = _http.get_json(soql(ENDPOINTS["soda_json"], select="count(*) as n"))
        log(f"repeat{i}:count", r2)
        r3, s = _http.get_json(soql(ENDPOINTS["soda_json"], order=order, limit=5))
        log(f"repeat{i}:head5", r3)
        fields_hdr = r3["headers"].get("x-soda2-fields")
        run["repeats"].append({
            "at": r1["requested_at"],
            "statuses": [r1["status"], r2["status"], r3["status"]],
            "rowsUpdatedAt": epoch_iso(m.get("rowsUpdatedAt")) if m else None,
            "column_hash": schema_hash([x.get("fieldName") for x in m.get("columns", [])]) if m else None,
            "count": int(c[0]["n"]) if c else None,
            "soda2_fields": fields_hdr,
            "rate_limit_headers": {k: v for k, v in r3["headers"].items() if "ratelimit" in k or "retry" in k},
        })

    run["run_finished_at"] = _http.now_iso()
    (OUT / "dataset_probe.json").write_text(json.dumps(run, indent=2, default=str))
    print(f"wrote {OUT / 'dataset_probe.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
