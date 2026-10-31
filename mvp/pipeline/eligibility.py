"""MVP eligibility logic: what counts as recent catchable stocking, and per-lake trip status.

Catchable-size rule (documented on /methodology/):
  * only completed plants from WDFW Fish Plants (record_kind == "reported_plant")
  * species_type "Trout/Kokanee"
  * 0 < number_of_fish_per_pound <= 3.0. This is WDFW's own threshold: its lowland-lake
    pages list "catchable (3 fish per pound or larger)" plants with the query
    number_of_fish_per_pound <= 3.0. Lifestage labels are NOT used (inconsistent in the
    source: e.g. "Legals" at 7 fish/lb).
  * fish/lb missing, 0 or >= 999999 -> "size not reported": never counted as catchable
  * number_released > 0
Recent: release_start_date within RECENT_DAYS before the trip date (a product window, not
a biological claim). Stocking after the latest data refresh cannot be known.

Status flags are kept in separate categories and never merged into OPEN/CLOSED:
  regulation | physical_access | health | data
"""
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validation/wdfw/access"))
from trip_decision import fourth_saturday_april, window  # Step 3 season-window parser  # noqa: E402

CATCHABLE_FPP = 3.0
RECENT_DAYS = 30
EARLIER_DAYS = 120
CATCHABLE_SOURCE = "https://wdfw.wa.gov/fishing/locations/lowland-lakes"  # WDFW page script: number_of_fish_per_pound <= 3.0


def classify(ev):
    if ev.get("record_kind") != "reported_plant":
        raise ValueError(f"non-completed stocking record reached the site: {ev.get('content_hash_id')}")
    fpp = ev.get("number_of_fish_per_pound")
    if ev.get("species_type") != "Trout/Kokanee":
        return "not_counted", f"species type {ev.get('species_type')} (not trout/kokanee)"
    if ev.get("number_released", 0) <= 0:
        return "not_counted", "zero fish reported"
    if fpp is None or fpp <= 0 or fpp >= 999999:
        return "size_not_reported", "fish-per-pound not reported"
    if fpp <= CATCHABLE_FPP:
        return "catchable", f"{fpp:g} fish/lb (WDFW catchable threshold: 3 or fewer per lb)"
    return "below_catchable_size", f"{fpp:g} fish/lb: smaller than WDFW's catchable threshold"


LABEL = {"catchable": "Catchable size", "below_catchable_size": "Smaller than catchable size",
         "size_not_reported": "Size not reported", "not_counted": "Not counted"}


def stocking_summary(events, trip, data_date):
    """events: this lake's events. data_date: the latest date the data can describe."""
    out = {"recent": [], "earlier": [], "non_catchable_recent": [], "all": []}
    for e in sorted(events, key=lambda e: e["release_start_date"], reverse=True):
        cls, why = classify(e)
        d = date.fromisoformat(e["release_start_date"])
        row = {**e, "class": cls, "class_reason": why, "date": d}
        out["all"].append(row)
        if d > trip:
            continue
        age = (trip - d).days
        if cls == "catchable" and age <= RECENT_DAYS:
            out["recent"].append(row)
        elif cls == "catchable" and age <= EARLIER_DAYS:
            out["earlier"].append(row)
        elif cls != "catchable" and age <= RECENT_DAYS:
            out["non_catchable_recent"].append(row)
    out["recent_total"] = sum(r["number_released"] for r in out["recent"])
    out["recent_species"] = sorted({r["species"] for r in out["recent"]})
    out["last_catchable"] = next((r for r in out["all"] if r["class"] == "catchable" and r["date"] <= trip), None)
    out["data_limit_note"] = (f"Stocking after {data_date:%b %-d} is not yet in WDFW's data" if trip > data_date else None)
    return out


def windows_for(text, years):
    res = []
    for y in years:
        w = window(text, y)
        if w:
            res.append({"start": w[0].isoformat(), "end": w[1].isoformat()})
    return res


def curated_notice_windows(curated, water_id):
    return [n for n in curated.get(water_id, [])]


