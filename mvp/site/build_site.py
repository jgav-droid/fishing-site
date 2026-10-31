#!/usr/bin/env python3
"""Render the static, indexable MVP site from mvp/data/ into mvp/dist/.

  python3 mvp/site/build_site.py [--date YYYY-MM-DD] [--data-dir DIR] [--out DIR] [--production]

--production refuses to build with placeholder settings (base_url, contact) and makes the
site indexable. Without it, every page carries noindex and robots.txt disallows crawling.
"""
import argparse
import html
import json
import math
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

MVP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MVP / "pipeline"))
import eligibility as el  # noqa: E402
from common import load  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

E = html.escape
AGENCY = {"wdfw.wa.gov": "WDFW", "geodataservices.wdfw.wa.gov": "WDFW (GIS)", "www.eregulations.com": "WDFW sport fishing rules",
          "data.wa.gov": "WDFW via data.wa.gov", "parks.wa.gov": "Washington State Parks", "clark.wa.gov": "Clark County",
          "www.seattle.gov": "Seattle Parks and Recreation", "www.seatacwa.gov": "City of SeaTac", "www.kentwa.gov": "City of Kent",
          "snohomishcountywa.gov": "Snohomish County Parks", "cityoflacey.org": "City of Lacey", "cityoflakewood.us": "City of Lakewood",
          "www.mytpu.org": "Tacoma Power", "www.puyallupwa.gov": "City of Puyallup", "www.piercecountywa.gov": "Pierce County Parks",
          "www.nwtoxicalgae.org": "WA Dept of Ecology (toxic algae)"}
STATE_WORD = {"YES": "Yes", "NO": "No", "LIMITED": "Limited", "UNKNOWN": "Not stated"}
ICON = {
    "fish": '<path d="M3 12c3-4 7-5 11-5 3 0 5 2 7 5-2 3-4 5-7 5-4 0-8-1-11-5zm0 0l-2-3m2 3l-2 3"/><circle cx="16" cy="11" r="1"/>',
    "shore": '<path d="M2 18c2 0 2-1.5 4-1.5S8 18 10 18s2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5M4 14l5-8 3 5 2-3 6 6"/>',
    "dock": '<path d="M3 10h18M6 10v9M12 10v9M18 10v9M2 21c2 0 2-1 4-1s2 1 4 1 2-1 4-1 2 1 4 1"/>',
    "park": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M10 17V7h3a3 3 0 010 6h-3"/>',
    "pass": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h6M7 14h4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "season": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "alert": '<path d="M12 3l10 18H2zM12 10v5M12 18v.5"/>',
    "access": '<path d="M12 21s-7-6-7-11a7 7 0 0114 0c0 5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
}


def icon(name):
    return f'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICON[name]}</svg>'


def km(a, b, c, d):
    return math.hypot((a - c) * 111.0, (b - d) * 111.0 * math.cos(math.radians(a)))


def miles(k):
    return k / 1.609344


