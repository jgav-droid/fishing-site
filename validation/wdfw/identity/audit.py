#!/usr/bin/env python3
"""Score the matcher against the manually audited validation sample.

Inputs:
  identity/validation_sample.json   hand-labelled ground truth (committed)
  out/identity/matches.json         matcher output
Outputs:
  identity/audit_results.json       per-item outcome + metrics (committed)

Truth labels:
  "<entity_id>"           the correct official entity
  "NO_OFFICIAL_ENTITY"    the water has no official lowland page / GIS high-lake entity
  "UNDECIDABLE"           official sources do not let even a reviewer decide

Outcomes:
  exact_correct          A, entity == truth
  alias_correct          B, entity == truth
  FALSE_CONFIDENT        A/B, entity != truth           <- must be zero
  review_truth_listed    C/D, truth among candidates (or truth is NO_OFFICIAL_ENTITY/UNDECIDABLE)
  review_truth_missing   C/D, truth is an entity not among candidates (safe; reviewer must search)
  review_wrong_top       C, suggested entity != truth (safe, but a misleading suggestion)
  none_correct           NONE, truth NO_OFFICIAL_ENTITY
  none_unresolved_safe   NONE, truth UNDECIDABLE (left unattached)
  none_missed            NONE, truth is an entity (not attached; not a false match)
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out" / "identity"


def outcome(m, truth):
    lvl, ent = m["level"], m.get("entity_id")
    cands = {c["entity_id"] for c in m.get("candidates", [])}
    if lvl in ("A", "B"):
        if ent == truth:
            return "exact_correct" if lvl == "A" else "alias_correct"
        return "FALSE_CONFIDENT"
    if lvl == "NONE":
        return {"NO_OFFICIAL_ENTITY": "none_correct", "UNDECIDABLE": "none_unresolved_safe"}.get(truth, "none_missed")
    if lvl == "C" and ent and ent != truth:
        return "review_wrong_top"
    if truth in ("NO_OFFICIAL_ENTITY", "UNDECIDABLE") or truth in cands or ent == truth:
        return "review_truth_listed"
    return "review_truth_missing"


def main():
    sample = json.loads((HERE / "validation_sample.json").read_text())
    matches = {m["location_key"]: m for m in json.loads((OUT / "matches.json").read_text())}
    items = []
    for s in sample["items"]:
        m = matches.get(s["location_key"])
        if m is None:
            sys.exit(f"sample location not in matches: {s['location_key']}")
        o = outcome(m, s["truth"])
        items.append({"category": s["category"], "location_key": s["location_key"], "truth": s["truth"],
                      "truth_basis": s["truth_basis"], "level": m["level"], "method": m["method"],
                      "matched_entity": m.get("entity_id"), "canonical_name": m.get("canonical_name"),
                      "county": m.get("county"), "official_url": m.get("official_url"),
                      "lat": m.get("lat"), "lon": m.get("lon"), "evidence": m["evidence"],
                      "candidates": [c["entity_id"] for c in m.get("candidates", [])],
                      "review_required": m["review_required"], "outcome": o})
    n = len(items)
    oc = Counter(i["outcome"] for i in items)
    automated = sum(1 for i in items if i["level"] in ("A", "B"))
    review = sum(1 for i in items if i["level"] in ("C", "D"))
    safe = sum(oc[k] for k in ("exact_correct", "alias_correct", "review_truth_listed",
                               "review_truth_missing", "review_wrong_top", "none_correct", "none_unresolved_safe"))
    mvp = [i for i in items if i["category"] == "mvp"]
    # the MVP list names 20 waters; "Martha Lake (Snohomish County)" covers two official
    # lakes, so that MVP item counts as automated-correct only if both rows are
    martha = [i for i in mvp if i["location_key"].startswith("MARTHA LK (")]
    auto_ok = lambda i: i["outcome"] in ("exact_correct", "alias_correct")
    mvp_items_ok = sum(1 for i in mvp if i not in martha and auto_ok(i)) + (1 if martha and all(map(auto_ok, martha)) else 0)
    mvp_items_review = sum(1 for i in mvp if i not in martha and i["review_required"]) + (1 if any(i["review_required"] for i in martha) else 0)
    metrics = {
        "sample_size": n, "by_category": dict(Counter(i["category"] for i in items)),
        "outcomes": dict(oc),
        "false_confident_matches": oc["FALSE_CONFIDENT"],
        "false_positive_rate_of_automated": round(oc["FALSE_CONFIDENT"] / automated, 4) if automated else 0.0,
        "automated_match_rate": round(automated / n, 4),
        "review_rate": round(review / n, 4),
        "none_rate": round(sum(1 for i in items if i["level"] == "NONE") / n, 4),
        "safe_rate": round(safe / n, 4),
        "mvp_rows": len(mvp),
        "mvp_rows_correct_automated": sum(1 for i in mvp if auto_ok(i)),
        "mvp_items_total": len(mvp) - len(martha) + (1 if martha else 0),
        "mvp_items_correct_automated": mvp_items_ok,
        "mvp_items_routed_to_review": mvp_items_review,
        "mvp_false_confident": sum(1 for i in mvp if i["outcome"] == "FALSE_CONFIDENT"),
        "levels": dict(Counter(i["level"] for i in items)),
    }
    (HERE / "audit_results.json").write_text(json.dumps({"metrics": metrics, "items": items}, indent=1))
    print(json.dumps(metrics, indent=1))
    for i in items:
        flag = "!!" if i["outcome"] in ("FALSE_CONFIDENT", "none_missed") else "  "
        print(f"{flag} {i['category']:10} {i['location_key']:30} {i['level']:4} {i['outcome']:20} -> "
              f"{i['matched_entity'] or '-'} | truth {i['truth']}")
    return 1 if oc["FALSE_CONFIDENT"] else 0


if __name__ == "__main__":
    sys.exit(main())
