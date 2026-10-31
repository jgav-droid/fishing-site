#!/usr/bin/env python3
"""Text-only trip-decision records (validation, no UI).

Combines three different facts and keeps them separate:
  * stocking events    (6fex-3r7d, Step 1; matched via Step 2 aliases)
  * fishing rules      (WDFW lake page notes + pamphlet + emergency-rule filter)
  * physical access    (access_dataset.json, every line traceable to a cited source)
It never claims a lake is "open". It reports what the cited sources say, and the
date ranges they give, for the trip date.

  python3 access/trip_decision.py --date 2026-10-31 --lakes wa-w-spanaway-lake ...
Writes access/trip_decisions.txt
"""
import argparse
import csv
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# WDFW's own lowland-lake pages list "catchable (3 fish per pound or larger)" plants only;
# fry/fingerling plants are not this weekend's fish, so they never headline a record.
CATCHABLE_FPP = 3.0
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}


def fourth_saturday_april(y):
    d = date(y, 4, 1)
    first_sat = d + timedelta(days=(5 - d.weekday()) % 7)
    return first_sat + timedelta(weeks=3)


def window(text, y):
    """'4th Saturday in April - September 30' -> (start, end) for year y; None if not parseable."""
    t = text.lower()
    m = re.search(r"(4th saturday in april|fourth saturday in april|([a-z]+) (\d{1,2}))\s*(?:-|to|through)\s*([a-z]+) (\d{1,2})", t)
    if not m or m.group(4) not in MONTHS:
        return None
    start = fourth_saturday_april(y) if "saturday" in m.group(1) else date(y, MONTHS[m.group(2)], int(m.group(3)))
    return start, date(y, MONTHS[m.group(4)], int(m.group(5)))


def km(a, b, c, d):
    return math.hypot((a - c) * 111, (b - d) * 111 * math.cos(math.radians(a)))