class Site:
    def __init__(self, data_dir, out, trip, production):
        self.cfg = json.loads((MVP / "config.json").read_text())
        self.production = production
        if production:
            if "example.invalid" in self.cfg["base_url"] or not self.cfg["contact_email"]:
                raise SystemExit("production build needs config.json base_url and contact_email")
        self.base = self.cfg["base_url"].rstrip("/")
        self.tz = ZoneInfo(self.cfg["timezone"]) if ZoneInfo else timezone.utc
        self.out = Path(out)
        self.trip = trip
        self.d = data_dir
        self.waters = load("waters.json", data_dir)
        self.access = {r["water_id"]: r for r in load("access_facts.json", data_dir)["waters"]}
        self.access_reviewed = load("access_facts.json", data_dir)["reviewed_at"]
        stock = load("stocking_events.json", data_dir) or {"events": [], "retrieved_at": None}
        self.stock_meta = stock
        self.events = {}
        for ev in stock["events"]:
            self.events.setdefault(ev["water_id"], []).append(ev)
        upd = stock.get("dataset_rows_updated_at")
        self.data_date = (datetime.fromtimestamp(upd, timezone.utc).astimezone(self.tz).date() if upd else trip)
        self.notices = load("notices.json", data_dir) or {}
        self.curated = (load("curated_notices.json", data_dir) or {"notices": {}})["notices"]
        self.status = load("source_status.json", data_dir) or {}
        self.queue = (load("review_queue.json", data_dir) or {"items": []})["items"]
        self.aliases = load("aliases.json", data_dir)
        self.places = load("places.json", data_dir)["places"]
        self.built_at = datetime.now(timezone.utc).replace(microsecond=0)
        self.pages = []
        self.st = {}
        for w in self.waters:
            self.st[w["water_id"]] = el.lake_status(
                w, self.access[w["water_id"]], self.events.get(w["water_id"], []), self.notices.get("regulations", {}),
                self.notices.get("health", {}), self.curated, self.notices.get("source_changes", {}), trip, self.data_date,
                self.notices.get("state_parks_alerts", {}))
        self.by_id = {w["water_id"]: w for w in self.waters}
        self.near_place = {w["water_id"]: self.nearest_place(w) for w in self.waters}

    # ---------- helpers ----------
    def local(self, iso, fmt="%b %-d, %Y %-I:%M %p"):
        if not iso:
            return "never"
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")) if isinstance(iso, str) else iso
        return dt.astimezone(self.tz).strftime(fmt) + (" PT" if "%p" in fmt else "")

    def ts(self, iso):
        return f'<time datetime="{E(iso or "")}" data-rel>{E(self.local(iso))}</time>'

    def stale(self, key):
        s = self.status.get(key)
        if not s or not s.get("last_success"):
            return True, "never successfully checked"
        age_h = (self.built_at - datetime.fromisoformat(s["last_success"])).total_seconds() / 3600
        limit = self.cfg["stale_after_hours"].get(key, 36)
        if s.get("status") == "failed":
            return True, f"latest refresh failed ({self.local(s['last_attempt'])}); showing data last confirmed {self.local(s['last_success'])}"
        if age_h > limit:
            return True, f"not refreshed for {age_h:.0f} hours"
        return False, ""

    def nearest_place(self, w):
        c = w["lake_centre"]
        best = min(self.places, key=lambda p: km(c["lat"], c["lon"], p["lat"], p["lon"]))
        return best["name"], miles(km(c["lat"], c["lon"], best["lat"], best["lon"]))

    def url(self, path):
        return self.base + path

    def agency(self, u):
        return AGENCY.get(urlparse(u).netloc, urlparse(u).netloc)

    def src(self, u, label=None):
        return (f'<a class="src js-track" data-track="source_click" href="{E(u)}" rel="noopener" target="_blank">'
                f'{E(label or self.agency(u))}</a>')

    def manager_word(self, ap):
        return ap["manager"].replace(" (Tacoma Public Utilities)", "")

    # ---------- field rendering: UNKNOWN never becomes NO ----------
    def field(self, f, manager, lake_level=False):
        s, v = f["state"], f["value"]
        if s == "YES" and "CLOSED" in v:      # exists but closed (e.g. Spanaway pier): never a green "Yes"
            return "no", "Closed", v
        if s == "UNKNOWN":
            if f.get("provenance") and "CONFLICT" in v:
                return "unknown", "Unclear: official sources conflict", "See the data-quality notes below"
            who = "official sources" if lake_level else manager
            note = v if v and v != "Not stated" else ""
            return "unknown", f"Not stated by {who}", note
        return s.lower(), STATE_WORD[s], v

    def pass_fee(self, ap):
        p, f = ap["pass_required"], ap["parking_or_access_fee"]
        m = self.manager_word(ap)
        if p["state"] == "UNKNOWN" and f["state"] == "UNKNOWN":
            return "unknown", f"Not stated by {m}", ""
        parts = []
        if p["state"] == "YES":
            parts.append(p["value"])
        elif p["state"] == "NO":
            parts.append(p["value"])
        if f["state"] in ("YES", "NO") and not f["value"].startswith("Pass only"):
            parts.append(f["value"] if f["state"] == "YES" else f"No fee: {f['value']}")
        elif f["state"] == "YES":
            parts.append(f["value"].replace("Pass only: ", ""))
        if p["state"] == "UNKNOWN":
            parts.append(f"Pass requirement not stated by {m}")
        if f["state"] == "UNKNOWN":
            parts.append(f"parking fee not stated by {m}" + (f" ({f['value']})" if f["value"] != "Not stated" else ""))
        state = "yes" if (p["state"] == "YES" or f["state"] == "YES") else "no" if (p["state"] == "NO" and f["state"] in ("NO", "UNKNOWN")) else "unknown"
        return state, "Required" if state == "yes" else ("None required" if state == "no" and f["state"] == "NO" else "See details"), " · ".join(parts)

    def pass_fee_short(self, ap):
        """Card form: pass name + first price. Full sourced wording stays on the lake page."""
        p, f = ap["pass_required"], ap["parking_or_access_fee"]
        if p["state"] == "UNKNOWN" and f["state"] == "UNKNOWN":
            return "unknown", f"Not stated by {self.manager_word(ap)}"
        price = re.search(r"\$\s?\d+(?:/day)?", f["value"]) if f["state"] == "YES" else None
        price = price.group(0).replace("$ ", "$") if price else ""
        if p["state"] == "YES":
            txt = re.sub(r"\s*\(.*?\)", "", p["value"]) + (f" · {price}" if price else "")
            return "yes", txt
        if f["state"] == "YES":
            first = re.sub(r"\s*\(.*?\)", "", f["value"].split(";")[0])
            return "yes", first + (" · no Discover Pass" if p["state"] == "NO" else "")
        if f["state"] == "NO" and p["state"] == "NO":
            return "no", "None stated"
        return "unknown", ("No Discover Pass needed; parking fee not stated" if p["state"] == "NO"
                           else f"Pass not stated by {self.manager_word(ap)}; no day-use fee listed")

    def row(self, ic, label, cls, word, detail, sources=()):
        s = "".join(f" {self.src(u)}" for u in dict.fromkeys(sources))
        return (f'<div class="fact {cls}"><dt>{icon(ic)}{E(label)}</dt><dd><strong>{E(word)}</strong>'
                f'{(" " + E(detail)) if detail else ""}{("<span class=srcs>" + s + "</span>") if s else ""}</dd></div>')

    def prov_urls(self, f):
        return [p["source_url"].split(" (")[0] for p in f.get("provenance", [])]

    # ---------- page chrome ----------
    def page(self, path, title, desc, body, extra_head="", jsonld=None, index=True):
        canon = self.url(path)
        robots = "" if (self.production and index) else '<meta name="robots" content="noindex">'
        ga = ""
        if self.cfg["ga4_measurement_id"]:
            gid = E(self.cfg["ga4_measurement_id"])
            ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>'
                  f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag("js",new Date());gtag("config","{gid}");</script>')
        gsv = f'<meta name="google-site-verification" content="{E(self.cfg["google_site_verification"])}">' if self.cfg["google_site_verification"] else ""
        ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
        doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canon)}">
{robots}{gsv}
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}"><meta property="og:url" content="{E(canon)}"><meta property="og:type" content="website">
<link rel="stylesheet" href="/assets/style.css">
<meta name="theme-color" content="#1f4d3a">
{ld}{extra_head}{ga}
</head>
<body>
<header class="top"><a class="brand" href="/">{E(self.cfg["site_name"])}</a>
<nav><a href="/">Trip finder</a><a href="/recently-stocked/">Recently stocked</a><a href="/lakes/">Lakes</a><a href="/methodology/">How it works</a></nav></header>
<main id="main">
{body}
</main>
<footer class="foot"><p>Independent site; not affiliated with WDFW or any land manager. Stocking data: WDFW Fish Plants (data.wa.gov). Access facts come from each official manager's pages and are linked on every lake page.
Always check posted signs and the <a href="https://www.eregulations.com/washington/fishing/" rel="noopener">WDFW sport fishing rules</a>.</p>
<p><a href="/methodology/">Methodology &amp; sources</a> · <a href="/data-quality/">Data quality &amp; corrections</a> · Built {E(self.local(self.built_at.isoformat()))}</p></footer>
<script src="/assets/site.js" defer></script>
</body></html>
"""
        p = self.out / path.lstrip("/") / "index.html" if path.endswith("/") else self.out / path.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8")
        if index and path != "/404.html":
            self.pages.append(path)

    # ---------- freshness ----------
    def freshness_block(self, wid=None, compact=False):
        lines = []
        s = self.status.get("stocking", {})
        bad, why = self.stale("stocking")
        upd = self.stock_meta.get("dataset_rows_updated_at")
        upd_txt = self.local(datetime.fromtimestamp(upd, timezone.utc).isoformat()) if upd else "unknown"
        lines.append(f'<li class="{"stale" if bad else ""}"><b>Stocking:</b> WDFW data published {E(upd_txt)}; we last checked it {self.ts(s.get("last_success"))}'
                     + (f' <span class="stalewarn">STALE: {E(why)}</span>' if bad else "") + "</li>")
        lines.append(f'<li><b>Access details:</b> last reviewed {E(date.fromisoformat(self.access_reviewed).strftime("%b %-d, %Y"))} '
                     f'(static facts; not live reporting)'
                     + ("" if self.stale("access_source_pages")[0] else f'. Official pages re-checked for changes {self.ts(self.status.get("access_source_pages", {}).get("last_success"))}')
                     + "</li>")
        nsrc = [("wdfw_emergency_rules", "WDFW emergency rules"), ("ecology_toxic_algae", "Ecology toxic-algae list")]
        if wid is None or any(a["manager_type"] == "state_park" for a in self.access[wid]["access_points"]):
            nsrc.append(("wa_state_parks_alerts", "State Parks alerts"))
        parts = []
        for k, label in nsrc:
            b, w = self.stale(k)
            parts.append(f'{E(label)} {self.ts(self.status.get(k, {}).get("last_success"))}' + (f' <span class="stalewarn">STALE: {E(w)}</span>' if b else ""))
        lines.append("<li><b>Notices checked:</b> " + "; ".join(parts) + "</li>")
        return f'<ul class="fresh{" compact" if compact else ""}">' + "".join(lines) + "</ul>"

    # ---------- lake card (homepage / city / alternatives) ----------
    def card_data(self, w):
        st, a = self.st[w["water_id"]], self.access[w["water_id"]]
        catch = [[r["release_start_date"], r["number_released"], r["species"]] for r in st["stocking"]["all"] if r["class"] == "catchable"]
        wins = [{"cat": f["cat"], "key": f["key"], "windows": f["windows"], "season": bool(f.get("season")),
                 "notice": bool(f.get("notice")), "out_level": f.get("out_level"), "in_level": f.get("in_level"),
                 "label_in": f.get("label_in"), "label_out": f.get("label_out"), "text": f["text"]}
                for f in st["flags"] if f.get("windows")]
        return {"lat": w["lake_centre"]["lat"], "lon": w["lake_centre"]["lon"], "catch": catch, "windows": wins,
                "shore": a["bank_fishing_status"]["state"], "dock": a["fishing_pier_or_dock"]["state"],
                "restricted": st["restricted"]}

    def card(self, w, dist_mi=None, compact=False):
        wid = w["water_id"]
        st, a = self.st[wid], self.access[wid]
        prim = next(x for x in a["access_points"] if x["primary"])
        stg = st["stocking"]
        if stg["recent"]:
            rec = f'{stg["recent_total"]:,} {"/".join(s.lower() for s in stg["recent_species"])} · {el.fmt_range([r["date"] for r in stg["recent"]])}'
            rec_cls = "yes"
        else:
            lc = stg["last_catchable"]
            rec = "No catchable-size stocking reported in the last 30 days" + (f' (last: {lc["date"]:%b %-d, %Y})' if lc else "")
            rec_cls = "unknown"
        shore = self.field(a["bank_fishing_status"], None, True)
        dock = self.field(a["fishing_pier_or_dock"], None, True)
        park = self.field(prim["parking_available"], self.manager_word(prim))
        pf = self.pass_fee_short(prim)
        hrs = self.field(prim["operating_hours"], self.manager_word(prim))
        flags = [f for f in st["flags"] if f["level"] in ("blocking", "warn", "restricted") and not f.get("windows")]
        flag_html = "".join(f'<li class="flag {E(f["level"])} cat-{E(f["cat"])}" data-key="{E(f["key"])}"><span class="cat">{E(CAT[f["cat"]])}</span> {E(f["text"])}</li>' for f in flags)
        win_html = "".join(f'<li class="flag {E(f["level"])} cat-{E(f["cat"])}" data-win="{i}"{"" if f["level"] in ("blocking", "warn", "restricted") else " hidden"}><span class="cat">{E(CAT[f["cat"]])}</span> <span class="t">{E(f["text"])}</span></li>'
                           for i, f in enumerate([f for f in st["flags"] if f.get("windows")]))
        flag_html += win_html
        none_hidden = any(f["level"] in ("blocking", "warn", "restricted") for f in st["flags"])
        alt = self.alternatives(w, 1)
        dd = json.dumps(self.card_data(w), separators=(",", ":"))
        return f"""<article class="card" id="lake-{E(w['slug'])}" data-lake='{E(dd)}' data-slug="{E(w['slug'])}">
