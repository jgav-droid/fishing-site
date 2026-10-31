#!/usr/bin/env python3
"""Write small committed samples from the gitignored identity outputs.

samples/canonical_waters_sample.json   official entities touched by the validation sample
samples/aliases_sample.json            stocking name -> entity pairs (A/B) a water_aliases table would hold
samples/review_queue_sample.json       C/D decisions (validation sample + 60 random others)
samples/stocking_locations_sample.json inventory rows for the validation sample
samples/geo_code_profile.json          geo_code statistics + multi-name / multi-county codes
samples/match_summary.json             level/method counts over ALL stocking locations
"""
import json
import random
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out" / "identity"
SAMPLES = HERE / "samples"


def main():
    SAMPLES.mkdir(exist_ok=True)
    matches = json.loads((OUT / "matches.json").read_text())
    by_key = {m["location_key"]: m for m in matches}
    ents = {e["entity_id"]: e for e in json.loads((OUT / "entities.json").read_text())}
    locs = {L["location_key"]: L for L in json.loads((OUT / "stocking_locations.json").read_text())}
    sample = json.loads((HERE / "validation_sample.json").read_text())["items"]
    keys = [s["location_key"] for s in sample]

    touched = set()
    for k in keys:
        m = by_key[k]
        if m.get("entity_id"):
            touched.add(m["entity_id"])
        touched.update(c["entity_id"] for c in m.get("candidates", []))
    touched.update(s["truth"] for s in sample if s["truth"] in ents)
    keep = ("entity_id", "source", "canonical_name", "county", "counties", "geo_code", "official_url",
            "lat", "lon", "fishwa_id", "corroborating_sources", "name_key")
    (SAMPLES / "canonical_waters_sample.json").write_text(json.dumps(
        [{k: ents[e].get(k) for k in keep if k in ents[e]} for e in sorted(touched)], indent=1))

    aliases = [{"entity_id": m["entity_id"], "alias": m["location_key"],
                "county_context": m["county_evidence"], "geo_code": m["geo_code"],
                "source": "6fex-3r7d release_location", "level": m["level"], "method": m["method"]}
               for m in matches if m["level"] in ("A", "B")]
    random.seed(20261031)
    (SAMPLES / "aliases_sample.json").write_text(json.dumps(
        {"total_A_B_aliases": len(aliases),
         "sample": sorted([a for a in aliases if a["alias"] in keys] + random.sample(aliases, 60),
                          key=lambda a: a["alias"])}, indent=1))

    review = [m for m in matches if m["level"] in ("C", "D")]
    pick = [m for m in review if m["location_key"] in keys]
    pick += random.sample([m for m in review if m["location_key"] not in keys], 60)
    (SAMPLES / "review_queue_sample.json").write_text(json.dumps(
        {"total_review": len(review), "sample": sorted(pick, key=lambda m: m["location_key"])}, indent=1))

    (SAMPLES / "stocking_locations_sample.json").write_text(json.dumps([locs[k] for k in keys], indent=1))
    prof = json.loads((OUT / "geo_code_profile.json").read_text())
    (SAMPLES / "geo_code_profile.json").write_text(json.dumps(prof, indent=1))
    (SAMPLES / "match_summary.json").write_text(json.dumps({
        "locations": len(matches),
        "locations_by_level": dict(sorted(Counter(m["level"] for m in matches).items())),
        "rows_by_level": {lvl: sum(m["rows"] for m in matches if m["level"] == lvl)
                          for lvl in ("A", "B", "C", "D", "NONE")},
        "methods": dict(Counter(m["method"] for m in matches).most_common()),
        "official_entities": dict(Counter(e["source"] for e in ents.values())),
    }, indent=1))
    print("wrote", sorted(p.name for p in SAMPLES.iterdir()))


if __name__ == "__main__":
    main()
