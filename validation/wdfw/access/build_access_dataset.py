#!/usr/bin/env python3
"""Assemble the 20-lake access dataset with per-field provenance, and compute coverage.

Inputs (cached by the probes; gitignored under out/):
  out/identity/pages/*        WDFW lowland-lake pages (Step 2 crawl)
  out/access/pages/*          WDFW access-site pages + land-manager pages
  out/access/*.json           WDFW GIS layers, joins, manager page metadata
  out/access/er.html, algae.html
  access/curated_facts.py     hand-curated states + verbatim evidence quotes
Outputs (committed):
  access/access_dataset.json
  access/coverage_report.json

Every evidence quote must occur in its cached source (case/whitespace/punctuation
normalized) or the build fails: provenance is checked, not asserted.
"""
import glob
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from curated_facts import FACTS  # noqa: E402

OUT = ROOT / "out"
CORE_FIELDS = ["bank_fishing_status", "public_access", "parking_available", "pass_or_fee"]
LAKE_FIELDS = ["bank_fishing_status", "fishing_pier_or_dock"]
AP_FIELDS = ["public_access", "parking_available", "parking_or_access_fee", "pass_required",
             "operating_hours", "seasonal_access", "closure_channel"]


def norm(s):
    s = html.unescape(s)
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("–", "-").replace("—", "-").replace("\xa0", " "))
    return " ".join(s.split()).lower()


def page_text(path):
    s = Path(path).read_text(encoding="utf-8")
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    return norm(re.sub(r"<[^>]+>", " ", s))


def cache_name(url):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", url.split("://", 1)[1])[:180] + ".html"


class Sources:
    def __init__(self):
        self.texts, self.meta = {}, {}
        self.gis = {int(f["AccessSiteID"]): f for f in json.loads((OUT / "access/shore_fishing_sites.json").read_text())["features"]
                    if f.get("AccessSiteID")}
        self.gis_meta = json.loads((OUT / "access/shore_fishing_sites.json").read_text())
        self.mgr = json.loads((OUT / "access/manager_pages.json").read_text())

    def resolve(self, key):
        """-> (url, normalized text, retrieved_at)"""
        if key in self.texts:
            return self.texts[key]
        kind, _, rest = key.partition(":")
        if kind == "LP":
            url = f"https://wdfw.wa.gov/fishing/locations/lowland-lakes/{rest}"
            path = glob.glob(str(OUT / f"identity/pages/*lowland-lakes_{rest}.html"))[0]
            r = (url, page_text(path), "2026-10-31 (Step 2 crawl)")
        elif kind == "WAS":
            url = f"https://wdfw.wa.gov/places-to-go/water-access-sites/{rest}"
            r = (url, page_text(OUT / "access/pages" / cache_name(url)), "2026-10-31")
        elif kind == "GIS":
            f = self.gis[int(rest)]
            r = (f"{self.gis_meta['source_url']} (AccessSiteID {rest})", norm(f["Description"] or ""), self.gis_meta["retrieved_at"])
        elif key == "WDFWLANDS":
            url = "https://wdfw.wa.gov/places-to-go/water-access-sites"
            r = (url, page_text(OUT / "access/was_list.html"), "2026-10-31")
        elif key == "DP":
            url = "https://parks.wa.gov/passes-permits/get-park-pass/discover-pass"
            r = (url, page_text(OUT / "access/pages" / cache_name(url)), self.mgr[url].get("retrieved_at"))
        elif key == "ECO":
            r = ("https://www.nwtoxicalgae.org/", page_text(OUT / "access/algae.html"), "2026-10-31")
        elif kind == "M":
            url = rest if rest.startswith("http") else key[2:]
            r = (url, page_text(OUT / "access/pages" / cache_name(url)), self.mgr.get(url, {}).get("retrieved_at"))
        else:
            raise SystemExit(f"unknown source key {key}")
        self.texts[key] = r
        return r