<h3><a class="js-track" data-track="lake_result_click" href="/lakes/{E(w['slug'])}/">{E(w['display_name'])}</a> <span class="where">{E(", ".join(w['counties']))} Co.<span class="dist">{f" · ~{dist_mi:.0f} mi straight-line" if dist_mi is not None else ""}</span></span></h3>
<dl class="facts">
<div class="fact {rec_cls}" data-role="recent"><dt>{icon("fish")}Recently stocked</dt><dd><strong>{E(rec)}</strong></dd></div>
<div class="fact {shore[0]}"><dt>{icon("shore")}Shore fishing</dt><dd><strong>{E(shore[1])}</strong></dd></div>
<div class="fact {dock[0]}"><dt>{icon("dock")}Pier / dock</dt><dd><strong>{E(dock[1])}</strong>{(" " + E(dock[2])) if dock[0] in ("yes", "no") and "CLOSED" in dock[2] else ""}</dd></div>
<div class="fact {park[0]}"><dt>{icon("park")}Parking</dt><dd><strong>{E(park[1])}</strong></dd></div>
<div class="fact {pf[0]}"><dt>{icon("pass")}Pass / fee</dt><dd><strong>{E(pf[1])}</strong></dd></div>
<div class="fact {hrs[0]}"><dt>{icon("clock")}Hours</dt><dd><strong>{E(hrs[2] if hrs[0] != "unknown" else hrs[1])}</strong></dd></div>
</dl>
<ul class="flags" data-role="flags">{flag_html}<li class="flag none" data-role="noflags"{" hidden" if none_hidden else ""}>No current issues identified from monitored official sources</li></ul>
<p class="why" data-role="why">{("Why it appears: " + E("; ".join(st["why"]))) if st["qualifies"] else ""}</p>
{f'<p class="alt">Nearby alternative: <a class="js-track" data-track="alternative_click" href="/lakes/{E(alt[0][0]["slug"])}/">{E(alt[0][0]["display_name"])}</a> (~{alt[0][1]:.0f} mi)</p>' if alt else ""}
</article>"""

    def alternatives(self, w, n=4):
        c = w["lake_centre"]
        out = []
        for o in self.waters:
            if o is w:
                continue
            d = miles(km(c["lat"], c["lon"], o["lake_centre"]["lat"], o["lake_centre"]["lon"]))
            if d <= self.cfg["nearby_alternative_radius_miles"]:
                s = self.st[o["water_id"]]
                out.append((o, d, s))
        out.sort(key=lambda t: (not t[2]["qualifies"], bool(t[2]["blocking"]), t[2]["restricted"], t[1]))
        return out[:n]

    def ranked(self, lst):
        return sorted(lst, key=lambda w: (not self.st[w["water_id"]]["qualifies"], bool(self.st[w["water_id"]]["blocking"]),
                                          -(self.st[w["water_id"]]["stocking"]["last_catchable"]["date"].toordinal()
                                            if self.st[w["water_id"]]["stocking"]["last_catchable"] else 0)))

    # ---------- pages ----------
    def home(self):
        q = [w for w in self.ranked(self.waters) if self.st[w["water_id"]]["qualifies"]]
        rest = [w for w in self.ranked(self.waters) if not self.st[w["water_id"]]["qualifies"]]
        places = json.dumps([[p["name"], round(p["lat"], 4), round(p["lon"], 4)] for p in self.places], separators=(",", ":"))
        opts = "".join(f'<option value="{E(p["name"])}">' for p in self.places)
        body = f"""<section class="intro"><h1>Recently stocked lakes you can fish from shore</h1>
