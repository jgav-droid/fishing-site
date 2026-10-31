#!/usr/bin/env python3
"""Source fragmentation, field-class breakdown, setup-time and maintenance model.

Reads access/access_dataset.json (provenance) and the action counts below, writes
access/analysis.json. Every assumption is a named constant; change it and rerun.
"""
import json
import statistics
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent

AGENCY = {"wdfw.wa.gov": "WDFW", "geodataservices.wdfw.wa.gov": "WDFW", "www.eregulations.com": "WDFW",
          "parks.wa.gov": "WA State Parks", "clark.wa.gov": "Clark County", "www.seattle.gov": "City of Seattle",
          "www.seatacwa.gov": "City of SeaTac", "www.kentwa.gov": "City of Kent",
          "snohomishcountywa.gov": "Snohomish County", "cityoflacey.org": "City of Lacey",
          "cityoflakewood.us": "City of Lakewood", "www.mytpu.org": "Tacoma Power",
          "www.puyallupwa.gov": "City of Puyallup", "www.piercecountywa.gov": "Pierce County",
          "www.nwtoxicalgae.org": "WA Dept of Ecology"}
FORMAT = {"geodataservices.wdfw.wa.gov": "ArcGIS REST JSON"}
SHARED = {"https://wdfw.wa.gov/places-to-go/water-access-sites", "https://parks.wa.gov/passes-permits/get-park-pass/discover-pass",
          "https://clark.wa.gov/public-works/parking-fees", "https://snohomishcountywa.gov/5281/Passes",
          "https://www.mytpu.org/community-environment-parks/parks-recreation/reservations-fees/",
          "https://geodataservices.wdfw.wa.gov/arcgis/rest/services/FP_FishMaps/ShoreFishingSites/MapServer/0",
          "https://www.nwtoxicalgae.org/"}
TEMPLATE = {"WDFW": "WDFW lake page (710) + water-access-site page (472) + statewide GIS layers",
            "WA State Parks": "parks.wa.gov park page: Hours/Fees/Alerts blocks (parser 4/4)",
            "WA Dept of Ecology": "one statewide advisory table"}

# Searches actually run per lake to find the land-manager page or a fee/pass statement
SEARCHES = {"wa-w-battle-ground-lake": 1, "wa-w-klineline-pond": 1, "wa-w-lacamas-lake": 1, "wa-w-green-lake-king": 2,
            "wa-w-angle-lake": 1, "wa-w-lake-meridian": 2, "wa-w-martha-alderwood-manor": 2, "wa-w-longs-pond": 1,
            "wa-w-american-lake": 1, "wa-w-alder-lake": 1, "wa-w-lake-bradley": 2, "wa-w-spanaway-lake": 1}
URL_REPAIRS = {"wa-w-lake-bradley": 1}       # cityofpuyallup.org/545 -> 301 -> 404; re-found at puyallupwa.gov/2503

# Founder-equivalent minutes per action (assumptions)
MIN_SEARCH = 2.0          # run one official-domain search, pick the right result
MIN_MGR_PAGE = 4.0        # read a land-manager page for hours/fees/pass/dock/notices
MIN_WDFW_PAGE = 1.0       # review an auto-parsed WDFW template page (lake page, access site)
MIN_SHARED_PAGE = 0.5     # shared page (pass rules, fee schedule), amortized
MIN_JUDGEMENT = 0.5       # assign a YES/LIMITED/NO/UNKNOWN state from evidence, per field
MIN_CONFLICT = 5.0        # investigate and record one source conflict
MIN_URL_REPAIR = 4.0
MIN_MONITOR = 1.0         # register one page/feed for change detection

FIELD_CLASS = {
    "lake_centre_coordinates": "STATIC", "access_coordinates": "STATIC", "bank_fishing_status": "STATIC",
    "fishing_pier_or_dock (existence)": "STATIC", "public_access": "STATIC", "parking_available": "STATIC",
    "access_manager / official URLs": "STATIC", "accessibility notes (ADA)": "STATIC", "two-pole / gear rules": "PERIODIC",
    "parking_or_access_fee": "PERIODIC", "pass_required / pass_type": "PERIODIC", "operating_hours": "PERIODIC",
    "seasonal_access windows": "PERIODIC", "fishing season & lake-specific rules (annual pamphlet)": "PERIODIC",
    "angler eligibility restrictions (juvenile-only waters)": "PERIODIC",
    "temporary closures / construction": "EVENT", "facility status (pier/ramp closed)": "EVENT",
    "emergency fishing rules": "EVENT", "water-quality (toxic algae) advisories": "EVENT",
    "lake-level-dependent access (reservoirs)": "EVENT",
    "stocking events": "HIGH_FREQUENCY (automated, daily feed)",
}

