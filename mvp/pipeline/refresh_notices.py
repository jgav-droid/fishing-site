#!/usr/bin/env python3
"""Refresh notices, kept as separate fact types (never merged into an OPEN/CLOSED flag):

  regulations       WDFW emergency rules in force for each lake (per-lake filter page)
  health            WA Ecology toxic-algae table ("Current lakes with values above guidelines")
  physical_access   WA State Parks Alerts block; curated dated notices from the Step 3 review
  source_changes    normalised-hash change detection on every access source page vs its
                    review-time baseline; a change flags the lake's access facts as
                    "official page changed since our review" and adds a review item

Each source keeps its own status. On failure, that source's last-known data is kept and
marked by source_status (last_success does not move).
"""
import hashlib
import html
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import _http, load, main_text, now_iso, save, update_source_status  # noqa: E402

ECOLOGY = "https://www.nwtoxicalgae.org/"
# Ecology site IDs verified against the table (stable ids beat names)
ECOLOGY_SITE_IDS = {"55": "wa-w-spanaway-lake"}
DELAY = 1.0


def _name_key(s):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "validation/wdfw/identity"))
    from match import parse_official  # Step 2 normaliser, same keys as waters.unique_name_keys
    return parse_official(s)["name_key"]


def fetch(url):
    r = _http.get(url, accept="text/html", timeout=60)
    if r["status"] != 200:
        raise RuntimeError(f"HTTP {r['status']} {r['error']}")
    time.sleep(DELAY)
    return r["body"].decode("utf-8", "replace")


def emergency_rules(waters, notices, data_dir):
    out, failed = {}, []
    for w in waters:
        url = w["emergency_rules_url"]
        try:
            s = fetch(url)
            m = re.search(r"<main.*?</main>", s, re.S)
            body = m.group(0) if m else s
            rules = []
            for href, title in re.findall(r'href="(/fishing/regulations/emergency-rules/[a-z0-9-]+-20\d\d-\d\d)"[^>]*>(.*?)</a>', body, re.S):
                t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", title)).split())
                if t and all(r["url"] != "https://wdfw.wa.gov" + href for r in rules):
                    rules.append({"title": t, "url": "https://wdfw.wa.gov" + href})
            out[w["water_id"]] = {"source_url": url, "rules": rules, "checked_at": now_iso()}
        except Exception as e:
            failed.append(f"{w['water_id']}: {e}")
            if w["water_id"] in notices.get("regulations", {}):
                out[w["water_id"]] = notices["regulations"][w["water_id"]]   # last known
    notices["regulations"] = out
    update_source_status(data_dir, "wdfw_emergency_rules", not failed, "; ".join(failed)[:300] or None,
                         {"lakes_checked": len(waters) - len(failed)})


def algae(waters, notices, queue, data_dir):
    try:
        s = fetch(ECOLOGY)
        t = re.search(r'id="c_ExceedanceGridView">(.*?)</table>', s, re.S)
        if not t:
            raise RuntimeError("advisory table not found (page template changed?)")
        rows = re.findall(r'href="Data\.aspx\?SiteID=(\d+)">([^<]+)</a></td><td>([^<]+)</td>', t.group(1))
    except Exception as e:
        update_source_status(data_dir, "ecology_toxic_algae", False, e)
        return
    by_key = {}
    for w in waters:
        for k in w["unique_name_keys"]:
            by_key[k] = w["water_id"]
    ambiguous = {k: w["water_id"] for w in waters for k in w["ambiguous_name_keys"]}
    out = {}
    for site_id, name, sampled in rows:
        name = html.unescape(name).strip()
        key = _name_key(name)
        entry = {"site_name": name, "ecology_site_id": site_id, "last_sample_date": sampled.strip(),
                 "source_url": ECOLOGY, "site_url": f"{ECOLOGY}Data.aspx?SiteID={site_id}",
                 "statement": "Listed by WA Dept of Ecology under 'Current lakes with values above guidelines'",
                 "checked_at": now_iso()}
        if site_id in ECOLOGY_SITE_IDS:
            out.setdefault(ECOLOGY_SITE_IDS[site_id], []).append({**entry, "match": "ecology_site_id"})
        elif key in by_key:
            out.setdefault(by_key[key], []).append({**entry, "match": "unique_name"})
            queue["items"].append({"kind": "advisory_name_match", "water_id": by_key[key], "site_name": name,
                                   "ecology_site_id": site_id, "detected_at": now_iso(),
                                   "note": "Attached by unique name; add the SiteID to ECOLOGY_SITE_IDS after confirming."})
        elif key in ambiguous:
            queue["items"].append({"kind": "advisory_ambiguous_name", "candidate_water_id": ambiguous[key], "site_name": name,
                                   "ecology_site_id": site_id, "detected_at": now_iso(),
                                   "note": "Name shared by several official waters: NOT attached. Confirm via the Ecology site page."})
    notices["health"] = out
    update_source_status(data_dir, "ecology_toxic_algae", True, extra={"listed_sites": len(rows)})