<p>Catchable trout reported stocked by WDFW in the last 30 days, plus documented public shore access, parking, passes and current notices. {len(self.waters)} validated Washington lakes.</p></section>
<form id="finder" class="finder" onsubmit="return false" aria-label="Trip finder" data-trip="{self.trip.isoformat()}" data-data-date="{self.data_date.isoformat()}">
<div class="from"><label>From <input id="f-place" list="places" placeholder="Town, e.g. Tacoma" autocomplete="off"><datalist id="places">{opts}</datalist></label>
<button type="button" id="f-geo" class="btn-sec">Use my location</button></div>
<label>Trip date <input id="f-date" type="date" value="{self.trip.isoformat()}" min="{self.trip.isoformat()}" max="{date.fromordinal(self.trip.toordinal() + 21).isoformat()}"></label>
<label>Max distance <select id="f-max"><option value="10">10 mi</option><option value="25" selected>25 mi</option><option value="40">40 mi</option><option value="60">60 mi</option><option value="999">Any</option></select></label>
<details class="more"><summary>More filters</summary>
<label class="chk"><input id="f-shore" type="checkbox" checked> Shore/bank access required</label>
<label>Pier/dock <select id="f-dock"><option value="any">Any</option><option value="prefer">Prefer</option><option value="require">Required</option></select></label>
<label class="chk"><input id="f-hide-restricted" type="checkbox"> Hide waters restricted to juveniles/seniors/disabled anglers</label>
</details>
</form>
<script id="places-data" type="application/json">{places}</script>
<p class="note">Distances are straight-line miles, not driving distance.</p>
<p id="f-status" class="status" role="status">Showing lakes for {E(self.trip.strftime("%a %b %-d, %Y"))}, newest catchable stocking first. Add a starting place to sort by distance.</p>
<section><h2 id="r-h">Recently stocked + shore access <span id="r-count">({len(q)})</span></h2>
<div id="results" class="cards">{"".join(self.card(w) for w in q)}</div></section>
<section><h2>Other validated lakes <span class="sub">(no catchable stocking reported in the last 30 days, or no documented shore access)</span></h2>
<div id="others" class="cards">{"".join(self.card(w) for w in rest)}</div></section>
{self.freshness_block()}
"""
        self.page("/", f"Recently Stocked Lakes for Shore Fishing in Washington | {self.cfg['site_name']}",
                  "Find Washington lakes with recently stocked catchable trout and documented shore access, with parking, pass, hours and notice details from official sources.",
                  body, extra_head='<script src="/assets/finder.js" defer></script>',
                  jsonld={"@context": "https://schema.org", "@type": "WebSite", "name": self.cfg["site_name"], "url": self.url("/")})

    def lake(self, w):
        wid = w["water_id"]
        a, st = self.access[wid], self.st[wid]
        prim = next(x for x in a["access_points"] if x["primary"])
        stg = st["stocking"]
        mgr = self.manager_word(prim)
        np_name, np_mi = self.near_place[wid]
        shore = self.field(a["bank_fishing_status"], None, True)
        dock = self.field(a["fishing_pier_or_dock"], None, True)
        park = self.field(prim["parking_available"], mgr)
        pf = self.pass_fee(prim)
        hrs = self.field(prim["operating_hours"], mgr)
        seas = self.field(prim["seasonal_access"], mgr)
        if stg["recent"]:
            rec_word = f'{stg["recent_total"]:,} {"/".join(s.lower() for s in stg["recent_species"])}'
            rec_detail = f'{el.fmt_range([r["date"] for r in stg["recent"]])} (catchable size)'
            rec_cls = "yes"
        else:
            rec_word = "None in the last 30 days"
            lc = stg["last_catchable"]
            rec_detail = f'Last catchable-size plant: {lc["date"]:%b %-d, %Y}' if lc else "No catchable-size plant in the last 12 months"
            rec_cls = "unknown"
        cats = {"regulation": [], "physical_access": [], "health": [], "data": []}
        for f in st["flags"]:
            if f["level"] != "inactive":
                cats[f["cat"]].append(f)

        def flag_li(f):
            extra = ""
            if f.get("rules"):
                extra = "<ul>" + "".join(f'<li>{self.src(r["url"], r["title"])}</li>' for r in f["rules"]) + "</ul>"
            srcs = [f["source"]] if f.get("source") else f.get("sources", [])
            posted = f' (posted {E(f["posted"])})' if f.get("posted") else ""
            return (f'<li class="flag {E(f["level"])}">{E(f["text"])}{posted} '
                    + " ".join(self.src(s) for s in srcs) + extra + "</li>")
        notices_html = ""
        for cat, title in (("regulation", "Fishing regulations"), ("physical_access", "Physical access"),
                           ("health", "Health advisories"), ("data", "Data notes")):
            items = cats[cat]
            if cat == "health" and not items:
                body_ = f'<li class="flag none">Not on WA Ecology\'s list of lakes above toxic-algae guidelines (checked {self.ts(self.status.get("ecology_toxic_algae", {}).get("last_success"))}). {self.src("https://www.nwtoxicalgae.org/")}</li>'
            elif not items:
                body_ = '<li class="flag none">None identified from monitored official sources</li>'
            else:
                body_ = "".join(flag_li(f) for f in items)
            notices_html += f'<h3>{E(title)}</h3><ul class="flags">{body_}</ul>'
        above = f"""<dl class="facts big">
{self.row("fish", "Recently stocked", rec_cls, rec_word, rec_detail, ["https://data.wa.gov/dataset/WDFW-Fish-Plants/6fex-3r7d"])}
{self.row("shore", "Shore fishing", shore[0], shore[1], shore[2], self.prov_urls(a["bank_fishing_status"]))}
{self.row("dock", "Pier / dock", dock[0], dock[1], dock[2], self.prov_urls(a["fishing_pier_or_dock"]))}
{self.row("access", "Main access", "yes", prim["name"], f"managed by {prim['manager']}", [prim["url"]])}
{self.row("park", "Parking", park[0], park[1], park[2], self.prov_urls(prim["parking_available"]))}
{self.row("pass", "Pass / fee", pf[0], pf[1], pf[2], self.prov_urls(prim["pass_required"]) + self.prov_urls(prim["parking_or_access_fee"]))}
{self.row("clock", "Hours", hrs[0], hrs[1], hrs[2], self.prov_urls(prim["operating_hours"]))}
{self.row("season", "Seasonal access", seas[0], seas[1], seas[2], self.prov_urls(prim["seasonal_access"]))}
</dl>"""
        top_flags = [f for f in st["flags"] if f["level"] in ("blocking", "warn", "restricted")]
        crit = [f for f in st["flags"] if f["level"] in ("blocking", "restricted") or (f["cat"] == "health" and f["level"] == "warn")]
        before = (f'<div class="before" role="note"><b>Before you go ({E(self.trip.strftime("%a %b %-d"))}):</b><ul>'
                  + "".join(f'<li>{E(f["text"])}</li>' for f in crit) + "</ul></div>") if crit else ""
        issues = ("".join(f'<li class="flag {E(f["level"])}"><span class="cat">{E(CAT[f["cat"]])}</span> {E(f["text"])}</li>' for f in top_flags)
                  or '<li class="flag none">None identified from monitored official sources</li>')
        rows = []
        for r in stg["all"][:40]:
            rows.append(f'<tr class="{E(r["class"])}"><td>{r["date"]:%b %-d, %Y}</td><td>{E(r["species"] or "")}</td>'
                        f'<td class="num">{r["number_released"]:,}</td><td class="num">{"" if r["number_of_fish_per_pound"] is None else f"{r["number_of_fish_per_pound"]:g}"}</td>'
                        f'<td>{E(el.LABEL[r["class"]])}</td></tr>')
        stock_tbl = ('<div class="tblwrap"><table><thead><tr><th>Date</th><th>Species</th><th>Number</th><th>Fish/lb</th><th>Size class</th></tr></thead><tbody>'
                     + "".join(rows) + "</tbody></table></div>") if rows else "<p>No reported plants in the last 12 months.</p>"
        shore_quotes = "".join(f'<li>“{E(p["quote"])}” {self.src(p["source_url"].split(" (")[0])}</li>' for p in a["bank_fishing_status"]["provenance"])
        pts = a.get("shore_fishing_points", [])
        pts_html = "".join(f'<li>{E(p["description"])}: <a class="js-track" data-track="source_click" href="https://www.google.com/maps/search/?api=1&amp;query={p["lat"]:.5f},{p["lon"]:.5f}" rel="noopener" target="_blank">open point in maps</a> (WDFW shore-fishing site)</li>' for p in pts)
        ap_html = ""
        for ap in a["access_points"]:
            m = self.manager_word(ap)
            pf2 = self.pass_fee(ap)
            coords = ap.get("access_coordinates")
            ap_html += f"""<section class="ap"><h3>{E(ap["name"])} <span class="sub">({E(ap["manager"])}{", main access" if ap["primary"] else ""})</span></h3><dl class="facts">
{self.row("park", "Parking", *self.field(ap["parking_available"], m), self.prov_urls(ap["parking_available"]))}
{self.row("pass", "Pass / fee", *pf2, self.prov_urls(ap["pass_required"]) + self.prov_urls(ap["parking_or_access_fee"]))}
{self.row("clock", "Hours", *self.field(ap["operating_hours"], m), self.prov_urls(ap["operating_hours"]))}
{self.row("season", "Seasonal access", *self.field(ap["seasonal_access"], m), self.prov_urls(ap["seasonal_access"]))}
{self.row("dock", "Fishing platform", *self.field(ap["fishing_platform"], m), self.prov_urls(ap["fishing_platform"])) if "fishing_platform" in ap else ""}
</dl><p>{self.src(ap["url"], "Official page")}{f' · <a class="js-track" data-track="source_click" href="https://www.google.com/maps/search/?api=1&amp;query={coords["lat"]:.5f},{coords["lon"]:.5f}" rel="noopener" target="_blank">Open documented access point in maps</a>' if coords else ""}</p></section>"""
        rules = "".join(f'<li>“{E(n["quote"])}” {self.src(n["source_url"])}</li>' for n in a["rule_notes"])
        alts = self.alternatives(w)
        alt_html = "".join(self.alt_li(o, d, s) for o, d, s in alts) or "<li>No other validated lake within 25 miles.</li>"
        srcs = {}
        for f in ("bank_fishing_status", "fishing_pier_or_dock"):
            for p in a[f]["provenance"]:
                srcs[p["source_url"].split(" (")[0]] = p.get("retrieved_at")
        for ap in a["access_points"]:
            for v in ap.values():
                if isinstance(v, dict) and "provenance" in v:
                    for p in v["provenance"]:
                        srcs[p["source_url"].split(" (")[0]] = p.get("retrieved_at")
        for n in a["rule_notes"]:
            srcs[n["source_url"]] = n.get("retrieved_at")
        srcs[w["official_wdfw_url"]] = srcs.get(w["official_wdfw_url"])
        srcs["https://data.wa.gov/dataset/WDFW-Fish-Plants/6fex-3r7d"] = self.status.get("stocking", {}).get("last_success")
        srcs[w["emergency_rules_url"]] = self.status.get("wdfw_emergency_rules", {}).get("last_success")
        srcs["https://www.eregulations.com/washington/fishing/"] = None
        srcs["https://www.nwtoxicalgae.org/"] = self.status.get("ecology_toxic_algae", {}).get("last_success")
        src_html = "".join(f'<li>{self.src(u, self.agency(u) + ": " + u.split("://", 1)[1][:80])}</li>' for u in sorted(srcs))
        title = f"{w['display_name']} Fishing — Stocking & Shore Access | {self.cfg['site_name']}"
        recent_txt = (f"{stg['recent_total']:,} catchable {'/'.join(s.lower() for s in stg['recent_species'])} stocked {el.fmt_range([r['date'] for r in stg['recent']])}"
                      if stg["recent"] else "Recent WDFW stocking")
        desc = (f"{recent_txt}. Shore fishing: {STATE_WORD[a['bank_fishing_status']['state']].lower()}; pier/dock: "
                f"{STATE_WORD[a['fishing_pier_or_dock']['state']].lower()}. Parking, pass, hours and notices for {w['display_name']} "
                f"({', '.join(w['counties'])} County, WA), with official sources.")
        body = f"""<nav class="crumbs"><a href="/">Trip finder</a> › <a href="/lakes/">Lakes</a> › {E(w["display_name"])}</nav>