# Maintenance model (per lake per year), split by primary access family
CHANGES_PER_YEAR = {"local_park": 8, "state_park": 4, "wdfw": 2}       # material changes detected on that lake's pages
NOISE_PER_YEAR = {"local_park": 6, "state_park": 2, "wdfw": 3}         # change alerts that turn out immaterial
MIN_REVIEW_CHANGE = 6.0
MIN_NOISE = 1.5
MIN_ANNUAL_REVERIFY = {"local_park": 5, "state_park": 3, "wdfw": 2}    # yearly check of periodic fields (fees/hours/pamphlet)
EMERGENCY_TRIAGE_PER_YEAR = 3                                          # lake-tagged rule items to read (most are statewide)
MIN_EMERGENCY = 2.0
FIXED_HOURS_PER_MONTH = 2.0                                            # monitor ops, broken parser/URL fixes, feed checks
PER_LAKE_OPS_MIN_PER_MONTH = 0.5
SCALE_MIX = {20: None, 50: None, 200: {"wdfw": 0.55, "state_park": 0.10, "local_park": 0.35},
             500: {"wdfw": 0.60, "state_park": 0.10, "local_park": 0.30}}  # None = use the MVP mix


def family(rec):
    t = next(a for a in rec["access_points"] if a["primary"])["manager_type"]
    return "wdfw" if t == "wdfw_water_access" else "state_park" if t == "state_park" else "local_park"


def provenance_urls(rec):
    urls = set()
    for f in ("bank_fishing_status", "fishing_pier_or_dock"):
        urls |= {p["source_url"].split(" (")[0] for p in rec[f]["provenance"]}
    for a in rec["access_points"]:
        for v in a.values():
            if isinstance(v, dict) and "provenance" in v:
                urls |= {p["source_url"].split(" (")[0] for p in v["provenance"]}
    for n in rec["current_notices"] + rec["rule_notes"]:
        urls.add(n["source_url"].split(" (")[0])
    return urls