def fact(src, t, errors, where):
    state, value, evidence = t[0], t[1], t[2]
    confidence = t[3] if len(t) > 3 else ("HIGH" if evidence and state != "UNKNOWN" else ("NONE" if state == "UNKNOWN" else "MEDIUM"))
    prov = []
    for key, quote in evidence:
        url, text, when = src.resolve(key)
        ok = norm(quote) in text
        if not ok:
            errors.append(f"{where}: quote not found in {key}: {quote!r}")
        prov.append({"source_url": url, "quote": quote, "verified_in_cache": ok, "retrieved_at": when})
    if state != "UNKNOWN" and not evidence:
        if where.endswith(".closure_channel") and state == "LIMITED":
            # an assessment of the page's structure (no notice block), not a sourced fact
            confidence = "ASSESSMENT"
        else:
            errors.append(f"{where}: state {state} without evidence")
    return {"state": state, "value": value, "confidence": confidence, "provenance": prov}


def notices(src, items, errors, where):
    return [fact(src, ("YES", q, [(k, q)]), errors, where)["provenance"][0] for k, q in items]


def main():
    src = Sources()
    mvp = json.loads((HERE / "mvp_waters.json").read_text())
    ents = {e["entity_id"]: e for e in json.loads((OUT / "identity/entities.json").read_text())}
    was = json.loads((OUT / "access/wdfw_access_sites_mvp.json").read_text())
    shore = json.loads((OUT / "access/wdfw_gis_shore_mvp.json").read_text())
    er = (OUT / "access/er.html").read_text(encoding="utf-8")
    sel = re.search(r'<select[^>]*name="lake"[^>]*>(.*?)</select>', er, re.S).group(1)
    er_ids = {norm(n): v for v, n in re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', sel)}
    errors, dataset = [], []
    for w in mvp:
        F, e = FACTS[w["water_id"]], ents[w["entity_id"]]
        rec = {"water_id": w["water_id"], "canonical_name": e["canonical_name"], "counties": e["counties"],
               "official_wdfw_url": e["official_url"], "wdfw_geo_code": e["geo_code"],
               "stocking_aliases": w["stocking_aliases"],
               "lake_centre": {"lat": e["lat"], "lon": e["lon"], "source_url": e["official_url"]}}
        for f in LAKE_FIELDS:
            rec[f] = fact(src, F[f], errors, f"{w['water_id']}.{f}")
        rec["rule_notes"] = notices(src, F.get("rule_notes", []), errors, f"{w['water_id']}.rule_notes")
        rec["current_notices"] = notices(src, F.get("current_notices", []), errors, f"{w['water_id']}.current_notices")
        rec["data_conflicts"] = F.get("data_conflicts", [])
        er_id = er_ids.get(norm(e["canonical_name"]))
        rec["fishing_rule_sources"] = {
            "lake_page": e["official_url"],
            "statewide_pamphlet": "https://www.eregulations.com/washington/fishing/",
            "emergency_rules_for_this_lake": (f"https://wdfw.wa.gov/fishing/regulations/emergency-rules?lake={er_id}" if er_id else None),
            "emergency_rules_rss": "https://wdfw.wa.gov/fishing/regulations/emergency-rules/rss",
        }
        aps = []
        for ap in F["access_points"]:
            a = {k: ap[k] for k in ("ap_id", "name", "manager", "manager_type", "url") if k in ap}
            a["primary"] = bool(ap.get("primary"))
            for f in AP_FIELDS:
                a[f] = fact(src, ap.get(f, ("UNKNOWN", "Not stated", [])), errors, f"{w['water_id']}.{ap['ap_id']}.{f}")
            if "fishing_platform" in ap:
                a["fishing_platform"] = fact(src, ap["fishing_platform"], errors, f"{w['water_id']}.{ap['ap_id']}.fishing_platform")
            coords = None
            if ap.get("coords_from", "").startswith("WAS:"):
                site = next((s for s in was[w["water_id"]] if s["url"].endswith(ap["coords_from"][4:])), None)
                if site:
                    coords = {"lat": site["lat"], "lon": site["lon"], "source_url": site["url"]}
            a["access_coordinates"] = coords
            aps.append(a)
        rec["access_points"] = aps
        rec["shore_fishing_points"] = [{"lat": s["lat"], "lon": s["lon"], "description": s["Description"],
                                        "source_url": f"{src.gis_meta['source_url']} (AccessSiteID {int(s['AccessSiteID'])})"}
                                       for s in shore[w["water_id"]]["shore_sites"]]
        if not any(a["access_coordinates"] for a in aps) and not rec["shore_fishing_points"]:
            rec["access_coordinates_status"] = "UNKNOWN (only lake centre and street address)"
        else:
            rec["access_coordinates_status"] = "YES"
        prim = next(a for a in aps if a["primary"])
        pf = [prim["pass_required"]["state"], prim["parking_or_access_fee"]["state"]]
        rec["summary"] = {
            "bank_fishing_status": rec["bank_fishing_status"]["state"],
            "fishing_pier_or_dock": rec["fishing_pier_or_dock"]["state"],
            "public_access": max((a["public_access"]["state"] for a in aps), key=lambda s: s != "UNKNOWN"),
            "parking_available": prim["parking_available"]["state"],
            "pass_required": prim["pass_required"]["state"],
            "parking_or_access_fee": prim["parking_or_access_fee"]["state"],
            "pass_or_fee": "KNOWN" if any(s != "UNKNOWN" for s in pf) else "UNKNOWN",
            "operating_hours": prim["operating_hours"]["state"],
            "seasonal_access": prim["seasonal_access"]["state"],
            "closure_channel": prim["closure_channel"]["state"],
            "emergency_rule_monitoring": "YES" if er_id else "UNKNOWN",
            "fishing_rule_source": "YES",
            "access_coordinates": rec["access_coordinates_status"].split()[0],
            "primary_access_manager": prim["manager"],
        }
        rec["last_verified_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        dataset.append(rec)

    if errors:
        print("PROVENANCE ERRORS:", *errors, sep="\n  ")
        return 1

    def cov(field, known=lambda s: s not in ("UNKNOWN",)):
        vals = [r["summary"][field] for r in dataset]
        k = sum(1 for v in vals if known(v))
        return {"known": k, "unknown": len(vals) - k, "of": len(vals),
                "states": {s: vals.count(s) for s in sorted(set(vals))}}
    fields = ["bank_fishing_status", "fishing_pier_or_dock", "public_access", "parking_available", "pass_required",
              "parking_or_access_fee", "pass_or_fee", "operating_hours", "seasonal_access", "closure_channel",
              "emergency_rule_monitoring", "fishing_rule_source", "access_coordinates"]
    coverage = {f: cov(f) for f in fields}
    useful = sum(c["known"] for c in coverage.values()) / sum(c["of"] for c in coverage.values())
    core = {f: coverage[f] for f in CORE_FIELDS}
    core_rate = sum(c["known"] for c in core.values()) / sum(c["of"] for c in core.values())
    decision_ready = [r["water_id"] for r in dataset if all(r["summary"][f] not in ("UNKNOWN",) for f in
                                                           ("bank_fishing_status", "public_access", "parking_available", "pass_or_fee"))]
    report = {"lakes": len(dataset), "per_field": coverage, "overall_useful_field_coverage": round(useful, 3),
              "core_field_coverage": round(core_rate, 3), "core_fields": CORE_FIELDS,
              "lakes_with_all_core_fields_known": len(decision_ready), "decision_ready_lakes": decision_ready,
              "evidence_quotes_verified": sum(len(p["provenance"]) for r in dataset for p in
                                              [r["bank_fishing_status"], r["fishing_pier_or_dock"]] +
                                              [a[f] for a in r["access_points"] for f in AP_FIELDS]),
              "data_conflicts": {r["water_id"]: r["data_conflicts"] for r in dataset if r["data_conflicts"]}}
    (HERE / "access_dataset.json").write_text(json.dumps(dataset, indent=1, ensure_ascii=False))
    (HERE / "coverage_report.json").write_text(json.dumps(report, indent=1))
    for f, c in coverage.items():
        print(f"{f:28} {c['known']:2}/{c['of']} known  {c['states']}")
    print(f"overall useful-field coverage {useful:.1%}; core {core_rate:.1%}; decision-ready lakes {len(decision_ready)}/20")
    print(f"evidence quotes verified: {report['evidence_quotes_verified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