<h1>{E(w["display_name"])} Fishing — Stocking &amp; Shore Access</h1>
<p class="lede">{E(", ".join(w["counties"]))} County, WA · nearest Census place: {E(np_name)} (~{np_mi:.0f} mi) · main access managed by {E(prim["manager"])}</p>
<section class="decision" aria-label="Trip decision summary">
{before}
{above}
<h2 class="issues-h">Current issues for {E(self.trip.strftime("%a %b %-d"))}</h2><ul class="flags">{issues}</ul>
{self.freshness_block(wid, compact=True)}
</section>
<section><h2>Recent stocking</h2>
<p>Completed releases reported by WDFW (Fish Plants dataset), last 12 months. Only <b>catchable-size</b> trout/kokanee (3 or fewer fish per pound, WDFW's own threshold) count toward "recently stocked". Smaller fish are listed but not counted.</p>
{f'<p class="note">{E(stg["data_limit_note"])}.</p>' if stg["data_limit_note"] else ""}
{stock_tbl}</section>
<section><h2>Shore access</h2>
<p><strong>{E(shore[1])}</strong>{(": " + E(shore[2])) if shore[2] else ""}</p>
<ul class="quotes">{shore_quotes}</ul>
{f'<h3>WDFW-documented shore fishing points</h3><ul>{pts_html}</ul>' if pts_html else '<p class="note">No WDFW-documented shore-fishing points for this lake; see the official pages for where to fish.</p>'}
</section>
<section><h2>Access points, parking, passes &amp; hours</h2>{ap_html}</section>
<section><h2>Current notices</h2><p class="note">Kept separate on purpose: a fishing rule, a park closure and a health advisory are different facts. This site does not declare a lake "open" or "closed".</p>{notices_html}
{f'<h3>Lake rules from WDFW</h3><ul class="quotes">{rules}</ul>' if rules else ""}
<p>Full rules: {self.src("https://www.eregulations.com/washington/fishing/", "WDFW sport fishing rules pamphlet")} · {self.src(w["emergency_rules_url"], "WDFW emergency rules for this lake")}</p></section>
<section><h2>Nearby alternatives</h2><ul class="alts">{alt_html}</ul></section>
<p class="note"><a href="/data-quality/">All known data issues and how to report a correction</a></p>
<section><h2>Sources</h2><ul class="sources">{src_html}</ul>
<p class="note">Official WDFW lake page: {self.src(w["official_wdfw_url"])}. Stocking matched via release location “{E(", ".join(x["alias"] for x in self.aliases if x["water_id"] == wid))}” (confirmed).</p></section>
"""
        jsonld = [{"@context": "https://schema.org", "@type": "LakeBodyOfWater", "name": w["display_name"],
                   "geo": {"@type": "GeoCoordinates", "latitude": w["lake_centre"]["lat"], "longitude": w["lake_centre"]["lon"]},
                   "containedInPlace": {"@type": "AdministrativeArea", "name": f"{', '.join(w['counties'])} County, Washington"},
                   "sameAs": w["official_wdfw_url"]},
                  {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                      {"@type": "ListItem", "position": 1, "name": "Trip finder", "item": self.url("/")},
                      {"@type": "ListItem", "position": 2, "name": "Lakes", "item": self.url("/lakes/")},
                      {"@type": "ListItem", "position": 3, "name": w["display_name"], "item": self.url(f"/lakes/{w['slug']}/")}]}]
        self.page(f"/lakes/{w['slug']}/", title, desc, body, jsonld=jsonld)

    def alt_li(self, o, d, s):
        stg = s["stocking"]
        rec = (f'catchable stocking {el.fmt_range([r["date"] for r in stg["recent"]])}' if stg["recent"] else "no catchable stocking in 30 days")
        warn = []
        if s["restricted"]:
            warn.append("restricted to juveniles/seniors/disabled anglers")
        warn += [f["text"] for f in s["blocking"]]
        a = self.access[o["water_id"]]
        return (f'<li><a class="js-track" data-track="alternative_click" href="/lakes/{E(o["slug"])}/">{E(o["display_name"])}</a> '
                f'~{d:.0f} mi · {E(rec)} · shore {E(STATE_WORD[a["bank_fishing_status"]["state"]].lower())}, dock {E(STATE_WORD[a["fishing_pier_or_dock"]["state"]].lower())}'
                + (f' <span class="flag warn inline">{E("; ".join(warn))}</span>' if warn else "") + "</li>")

    def lakes_index(self):
        items = "".join(f'<li><a href="/lakes/{E(w["slug"])}/">{E(w["display_name"])}</a> <span class="sub">{E(", ".join(w["counties"]))} County · shore {E(STATE_WORD[self.access[w["water_id"]]["bank_fishing_status"]["state"]].lower())}'
                        f'{" · stocked recently" if self.st[w["water_id"]]["qualifies"] else ""}</span></li>'
                        for w in sorted(self.waters, key=lambda w: w["display_name"]))
        body = f"""<h1>Validated lakes</h1><p>The {len(self.waters)} waters in v0.1. Each was identity-checked against WDFW lake pages and has a sourced shore-access record.</p><ul class="lakelist">{items}</ul>"""
        self.page("/lakes/", f"Washington Stocked Lakes With Shore Access (All {len(self.waters)}) | {self.cfg['site_name']}",
                  f"All {len(self.waters)} validated Washington lakes: stocking, shore access, docks, parking and passes from official sources.", body)

    def recently_stocked(self):
        rec, other = [], []
        for w in self.waters:
            for r in self.st[w["water_id"]]["stocking"]["recent"]:
                rec.append((r, w))
            for r in self.st[w["water_id"]]["stocking"]["non_catchable_recent"]:
                other.append((r, w))
        rec.sort(key=lambda t: t[0]["date"], reverse=True)
        other.sort(key=lambda t: t[0]["date"], reverse=True)

        def tr(r, w, cls=True):
            a = self.access[w["water_id"]]
            return (f'<tr><td>{r["date"]:%b %-d}</td><td><a href="/lakes/{E(w["slug"])}/">{E(w["display_name"])}</a></td><td>{E(r["species"])}</td>'
                    f'<td class="num">{r["number_released"]:,}</td><td class="num">{"" if r["number_of_fish_per_pound"] is None else f"{r["number_of_fish_per_pound"]:g}"}</td>'
                    + (f'<td>{E(STATE_WORD[a["bank_fishing_status"]["state"]])}</td>' if cls else f'<td>{E(el.LABEL[r["class"]])}</td>') + "</tr>")
        none = [w for w in self.waters if not self.st[w["water_id"]]["stocking"]["recent"]]
        body = f"""<h1>Recently stocked lakes in Washington (catchable trout)</h1>
<p>Catchable-size trout and kokanee (3 or fewer fish per pound) reported stocked by WDFW in the last 30 days at the {len(self.waters)} validated lakes, as of {E(self.trip.strftime("%b %-d, %Y"))}. These are completed releases, not the annual stocking plan.</p>
{self.freshness_block(compact=True)}
<div class="tblwrap"><table><thead><tr><th>Date</th><th>Lake</th><th>Species</th><th>Number</th><th>Fish/lb</th><th>Shore</th></tr></thead><tbody>{"".join(tr(r, w) for r, w in rec) or '<tr><td colspan=6>None in the last 30 days.</td></tr>'}</tbody></table></div>
<h2>Other releases in the last 30 days (not counted)</h2>
<p>Fry, fingerlings and other releases smaller than catchable size, or with size not reported. They are listed for completeness and do not make a lake "recently stocked" for a shore trip.</p>
<div class="tblwrap"><table><thead><tr><th>Date</th><th>Lake</th><th>Species</th><th>Number</th><th>Fish/lb</th><th>Size class</th></tr></thead><tbody>{"".join(tr(r, w, False) for r, w in other) or '<tr><td colspan=6>None.</td></tr>'}</tbody></table></div>
<h2>No catchable stocking in the last 30 days</h2><p>{", ".join(f'<a href="/lakes/{E(w["slug"])}/">{E(w["display_name"])}</a>' for w in none) or "None."}</p>"""
        self.page("/recently-stocked/", f"Recently Stocked Lakes in Washington — Catchable Trout | {self.cfg['site_name']}",
                  "Catchable-size trout reported stocked by WDFW in the last 30 days at Washington lakes with documented shore access. Fry plants listed separately.", body)

    def city_pages(self):
        cfg = self.cfg["city_pages"]
        placemap = {p["name"]: p for p in self.places}
        published, decisions = [], []
        for c in cfg["candidates"]:
            p = placemap.get(c)
            if not p:
                decisions.append({"city": c, "published": False, "reason": "not in Census place list"})
                continue
            near = sorted(((w, miles(km(p["lat"], p["lon"], w["lake_centre"]["lat"], w["lake_centre"]["lon"]))) for w in self.waters),
                          key=lambda t: t[1])
            near = [(w, d) for w, d in near if d <= cfg["radius_miles"]]
            ids = {w["water_id"] for w, _ in near}
            overlap = max((len(ids & s) / len(ids | s) for _, s in published), default=0) if ids else 0
            if len(near) < cfg["min_lakes"]:
                decisions.append({"city": c, "published": False, "lakes": len(near), "reason": f"fewer than {cfg['min_lakes']} validated lakes within {cfg['radius_miles']} mi"})
                continue
            if overlap > cfg["max_overlap"]:
                decisions.append({"city": c, "published": False, "lakes": len(near), "reason": f"{overlap:.0%} overlap with an already-published area page (thin duplicate)"})
                continue
            published.append((c, ids))
            decisions.append({"city": c, "published": True, "lakes": len(near), "overlap": round(overlap, 2)})
            q = [(w, d) for w, d in near if self.st[w["water_id"]]["qualifies"]]
            docks = sum(self.access[w["water_id"]]["fishing_pier_or_dock"]["state"] == "YES" for w, _ in near)
            restricted = [w["display_name"] for w, _ in near if self.st[w["water_id"]]["restricted"]]
            slug = c.lower()
            body = f"""<nav class="crumbs"><a href="/">Trip finder</a> › Near {E(c)}</nav>
<h1>Stocked lakes near {E(c)} for shore fishing</h1>
<p>{len(near)} validated lakes within about {cfg["radius_miles"]} straight-line miles of {E(c)} (US Census place point). As of {E(self.trip.strftime("%b %-d, %Y"))}, <b>{len(q)}</b> had catchable trout reported stocked in the last 30 days with documented shore access. {docks} have a public pier or dock.
{(" Restricted to juveniles, seniors and disabled anglers: " + E(", ".join(restricted)) + ".") if restricted else ""}</p>
<p class="note">Distances are straight-line, not driving distance. Use the <a href="/">trip finder</a> for a different date or starting point.</p>
<div class="cards">{"".join(self.card(w, d) for w, d in sorted(near, key=lambda t: (not self.st[t[0]["water_id"]]["qualifies"], bool(self.st[t[0]["water_id"]]["blocking"]), t[1])))}</div>
{self.freshness_block(compact=True)}"""
            self.page(f"/near/{slug}/", f"Stocked Lakes Near {c} for Shore Fishing | {self.cfg['site_name']}",
                      f"{len(near)} lakes near {c}, WA with WDFW stocking, shore access, docks, parking and passes. {len(q)} with catchable trout stocked in the last 30 days.", body)
        self.city_decisions = decisions

    def methodology(self):
        cd = "".join(f'<li>{E(d["city"])}: {"published" if d["published"] else "not published"}{(" — " + E(d["reason"])) if d.get("reason") else ""}{f" ({d["lakes"]} lakes)" if d.get("lakes") is not None else ""}</li>' for d in self.city_decisions)
        body = f"""<h1>How this site works</h1>
<h2>What it answers</h2><p>Which recently stocked lake can I realistically fish from shore, and what do I need to know before driving there? It combines four kinds of facts and keeps them separate: <b>stocking events</b>, <b>physical access</b>, <b>fishing regulations</b> and <b>health advisories</b>. It never declares a lake "open" or "closed".</p>
<h2>Which lakes</h2><p>v0.1 covers {len(self.waters)} hand-validated waters. Each lake's identity was checked against its official WDFW lake page, its stocking records are attached only through confirmed release-location names, and its access facts were reviewed on {E(date.fromisoformat(self.access_reviewed).strftime("%b %-d, %Y"))} with a verbatim quote and link for every value.</p>
<h2>"Recently stocked" means catchable size</h2>
<ul><li>Source: WDFW Fish Plants dataset (data.wa.gov 6fex-3r7d), which holds <b>completed, reported releases</b>. The annual stocking plan (planned releases) is not used anywhere on this site.</li>
<li>Counted: trout/kokanee with <b>3 or fewer fish per pound</b>. This is the threshold WDFW's own lake pages use for "catchable" plants. Lifestage labels are not used because they are inconsistent in the source.</li>
<li>Not counted: fry and fingerlings (more than 3 fish per pound), releases with no size reported, and other species. These are shown in stocking tables but never make a lake "recently stocked".</li>
<li>Recent = released within {el.RECENT_DAYS} days before your trip date. This is a planning window, not a claim about how many fish remain. Stocking after WDFW's latest data publication cannot be known.</li></ul>
<h2>Shore access and unknowns</h2>
<ul><li>Shore access is read from WDFW's shoreline notes, WDFW shore-fishing site points and manager pages. WDFW's shoreline rating is "Good" on almost every page, even where the note says access is limited, so the note decides.</li>
<li>If an official source does not state something, the site says <b>"Not stated by &lt;manager&gt;"</b>. Silence is never shown as "No" or "No fee". Where official sources conflict, the site says so.</li>
<li>Where one lake has several managers (e.g. a WDFW ramp and a city park dock), each access point is shown separately, because passes and fees differ.</li></ul>
<h2>Notices and freshness</h2>
<ul><li>WDFW emergency rules: checked for each lake through WDFW's per-lake emergency-rule listing (includes statewide rules).</li>
<li>Toxic algae: WA Dept of Ecology's list of lakes above guidelines. A listing attaches to a lake only by Ecology site ID, or by a name held by exactly one official WDFW water; ambiguous names (e.g. "Green Lake", "Clear Lake") are never attached automatically.</li>
<li>Park closures and construction: dated notices on manager pages, plus automatic change detection on every cited page. A changed page flags the lake as possibly out of date until re-reviewed.</li>
<li>Every source shows when it was last checked successfully. If a refresh fails, the last known data stays up, labelled <b>STALE</b> with the failure time; a failed check never counts as a fresh one.</li></ul>
<h2>Identity safeguards</h2>
<p>WDFW's geo_code is used as supporting evidence only. Known source errors are handled by explicit overrides: Long Lake (Thurston) stocking carries Long's Pond's code and is excluded from Long's Pond; the Warm Beach Lake Martha is kept apart from Martha Lake (Lynnwood); derby events and separate ponds that share a lake's code are not attached. Any new release location carrying one of these lakes' codes goes to a review queue instead of being attached.</p>
<h2>Distances</h2><p>Straight-line miles from a US Census place point (or your device location, which stays in your browser) to the lake centre in WDFW's lake data. They are not driving distances.</p>
<h2>Area pages</h2><p>An area page is published only if at least {self.cfg["city_pages"]["min_lakes"]} validated lakes lie within {self.cfg["city_pages"]["radius_miles"]} miles and its lakes overlap no more than {self.cfg["city_pages"]["max_overlap"]:.0%} with an area page already published.</p><ul>{cd}</ul>
<h2>Sources</h2><ul><li>{self.src("https://data.wa.gov/dataset/WDFW-Fish-Plants/6fex-3r7d", "WDFW Fish Plants (data.wa.gov)")}</li><li>{self.src("https://wdfw.wa.gov/fishing/locations/lowland-lakes", "WDFW lowland lake pages")}</li><li>{self.src("https://wdfw.wa.gov/places-to-go/water-access-sites", "WDFW water access areas")}</li><li>{self.src("https://wdfw.wa.gov/fishing/regulations/emergency-rules", "WDFW emergency fishing rules")}</li><li>{self.src("https://www.eregulations.com/washington/fishing/", "WDFW sport fishing rules pamphlet")}</li><li>{self.src("https://www.nwtoxicalgae.org/", "WA Dept of Ecology freshwater algae")}</li><li>{self.src("https://parks.wa.gov/", "Washington State Parks")}</li><li>County, city and utility park pages, linked on each lake page</li><li>{self.src("https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html", "US Census Gazetteer (place points)")}</li></ul>"""
        self.page("/methodology/", f"Methodology & Sources | {self.cfg['site_name']}",
                  "How lakes are selected, what counts as recently stocked catchable trout, how unknown and conflicting facts are shown, and where every fact comes from.", body)

    def data_quality(self):
        conflicts = "".join(f'<li><a href="/lakes/{E(self.by_id[r["water_id"]]["slug"])}/">{E(self.by_id[r["water_id"]]["display_name"])}</a>: {E(c)}</li>'
                            for r in self.access.values() for c in r["data_conflicts"])
        excl = "".join(f'<li>“{E(a["alias"])}”: {E(a["reason"])}</li>' for a in self.aliases if a["status"] == "excluded")
        kinds = {}
        for i in self.queue:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        qtxt = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in kinds.items()) or "none"
        contact = self.cfg["contact_email"]
        body = f"""<h1>Data quality &amp; corrections</h1>
<p>This site depends on trust, so known problems are listed here instead of hidden.</p>
<h2>Open review items</h2><p>{E(qtxt)}. Items appear when an official page changes, a source cannot be reached, or a new stocking location carries a validated lake's code.</p>
<h2>Known source conflicts</h2><ul>{conflicts}</ul>
<h2>Stocking records deliberately not attached</h2><ul>{excl}</ul>
<h2>Known limitations</h2><ul>
<li>Pass and fee rules are often not stated on city and county park pages. Those are shown as "Not stated", never as free.</li>
<li>WDFW water access areas publish seasonal open dates but no daily hours.</li>
<li>Closures announced only on signs or social media cannot be seen by this site.</li>
<li>WDFW's shoreline rating is not used on its own; the shoreline note is.</li></ul>
<h2>Report a correction</h2><p>{(f'Email <a href="mailto:{E(contact)}">{E(contact)}</a> with the lake, what is wrong, and an official link if you have one.') if contact else 'Correction contact: not yet configured (pre-launch).'}</p>"""
        self.page("/data-quality/", f"Data Quality & Corrections | {self.cfg['site_name']}",
                  "Known source conflicts, records deliberately not attached, open review items and how to report a correction.", body)

    def not_found(self):
        self.page("/404.html", f"Page not found | {self.cfg['site_name']}", "Page not found.",
                  '<h1>Page not found</h1><p><a href="/">Go to the trip finder</a> or <a href="/lakes/">browse lakes</a>.</p>', index=False)

    def sitemap_robots(self):
        today = self.built_at.date().isoformat()
        urls = "".join(f"<url><loc>{E(self.url(p))}</loc><lastmod>{today}</lastmod></url>" for p in self.pages)
        (self.out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
        robots = (f"User-agent: *\nAllow: /\nSitemap: {self.url('/sitemap.xml')}\n" if self.production
                  else "User-agent: *\nDisallow: /\n# non-production build\n")
        (self.out / "robots.txt").write_text(robots)

    def build(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "assets").mkdir(parents=True)
        for f in (MVP / "site/static").iterdir():
            shutil.copy(f, self.out / "assets" / f.name)
        self.home()
        for w in self.waters:
            self.lake(w)
        self.lakes_index()
        self.recently_stocked()
        self.city_pages()
        self.methodology()
        self.data_quality()
        self.not_found()
        self.sitemap_robots()
        report = {"built_at": self.built_at.isoformat(), "trip_date": self.trip.isoformat(), "production": self.production,
                  "pages": self.pages, "lake_pages": len(self.waters), "city_pages": self.city_decisions,
                  "qualifying_lakes": [w["display_name"] for w in self.waters if self.st[w["water_id"]]["qualifies"]],
                  "stale_sources": {k: self.stale(k)[1] for k in self.status if self.stale(k)[0]}}
        (self.out / "build_report.json").write_text(json.dumps(report, indent=1))
        return report


CAT = {"regulation": "Rule", "physical_access": "Access", "health": "Health", "data": "Data"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--data-dir")
    ap.add_argument("--out", default=str(MVP / "dist"))
    ap.add_argument("--production", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((MVP / "config.json").read_text())
    tz = ZoneInfo(cfg["timezone"]) if ZoneInfo else timezone.utc
    trip = date.fromisoformat(a.date) if a.date else datetime.now(tz).date()
    rep = Site(a.data_dir, a.out, trip, a.production).build()
    print(f"built {len(rep['pages'])} indexable pages ({rep['lake_pages']} lakes); qualifying today: {len(rep['qualifying_lakes'])}; "
          f"city pages: {[d['city'] for d in rep['city_pages'] if d['published']]}; stale: {rep['stale_sources'] or 'none'}")


if __name__ == "__main__":
    main()