def load_stocking(aliases, since):
    rows = []
    for r in csv.DictReader(open(ROOT / "out/full_export.csv", newline="", encoding="utf-8")):
        k = " ".join(r["Release Location"].split()).upper()
        if k in aliases:
            d = datetime.strptime(r["Release Start Date"].split()[0], "%m/%d/%Y").date()
            if d >= since:
                try:
                    fpp = float(r["Number of Fish Per Pound"].replace(",", ""))
                except ValueError:
                    fpp = None
                rows.append((d, r["Species"], int(float(r["Number Released"].replace(",", "") or 0)),
                             r["Number of Fish Per Pound"], r["Lifestage"], k, fpp is not None and 0 < fpp <= CATCHABLE_FPP))
    return sorted(rows, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-10-31")
    ap.add_argument("--lakes", nargs="+", required=True)
    ap.add_argument("--days", type=int, default=45)
    args = ap.parse_args()
    trip = date.fromisoformat(args.date)
    ds = {r["water_id"]: r for r in json.loads((HERE / "access_dataset.json").read_text())}
    since = trip - timedelta(days=args.days)
    all_alias = {a: wid for wid, r in ds.items() for a in r["stocking_aliases"]}
    recent = {}
    for row in load_stocking(set(all_alias), since):
        recent.setdefault(all_alias[row[5]], []).append(row)
    out = []
    for wid in args.lakes:
        r = ds[wid]
        L = [f"{r['canonical_name'].upper()}  ({', '.join(r['counties'])} County)   trip date {trip:%a %b %d, %Y}", "=" * 78]
        allst = recent.get(wid, [])
        st = [x for x in allst if x[6]]
        L.append(f"Recently stocked, catchable size (<= {CATCHABLE_FPP:g} fish/lb; WDFW Fish Plants 6fex-3r7d, refreshed 2026-10-29):")
        if st:
            for d, sp, n, fpp, life, _, _c in st[:4]:
                L.append(f"  {d:%b %d}  {n:,} {sp} ({fpp} fish/lb)")
        else:
            L.append(f"  none in the last {args.days} days")
        small = [x for x in allst if not x[6]]
        if small:
            L.append(f"  (also {len(small)} fry/fingerling plant(s), e.g. {small[0][0]:%b %d} {small[0][2]:,} {small[0][1]} at {small[0][3]} fish/lb: not catchable this weekend)")
        s = r["summary"]
        word = {"YES": "Yes", "NO": "No", "LIMITED": "Limited", "UNKNOWN": "Unknown (not stated by official sources)"}
        L.append(f"Shore fishing:   {word[s['bank_fishing_status']]}: {r['bank_fishing_status']['value']}")
        L.append(f"Pier/dock:       {word[s['fishing_pier_or_dock']]}: {r['fishing_pier_or_dock']['value']}")
        prim = next(a for a in r["access_points"] if a["primary"])
        L.append(f"Main access:     {prim['name']} ({prim['manager']})")
        L.append(f"Parking:         {word[prim['parking_available']['state']]}: {prim['parking_available']['value']}")
        L.append(f"Pass:            {word[prim['pass_required']['state']]}: {prim['pass_required']['value']}")
        L.append(f"Fees:            {word[prim['parking_or_access_fee']['state']]}: {prim['parking_or_access_fee']['value']}")
        L.append(f"Hours:           {word[prim['operating_hours']['state']]}: {prim['operating_hours']['value']}")
        for a in r["access_points"]:
            sa = a["seasonal_access"]
            w = window(sa["value"], trip.year) if sa["state"] == "YES" else None
            if w:
                inside = w[0] <= trip <= w[1]
                L.append(f"Access season:   {a['name']}: '{sa['value']}' -> on {trip:%b %d} this is "
                         f"{'INSIDE' if inside else 'OUTSIDE'} the listed window ({w[0]:%b %d}-{w[1]:%b %d}) [{a['url']}]")
            elif sa["state"] in ("YES", "LIMITED"):
                L.append(f"Access season:   {a['name']}: {sa['value']}")
        rules = []
        for n in r["rule_notes"]:
            q = n["quote"]
            w = window(q, trip.year)
            tag = ""
            if w and ("open" in q.lower()):
                tag = f"  -> on {trip:%b %d}: {'within' if w[0] <= trip <= w[1] else 'OUTSIDE'} that season"
            rules.append(f"  - {q}{tag}")
        L.append("Rules (WDFW):" + ("" if rules else " no lake-specific notes on the WDFW page; statewide pamphlet applies"))
        L += rules
        L.append(f"  Emergency rules for this lake: {r['fishing_rule_sources']['emergency_rules_for_this_lake']}")
        if r["current_notices"]:
            L.append("Current notices (as retrieved 2026-10-31):")
            for n in r["current_notices"]:
                L.append(f"  ! {n['quote']}  [{n['source_url']}]")
        if r["data_conflicts"]:
            L.append("Unresolved source conflicts:")
            L += [f"  ? {c}" for c in r["data_conflicts"]]
        alts = []
        for oid, o in ds.items():
            cat = [x for x in recent.get(oid, []) if x[6]]
            if oid == wid or not cat:
                continue
            d = km(r["lake_centre"]["lat"], r["lake_centre"]["lon"], o["lake_centre"]["lat"], o["lake_centre"]["lon"])
            if d <= 40:
                last = cat[0]
                flags = []
                if any("juvenile" in n["quote"].lower() for n in o["rule_notes"]):
                    flags.append("RESTRICTED: juvenile/senior/disabled anglers only")
                for x in o["access_points"]:
                    w = window(x["seasonal_access"]["value"], trip.year) if x["seasonal_access"]["state"] == "YES" else None
                    if x["primary"] and w and not (w[0] <= trip <= w[1]):
                        flags.append(f"{x['name']} outside its listed season ({w[0]:%b %d}-{w[1]:%b %d})")
                if o["current_notices"]:
                    flags.append(f"{len(o['current_notices'])} current notice(s)")
                alts.append((d, f"{o['canonical_name']} ({d:.0f} km): stocked {last[0]:%b %d} ({last[2]:,} {last[1]}); "
                                f"shore {o['summary']['bank_fishing_status'].lower()}, dock {o['summary']['fishing_pier_or_dock'].lower()}"
                                + (f"; {'; '.join(flags)}" if flags else "")))
        L.append("Nearby recently stocked alternatives (MVP set, 40 km):")
        L += [f"  - {t}" for _, t in sorted(alts)[:3]] or ["  - none in the MVP set"]
        urls = set({p["source_url"].split(" (")[0] for f in ("bank_fishing_status", "fishing_pier_or_dock") for p in r[f]["provenance"]}
                      | {p["source_url"].split(" (")[0] for a in r["access_points"] for f in a if isinstance(a[f], dict) and "provenance" in a[f]
                         for p in a[f]["provenance"]}
                      | {n["source_url"].split(" (")[0] for n in r["current_notices"] + r["rule_notes"]})
        consult = urls | {"https://wdfw.wa.gov/fishing/reports/stocking/trout-plants/all",
                          r["fishing_rule_sources"]["emergency_rules_for_this_lake"] or "", r["fishing_rule_sources"]["statewide_pamphlet"]}
        consult.discard("")
        L.append(f"Official sources behind this record ({len(consult)} pages):")
        L += [f"  {u}" for u in sorted(consult)]
        out.append("\n".join(L))
        r["_pages_consulted"] = len(consult)
        print(f"{r['canonical_name']}: {len(consult)} official pages combined")
    (HERE / "trip_decisions.txt").write_text(("\n\n" + "-" * 78 + "\n\n").join(out) + "\n")
    print("wrote access/trip_decisions.txt")


if __name__ == "__main__":
    main()