def state_parks(access, notices, data_dir):
    out, failed = {}, []
    for rec in access["waters"]:
        for a in rec["access_points"]:
            if a["manager_type"] != "state_park":
                continue
            try:
                s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", fetch(a["url"]), flags=re.S)
                t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())
                m = re.search(r"\bAlerts (.*?)(?: See all photos| Get Directions)", t)
                out[rec["water_id"]] = {"source_url": a["url"], "alerts_text": m.group(1)[:400] if m else None,
                                        "checked_at": now_iso()}
            except Exception as e:
                failed.append(f"{a['url']}: {e}")
                if rec["water_id"] in notices.get("state_parks_alerts", {}):
                    out[rec["water_id"]] = notices["state_parks_alerts"][rec["water_id"]]
    notices["state_parks_alerts"] = out
    update_source_status(data_dir, "wa_state_parks_alerts", not failed, "; ".join(failed) or None)


def source_changes(baselines, notices, queue, data_dir):
    changed, failed, checked, transient = {}, [], 0, []
    prev = notices.get("source_changes", {})
    for url, b in baselines.items():
        try:
            h = hashlib.sha256(main_text(fetch(url)).encode()).hexdigest()[:16]
            checked += 1
            if h != b["hash"]:
                # confirm with a second fetch: a WDFW lake page once returned a one-off
                # variant that matched the baseline again seconds later
                time.sleep(3)
                h2 = hashlib.sha256(main_text(fetch(url)).encode()).hexdigest()[:16]
                if h2 == b["hash"]:
                    transient.append(url)
                    continue
            if h != b["hash"]:
                changed[url] = {"water_ids": b["water_ids"], "baseline_at": b["baseline_at"], "detected_at": prev.get(url, {}).get("detected_at") or now_iso()}
        except Exception as e:
            failed.append({"url": url, "water_ids": b["water_ids"], "error": str(e)[:200]})
            if url in prev:
                changed[url] = prev[url]
    notices["source_changes"] = changed
    notices["source_fetch_failures"] = failed
    notices["source_transient_variants"] = transient
    queue["items"] = [i for i in queue["items"] if i.get("kind") not in ("access_source_changed", "access_source_unreachable")]
    for url, c in changed.items():
        queue["items"].append({"kind": "access_source_changed", "url": url, **c,
                               "note": "Official page text changed since the access review; re-verify the lake's access facts."})
    for f in failed:
        queue["items"].append({"kind": "access_source_unreachable", **f, "detected_at": now_iso(),
                               "note": "Could not fetch (404/redirect/timeout); URL may have moved."})
    update_source_status(data_dir, "access_source_pages", not failed, f"{len(failed)} page(s) unreachable" if failed else None,
                         {"pages_checked": checked, "pages_changed": len(changed)})


def main(data_dir=None, only=None):
    waters = load("waters.json", data_dir)
    access = load("access_facts.json", data_dir)
    notices = load("notices.json", data_dir) or {}
    queue = load("review_queue.json", data_dir) or {"items": []}
    queue["items"] = [i for i in queue["items"] if not i.get("kind", "").startswith("advisory_")]
    steps = only or ["regulations", "health", "parks", "changes"]
    if "regulations" in steps:
        emergency_rules(waters, notices, data_dir)
    if "health" in steps:
        algae(waters, notices, queue, data_dir)
    if "parks" in steps:
        state_parks(access, notices, data_dir)
    if "changes" in steps:
        source_changes(load("access_page_baselines.json", data_dir), notices, queue, data_dir)
    notices["generated_at"] = now_iso()
    save("notices.json", notices, data_dir)
    save("review_queue.json", queue, data_dir)
    print("notices:", {k: len(v) for k, v in notices.items() if isinstance(v, (dict, list))})
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    sys.exit(main(a.data_dir, a.only))