def lake_status(water, access, events, regs, health, curated_notices, source_changes, trip, data_date, parks_alerts=None):
    years = [trip.year, trip.year + 1]
    st = stocking_summary(events, trip, data_date)
    flags = []
    for n in access["rule_notes"]:
        q = n["quote"]
        if "juvenile" in q.lower():
            flags.append({"cat": "regulation", "level": "restricted", "key": "eligibility", "text": q, "source": n["source_url"]})
        w = window(q, trip.year) if " open" in (" " + q.lower()) else None
        if w:
            inside = w[0] <= trip <= w[1]
            t_in = f"Within the fishing season WDFW lists ({w[0]:%b %-d} – {w[1]:%b %-d})"
            t_out = f"Outside the fishing season WDFW lists ({w[0]:%b %-d} – {w[1]:%b %-d})"
            flags.append({"cat": "regulation", "level": "ok" if inside else "blocking", "key": "fishing_season",
                          "text": t_in if inside else t_out, "season": True, "out_level": "blocking",
                          "label_in": t_in, "label_out": t_out,
                          "quote": q, "source": n["source_url"], "windows": windows_for(q, years)})
    r = regs.get(water["water_id"])
    if r:
        flags.append({"cat": "regulation", "level": "info", "key": "emergency_rules",
                      "text": (f"{len(r['rules'])} WDFW emergency rule(s) listed for this lake (includes statewide rules)"
                               if r["rules"] else "No WDFW emergency rules listed for this lake"),
                      "rules": r["rules"], "source": r["source_url"], "checked_at": r["checked_at"]})
    for a in access["access_points"]:
        sa = a["seasonal_access"]
        w = window(sa["value"], trip.year) if sa["state"] == "YES" else None
        if w:
            inside = w[0] <= trip <= w[1]
            t_in = f"{a['name']}: inside its listed open dates ({sa['value']})"
            t_out = f"{a['name']}: outside its listed open dates ({sa['value']})"
            out_level = "blocking" if a["primary"] else "warn"
            flags.append({"cat": "physical_access", "level": "ok" if inside else out_level,
                          "key": "access_season", "ap": a["name"], "text": t_in if inside else t_out,
                          "season": True, "out_level": out_level, "label_in": t_in, "label_out": t_out,
                          "source": a["url"], "windows": windows_for(sa["value"], years)})
        elif "Open to vehicles only during the regulated sport fishing season" in sa["value"]:
            fs = next((f for f in flags if f["key"] == "fishing_season"), None)
            if fs:
                t_in = f"{a['name']}: vehicles allowed only during the fishing season"
                t_out = t_in + " (outside it on this date)"
                flags.append({"cat": "physical_access", "level": "ok" if fs["level"] == "ok" else "blocking",
                              "key": "access_season", "ap": a["name"], "text": t_in if fs["level"] == "ok" else t_out,
                              "season": True, "out_level": "blocking", "label_in": t_in, "label_out": t_out,
                              "source": a["url"], "windows": fs["windows"]})
    for n in curated_notices.get(water["water_id"], []):
        s, e = n.get("valid_from"), n.get("valid_until")
        active = (not s or date.fromisoformat(s) <= trip) and (not e or trip <= date.fromisoformat(e))
        flags.append({"cat": n["category"], "level": n.get("level", "warn") if active else "inactive", "key": "notice",
                      "text": n["text"], "posted": n.get("posted"), "source": n["source_url"], "notice": True,
                      "in_level": n.get("level", "warn"),
                      "windows": [{"start": s or "1900-01-01", "end": e or "2999-12-31"}]})
    if parks_alerts and parks_alerts.get(water["water_id"], {}).get("alerts_text"):
        pa = parks_alerts[water["water_id"]]
        flags.append({"cat": "physical_access", "level": "info", "key": "park_alerts",
                      "text": f"State Parks alert: {pa['alerts_text']}", "source": pa["source_url"], "checked_at": pa["checked_at"]})
    for h in health.get(water["water_id"], []):
        flags.append({"cat": "health", "level": "warn", "key": "toxic_algae",
                      "text": f"Toxic algae: {h['statement']} (last sample {h['last_sample_date']})" +
                              (" — matched by lake name" if h["match"] == "unique_name" else ""),
                      "source": h["site_url"], "checked_at": h["checked_at"]})
    changed = [u for u, c in source_changes.items() if water["water_id"] in c["water_ids"]]
    if changed:
        flags.append({"cat": "data", "level": "warn", "key": "source_changed",
                      "text": "An official source page has changed since our access review; access details may be out of date",
                      "sources": changed})
    for c in access["data_conflicts"]:
        flags.append({"cat": "data", "level": "info", "key": "conflict", "text": c})
    shore = access["bank_fishing_status"]["state"]
    qualifies = bool(st["recent"]) and shore in ("YES", "LIMITED")
    blocking = [f for f in flags if f["level"] == "blocking"]
    flags = [f for f in flags if f["level"] != "inactive"] + [f for f in flags if f["level"] == "inactive"]
    why = []
    if st["recent"]:
        why.append(f"catchable trout reported stocked {fmt_range([r['date'] for r in st['recent']])} "
                   f"({st['recent_total']:,} {', '.join(s.lower() for s in st['recent_species'])})")
    if shore in ("YES", "LIMITED"):
        why.append(f"documented public shore access ({shore.lower()})")
    return {"stocking": st, "flags": flags, "qualifies": qualifies, "blocking": blocking, "why": why,
            "restricted": any(f["key"] == "eligibility" for f in flags)}


def fmt_range(dates):
    ds = sorted(set(dates))
    if not ds:
        return ""
    if len(ds) == 1:
        return f"{ds[0]:%b %-d}"
    a, b = ds[0], ds[-1]
    return f"{a:%b %-d}–{b:%-d}" if a.month == b.month else f"{a:%b %-d} – {b:%b %-d}"