def main():
    ds = json.loads((HERE / "access_dataset.json").read_text())
    per_lake = []
    for r in ds:
        urls = provenance_urls(r)
        agencies = sorted({AGENCY[urlparse(u).netloc] for u in urls})
        own = sorted(u for u in urls if u not in SHARED)
        counts = {}
        for f in ("bank_fishing_status", "fishing_pier_or_dock"):
            for p in r[f]["provenance"]:
                counts[AGENCY[urlparse(p["source_url"].split(" (")[0]).netloc]] = counts.get(AGENCY[urlparse(p["source_url"].split(" (")[0]).netloc], 0) + 1
        for a in r["access_points"]:
            for v in a.values():
                if isinstance(v, dict) and v.get("provenance") and v["state"] != "UNKNOWN":
                    ag = AGENCY[urlparse(v["provenance"][0]["source_url"].split(" (")[0]).netloc]
                    counts[ag] = counts.get(ag, 0) + 1
        top, topn = max(counts.items(), key=lambda kv: kv[1])
        mgr_pages = [u for u in own if AGENCY[urlparse(u).netloc] not in ("WDFW", "WA Dept of Ecology")]
        wdfw_pages = [u for u in own if AGENCY[urlparse(u).netloc] == "WDFW"]
        shared = [u for u in urls if u in SHARED]
        n_judged = 2 + 7 * len(r["access_points"])
        minutes = {
            "identify_sources": SEARCHES.get(r["water_id"], 0) * MIN_SEARCH + MIN_URL_REPAIR * URL_REPAIRS.get(r["water_id"], 0),
            "populate_static_and_periodic": len(mgr_pages) * MIN_MGR_PAGE + len(wdfw_pages) * MIN_WDFW_PAGE
                                            + len(shared) * MIN_SHARED_PAGE + n_judged * MIN_JUDGEMENT,
            "resolve_inconsistencies": len(r["data_conflicts"]) * MIN_CONFLICT,
            "establish_monitoring": (len(own) + 1) * MIN_MONITOR,   # +1: emergency-rule lake filter
        }
        per_lake.append({
            "water_id": r["water_id"], "name": r["canonical_name"], "family": family(r),
            "authoritative_agencies": agencies, "n_agencies": len(agencies),
            "pages_total": len(urls), "pages_lake_specific": len(own), "pages_shared": len(shared),
            "one_source_covers_most_fields": topn / sum(counts.values()) >= 0.7, "top_agency": top,
            "top_agency_share": round(topn / sum(counts.values()), 2),
            "formats": sorted({FORMAT.get(urlparse(u).netloc, "HTML") for u in urls}),
            "pdf_or_manual_extraction": False,
            "template_family": TEMPLATE.get(top, f"{top}: own CMS page (no shared template)"),
            "data_conflicts": len(r["data_conflicts"]),
            "setup_minutes": {k: round(v, 1) for k, v in minutes.items()},
            "setup_minutes_total": round(sum(minutes.values()), 1),
        })
    n = len(per_lake)
    setup = [p["setup_minutes_total"] for p in per_lake]
    frag = {
        "median_authoritative_agencies_per_lake": statistics.median(p["n_agencies"] for p in per_lake),
        "median_pages_per_lake_total": statistics.median(p["pages_total"] for p in per_lake),
        "median_lake_specific_pages": statistics.median(p["pages_lake_specific"] for p in per_lake),
        "pct_covered_primarily_by_one_source": round(sum(p["one_source_covers_most_fields"] for p in per_lake) / n, 3),
        "pct_requiring_3plus_agencies": round(sum(p["n_agencies"] >= 3 for p in per_lake) / n, 3),
        "pct_requiring_pdf_or_manual_extraction": 0.0,
        "primary_family_counts": {f: sum(p["family"] == f for p in per_lake) for f in ("wdfw", "state_park", "local_park")},
        "distinct_land_managers": sorted({a for p in per_lake for a in p["authoritative_agencies"]}),
    }
    by_fam = {f: statistics.median([p["setup_minutes_total"] for p in per_lake if p["family"] == f] or [0])
              for f in ("wdfw", "state_park", "local_park")}
    worst = max(per_lake, key=lambda p: p["setup_minutes_total"])
    mvp_mix = {f: c / n for f, c in frag["primary_family_counts"].items()}

    def initial(k, mix):
        mix = mix or mvp_mix
        return k * sum(mix[f] * by_fam[f] for f in mix)

    def monthly(k, mix, scale=1.0):
        mix = mix or mvp_mix
        per_lake_year = {f: (CHANGES_PER_YEAR[f] * MIN_REVIEW_CHANGE + NOISE_PER_YEAR[f] * MIN_NOISE
                             + MIN_ANNUAL_REVERIFY[f] + EMERGENCY_TRIAGE_PER_YEAR * MIN_EMERGENCY) * scale for f in mix}
        manual_min = k * sum(mix[f] * per_lake_year[f] for f in mix) / 12
        ops_min = FIXED_HOURS_PER_MONTH * 60 + k * PER_LAKE_OPS_MIN_PER_MONTH
        return manual_min, ops_min

    maint = {}
    for k, mix in SCALE_MIX.items():
        man, ops = monthly(k, mix)
        lo, _ = monthly(k, mix, 0.5)
        hi, _ = monthly(k, mix, 2.0)
        maint[k] = {"manual_review_hours_per_month": round(man / 60, 1), "ops_hours_per_month": round(ops / 60, 1),
                    "total_hours_per_month": round((man + ops) / 60, 1), "total_hours_per_week": round((man + ops) / 60 / 4.33, 2),
                    "range_hours_per_week_(0.5x-2x change rate)": [round((lo + ops) / 60 / 4.33, 2), round((hi + ops) / 60 / 4.33, 2)],
                    "initial_setup_hours": round(initial(k, mix) / 60, 1)}
    classes = {}
    for c in FIELD_CLASS.values():
        key = c.split(" ")[0]
        classes[key] = classes.get(key, 0) + 1
    out = {"per_lake": per_lake, "fragmentation": frag,
           "setup_time": {"basis": "founder-equivalent minutes modeled from counted actions (searches, pages, judgements, conflicts) "
                                   "with the per-action costs in analyze.py; measured agent wall-clock for all 20 lakes was ~29 min",
                          "median_minutes_per_lake": statistics.median(setup), "mean_minutes_per_lake": round(statistics.mean(setup), 1),
                          "median_by_family": by_fam, "worst_case": {"name": worst["name"], "minutes": worst["setup_minutes_total"],
                                                                    "why": worst["setup_minutes"]},
                          "initial_hours_50": maint[50]["initial_setup_hours"], "initial_hours_500": maint[500]["initial_setup_hours"]},
           "field_classes": FIELD_CLASS,
           "field_class_breakdown_pct": {k: round(v / len(FIELD_CLASS), 3) for k, v in classes.items()},
           "maintenance": maint,
           "assumptions": {k: v for k, v in globals().items() if k.isupper() and k not in ("AGENCY", "FORMAT", "SHARED", "TEMPLATE", "FIELD_CLASS")}}
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"fragmentation": frag, "setup_time": {k: v for k, v in out["setup_time"].items() if k != "basis"},
                      "field_class_breakdown_pct": out["field_class_breakdown_pct"], "maintenance": maint}, indent=1, default=str))
    for p in per_lake:
        print(f"{p['name']:30} {p['family']:10} agencies={p['n_agencies']} pages={p['pages_total']} ({p['pages_lake_specific']} own) "
              f"top={p['top_agency']}({p['top_agency_share']}) setup={p['setup_minutes_total']}m conflicts={p['data_conflicts']}")


if __name__ == "__main__":
    main()
