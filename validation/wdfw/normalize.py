#!/usr/bin/env python3
"""Normalize raw Fish Plants rows into a simple structure, and run quality checks.

The mapping from official columns to normalized keys lives in field_map.json
and must reference fieldNames that exist in samples/schema_6fex-3r7d.json.
A target mapped to null is left OUT of the normalized record (never inferred).

  python3 normalize.py --propose   # suggest a mapping from the real schema
                                   # -> field_map.proposed.json (review it!)
  python3 normalize.py             # uses field_map.json

Outputs:
  samples/normalized_sample.json
  samples/quality.json
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples"
SCHEMA = SAMPLES / "schema_6fex-3r7d.json"
RAW = SAMPLES / "raw_sample.json"
MAP = HERE / "field_map.json"

# Keyword hints used ONLY by --propose to shortlist real columns for review.
HINTS = {
    "water_name": ["release_location", "water", "lake", "location", "site"],
    "county": ["county"],
    "stocking_date": ["release_date", "release_start", "plant_date", "stock_date", "date"],
    "species": ["species"],
    "quantity": ["number", "count", "quantity", "released", "num_"],
    "size_or_weight": ["per_lb", "fish_per", "size", "weight", "lbs", "pounds", "life", "stage"],
    "hatchery_or_source": ["hatchery", "facility", "source", "origin"],
    "latitude": ["lat"],
    "longitude": ["lon", "lng", "long"],
    "water_id": ["wria", "llid", "water_id", "location_id", "waterbody_id", "site_id"],
    "record_id": ["record_id", "release_id", "plant_id", "id"],
    "stocking_end_date": ["end_date", "release_end"],
}


def propose():
    schema = json.loads(SCHEMA.read_text())
    cols = schema["columns"]
    proposal = {"_record_kind": "UNCONFIRMED", "_notes": "Proposed from keyword hints. Review every entry."}
    for target, hints in HINTS.items():
        hits = [c for c in cols
                if any(h in (c["fieldName"] or "").lower() or h in (c["name"] or "").lower() for h in hints)]
        proposal[target] = {"candidates": [
            {"fieldName": c["fieldName"], "name": c["name"], "type": c["dataTypeName"],
             "description": c.get("description")} for c in hits]}
    out = HERE / "field_map.proposed.json"
    out.write_text(json.dumps(proposal, indent=2))
    print(f"wrote {out}. Copy confirmed fieldNames into field_map.json (string, list for size_or_weight, or null).")


def clean_text(v):
    if v is None:
        return None
    s = " ".join(str(v).split())
    return s or None


def parse_date(v):
    # Socrata calendar_date / floating_timestamp: 2026-10-15T00:00:00.000
    if not v:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(T[\d:.]+)?$", str(v))
    return m.group(1) if m else None


def parse_int(v):
    if v is None or v == "":
        return None
    try:
        f = float(str(v).replace(",", ""))
    except ValueError:
        return None
    return int(f) if f.is_integer() else None


def parse_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize(fmap, raw):
    schema_fields = {c["fieldName"] for c in json.loads(SCHEMA.read_text())["columns"]}
    used = []
    for k, v in fmap.items():
        if k.startswith("_") or not v:
            continue
        used += v if isinstance(v, list) else [v]
    missing = [f for f in used if f not in schema_fields]
    if missing:
        sys.exit(f"field_map.json references fields not in the official schema: {missing}")
    if fmap.get("_record_kind") in (None, "UNCONFIRMED"):
        sys.exit("field_map.json: set _record_kind (e.g. reported_plant) after reviewing the source semantics")

    retrieved_at, source_url = raw["retrieved_at"], raw["source_url"]
    records, issues = [], []
    seen = Counter()
    for i, row in enumerate(raw["rows"]):
        if fmap.get("record_id"):
            rid, kind = row.get(fmap["record_id"]), "dataset_column"
        else:
            # No official row key, and Socrata :id is regenerated on every full
            # refresh, so derive one from the official columns. Identical rows
            # (they exist) get an occurrence suffix.
            content = json.dumps({k: v for k, v in sorted(row.items()) if not k.startswith(":")})
            h = hashlib.sha256(content.encode()).hexdigest()[:20]
            seen[h] += 1
            rid, kind = f"{h}-{seen[h]}", "content_hash"
        rec = {"source_record_id": rid, "source_record_id_kind": kind,
               "record_kind": fmap["_record_kind"], "source": "WDFW", "source_dataset": "data.wa.gov/6fex-3r7d"}
        for key in ("water_name", "county", "species", "hatchery_or_source", "water_id"):
            if fmap.get(key):
                rec[key] = clean_text(row.get(fmap[key]))
        for key in ("stocking_date", "stocking_end_date"):
            if fmap.get(key):
                raw_v = row.get(fmap[key])
                rec[key] = parse_date(raw_v)
                if raw_v and rec[key] is None:
                    issues.append({"row": i, "field": key, "issue": "unparseable", "value": raw_v})
        if rec.get("stocking_end_date") and rec.get("stocking_date") and rec["stocking_end_date"] < rec["stocking_date"]:
            issues.append({"row": i, "field": "stocking_end_date", "issue": "before start date",
                           "value": [rec["stocking_date"], rec["stocking_end_date"]]})
        if fmap.get("quantity"):
            raw_v = row.get(fmap["quantity"])
            rec["quantity"] = parse_int(raw_v)
            if raw_v not in (None, "") and rec["quantity"] is None:
                issues.append({"row": i, "field": "quantity", "issue": "not an integer", "value": raw_v})
        if fmap.get("size_or_weight"):
            fields = fmap["size_or_weight"] if isinstance(fmap["size_or_weight"], list) else [fmap["size_or_weight"]]
            # keep the official column names: these measures differ in meaning
            rec["size_or_weight"] = {f: row.get(f) for f in fields if row.get(f) not in (None, "")} or None
        for key in ("latitude", "longitude"):
            if fmap.get(key):
                rec[key] = parse_float(row.get(fmap[key]))
        extra = {f: clean_text(row.get(f)) for f in fmap.get("official_extra") or [] if clean_text(row.get(f))}
        if extra:
            rec["official_extra"] = extra
        rec["source_url"] = source_url
        rec["retrieved_at"] = retrieved_at
        records.append(rec)
    return records, issues


def quality(records, issues, retrieved_at):
    q = {"records": len(records), "row_level_issues": issues[:50], "row_level_issue_count": len(issues)}
    keys = sorted({k for r in records for k in r})
    q["null_counts"] = {k: sum(1 for r in records if r.get(k) in (None, "")) for k in keys}
    today = retrieved_at[:10]
    dates = sorted(r["stocking_date"] for r in records if r.get("stocking_date"))
    q["stocking_date_range_in_sample"] = [dates[0], dates[-1]] if dates else None
    q["future_dated_records"] = [r for r in records if (r.get("stocking_date") or "") > today][:20]
    qty = [r["quantity"] for r in records if isinstance(r.get("quantity"), int)]
    q["quantity"] = {"min": min(qty), "max": max(qty), "zero_or_negative": sum(1 for x in qty if x <= 0)} if qty else None
    ids = Counter(r["source_record_id"] for r in records)
    q["duplicate_source_ids"] = [k for k, n in ids.items() if n > 1][:20]
    sig = Counter((r.get("water_name"), r.get("stocking_date"), r.get("species"), r.get("quantity")) for r in records)
    q["duplicate_content_rows"] = [list(k) for k, n in sig.items() if n > 1][:20]
    q["distinct"] = {k: len({r.get(k) for r in records}) for k in ("water_name", "county", "species", "hatchery_or_source") if k in keys}
    q["species_values"] = sorted({r.get("species") for r in records if r.get("species")})
    q["county_values"] = sorted({r.get("county") for r in records if r.get("county")})
    q["water_names_with_parenthetical_or_codes"] = sorted(
        {r["water_name"] for r in records if r.get("water_name") and re.search(r"[()#/]|\d{2,}", r["water_name"])})[:30]
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--propose", action="store_true")
    args = ap.parse_args()
    if args.propose:
        return propose()
    fmap = json.loads(MAP.read_text())
    raw = json.loads(RAW.read_text())
    records, issues = normalize(fmap, raw)
    (SAMPLES / "normalized_sample.json").write_text(json.dumps(records, indent=2))
    q = quality(records, issues, raw["retrieved_at"])
    (SAMPLES / "quality.json").write_text(json.dumps(q, indent=2))
    print(f"normalized {len(records)} records; {len(issues)} row-level issues; "
          f"{len(q['future_dated_records'])} future-dated; sample date range {q['stocking_date_range_in_sample']}")


if __name__ == "__main__":
    sys.exit(main())
