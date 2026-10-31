"""MVP tests: known identity/data exceptions, UNKNOWN handling, catchable logic, freshness,
SEO basics. Run: python3 -m unittest discover -s mvp/tests -v   (no network needed)."""
import copy
import html
import json
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

MVP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MVP / "pipeline"))
sys.path.insert(0, str(MVP / "site"))
import common  # noqa: E402
import eligibility as el  # noqa: E402
import refresh_notices  # noqa: E402
import refresh_stocking  # noqa: E402
import build_site  # noqa: E402

DATA = MVP / "data"
TRIP = date(2026, 10, 31)


CONFIG = json.loads((MVP / "config.json").read_text())
BASE = CONFIG["base_url"]


def built(trip=TRIP, data_dir=None, production=False, config_path=None):
    out = Path(tempfile.mkdtemp(prefix="mvp-dist-"))
    site = build_site.Site(str(data_dir or DATA), out, trip, production, config_path)
    site.build()
    return out, site


def text(path):
    return html.unescape(re.sub(r"<[^>]+>", " ", path.read_text()))


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.site = built()
        cls.waters = json.loads((DATA / "waters.json").read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out)

    def test_all_lake_pages_build_with_unique_seo(self):
        titles, descs = set(), set()
        sitemap = (self.out / "sitemap.xml").read_text()
        self.assertEqual(len(self.waters), 20)
        for w in self.waters:
            p = self.out / "lakes" / w["slug"] / "index.html"
            self.assertTrue(p.exists(), w["slug"])
            s = p.read_text()
            t = html.unescape(re.search(r"<title>(.*?)</title>", s).group(1))
            d = re.search(r'<meta name="description" content="(.*?)">', s).group(1)
            self.assertIn(f'<link rel="canonical" href="{BASE}/lakes/{w["slug"]}/">', s)
            self.assertTrue(t.startswith(f"{w['display_name']} Fishing — Stocking & Shore Access") and t.endswith("| Shorelio"), t)
            self.assertIn(f"/lakes/{w['slug']}/</loc>", sitemap)
            self.assertGreater(len(d), 80)
            titles.add(t)
            descs.add(d)
            self.assertIn('name="viewport"', s)
        self.assertEqual(len(titles), 20)
        self.assertEqual(len(descs), 20)
        self.assertNotIn("?", sitemap.replace('<?xml version="1.0" encoding="UTF-8"?>', ""))

    def test_non_production_is_noindex_and_production_refuses_placeholders(self):
        for f in self.out.rglob("*.html"):
            self.assertIn('content="noindex"', f.read_text(), f)
        self.assertIn("Disallow: /", (self.out / "robots.txt").read_text())
        if not CONFIG["contact_email"]:          # the committed config must still be refused
            with self.assertRaises(SystemExit):
                built(production=True)
        bad = build_site.production_config_problems
        ok = {"site_name": "Shorelio", "base_url": "https://shorelio.com", "contact_email": "help@shorelio.com"}
        self.assertEqual(bad(ok), [])
        for k, v in (("base_url", "http://shorelio.com"), ("base_url", "https://example.invalid"),
                     ("base_url", "https://jgav-droid.github.io"), ("base_url", "http://localhost:8000"),
                     ("base_url", "https://shorelio.com/site"), ("contact_email", ""),
                     ("contact_email", "x@example.com"), ("contact_email", "not-an-email")):
            self.assertTrue(bad({**ok, k: v}), (k, v))

    def test_branding(self):
        home = (self.out / "index.html").read_text()
        self.assertIn("<title>Recently Stocked Lakes in Washington With Shore Access | Shorelio</title>", home)
        self.assertIn("Find a fishing spot you can actually use.", home)
        self.assertNotIn("Find a fishing spot you can actually use.", (self.out / "lakes/ward-lake/index.html").read_text())
        for f in self.out.rglob("*.html"):
            t = f.read_text()
            self.assertIn('content="Shorelio"', t)            # og:site_name
            self.assertNotIn("Washington Stocked Lake Finder", t)

    def test_martha_is_confirmed_lynnwood_entity(self):
        m = text(self.out / "lakes/martha-lake-lynnwood/index.html")
        self.assertIn("WDFW name: Martha Alderwood Manor", m)
        self.assertIn("https://wdfw.wa.gov/fishing/locations/lowland-lakes/martha-alderwood-manor", (self.out / "lakes/martha-lake-lynnwood/index.html").read_text())
        self.assertNotIn("martha-lake-snohomish", (self.out / "lakes/martha-lake-lynnwood/index.html").read_text())

    def test_decision_block_precedes_long_content(self):
        s = (self.out / "lakes/battle-ground-lake/index.html").read_text()
        self.assertLess(s.index('class="decision"'), s.index("<h2>Recent stocking</h2>"))
        self.assertLess(s.index("Shore access"), s.index("<h2>Sources &amp; freshness</h2>"))

    def test_unknown_never_becomes_no(self):
        g = text(self.out / "lakes/green-lake-seattle/index.html")
        self.assertIn("Not stated by Seattle Parks and Recreation", g)
        for bad in ("No fee", "Free parking", "free parking", "No pass required"):
            self.assertNotIn(bad, g)
        for slug in ("angle-lake", "longs-pond", "bradley-lake"):
            self.assertIn("Not stated by", text(self.out / f"lakes/{slug}/index.html"))
        # every UNKNOWN field renders as "Not stated"/"Unclear", never "No"
        for w in self.waters:
            for f in self.site.access[w["water_id"]]["access_points"]:
                for k in ("parking_available", "pass_required", "operating_hours"):
                    if f[k]["state"] == "UNKNOWN":
                        cls, word, _ = self.site.field(f[k], "X")
                        self.assertEqual(cls, "unknown")
                        self.assertTrue(word.startswith("Not stated") or word.startswith("Unclear"))

    def test_conflict_and_limited_labels(self):
        k = text(self.out / "lakes/lake-kapowsin/index.html")
        self.assertIn("Unclear: official sources conflict", k)
        b = (self.out / "lakes/battle-ground-lake/index.html").read_text()
        # our LIMITED classification is shown (WDFW's rating says "Good"), next to its sourced explanation
        self.assertRegex(b, r'Shore access</dt><dd><span class="v">Limited bank access; a trail around the lake leads to shore spots '
                            r'<span class="badge limited">Limited shore access</span>')
        self.assertNotIn(">Good<", b)
        sp = (self.out / "lakes/spanaway-lake/index.html").read_text()
        self.assertRegex(sp, r'Pier / dock</dt><dd><span class="v"><strong>Closed</strong>')

    def test_fry_do_not_count_as_recent_catchable(self):
        st = self.site.st["wa-w-american-lake"]
        self.assertFalse(st["qualifies"])
        oct14 = [r for r in st["stocking"]["all"] if r["release_start_date"] == "2026-10-14"]
        self.assertTrue(oct14 and all(r["class"] == "below_catchable_size" for r in oct14))
        rs = (self.out / "recently-stocked/index.html").read_text()
        main_tbl, other_tbl = rs.split("Other releases in the last 30 days")
        self.assertNotIn("American Lake", main_tbl.split("<tbody>", 1)[1])
        self.assertIn("American Lake", other_tbl)
        self.assertFalse(self.site.st["wa-w-lake-meridian"]["qualifies"])  # Oct 20 plants were fry

    def test_season_windows_and_notices_by_date(self):
        ward = self.site.st["wa-w-ward-lake"]
        self.assertTrue(any(f["key"] == "access_season" and f["level"] == "blocking" for f in ward["flags"]))
        _, s_nov = built(date(2026, 11, 1))
        _, s_oct = built(date(2026, 10, 15))
        fs = lambda s: [f for f in s.st["wa-w-clear-lake-pierce"]["flags"] if f["key"] == "fishing_season"][0]["level"]
        self.assertEqual(fs(s_nov), "blocking")
        self.assertEqual(fs(s_oct), "ok")
        span = lambda s: [f for f in s.st["wa-w-spanaway-lake"]["flags"] if f["key"] == "notice" and "vehicles" in f["text"]][0]["level"]
        self.assertEqual(span(s_oct), "inactive")       # closure starts Oct 24
        self.assertEqual(span(s_nov), "blocking")

    def test_restricted_waters_flagged(self):
        for wid in ("wa-w-longs-pond", "wa-w-lake-bradley"):
            self.assertTrue(self.site.st[wid]["restricted"])
        self.assertFalse(self.site.st["wa-w-battle-ground-lake"]["restricted"])

    def test_internal_links_resolve(self):
        missing = set()
        for f in self.out.rglob("*.html"):
            for href in re.findall(r'href="(/[^"#?]*)"', f.read_text()):
                target = self.out / href.lstrip("/")
                if not (target.is_file() or (target / "index.html").is_file()):
                    missing.add((str(f.relative_to(self.out)), href))
        self.assertEqual(missing, set())

    def test_city_pages_are_not_thin(self):
        cities = {d["city"]: d for d in self.site.city_decisions}
        self.assertFalse(cities["Puyallup"]["published"])
        for c, d in cities.items():
            if d["published"]:
                self.assertGreaterEqual(d["lakes"], 3)
                self.assertTrue((self.out / "near" / c.lower() / "index.html").exists())


class HomepageRedesign(unittest.TestCase):
    """Presentation-only redesign: cards are simpler, but every warning they showed before
    is still rendered, grouped in one 'Before you go' area."""

    @classmethod
    def setUpClass(cls):
        cls.out, cls.site = built()
        cls.home = (cls.out / "index.html").read_text()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out)

    def card_html(self, slug):
        m = re.search(rf'<article class="card" id="lake-{slug}".*?</article>', self.home, re.S)
        self.assertIsNotNone(m, slug)
        return m.group(0)

    def test_every_active_warning_still_on_its_card(self):
        for w in self.site.waters:
            c = html.unescape(self.card_html(w["slug"]))
            for f in self.site.st[w["water_id"]]["flags"]:
                if f["level"] in ("blocking", "warn", "restricted"):
                    self.assertIn(f["text"], c, (w["slug"], f["text"]))
            active = any(f["level"] in ("blocking", "warn", "restricted") for f in self.site.st[w["water_id"]]["flags"])
            self.assertEqual('data-role="before" hidden' in c, not active, w["slug"])
            self.assertEqual('data-role="noflags" hidden' in c, active, w["slug"])

    def test_known_warnings_visible(self):
        self.assertIn("Before you go", self.card_html("ward-lake"))
        self.assertIn("outside its listed open dates", html.unescape(self.card_html("ward-lake")))
        self.assertIn("sev-block", self.card_html("ward-lake"))
        self.assertIn("juvenile anglers", html.unescape(self.card_html("longs-pond")))
        sp = html.unescape(self.card_html("spanaway-lake"))
        self.assertIn("closed to vehicles", sp)
        self.assertIn("Toxic algae", sp)
        self.assertIn("No current issues found", self.card_html("battle-ground-lake"))

    def test_cards_drop_status_tile_grid(self):
        res = self.home.split('id="results"', 1)[1]
        self.assertNotIn('class="fact ', res)          # no six-tile grid on the homepage
        self.assertNotIn('class="why"', res)

    def test_other_lakes_are_collapsed_and_light(self):
        self.assertRegex(self.home, r'<details class="others" id="others-wrap"><summary>')
        self.assertIn('<div id="others" class="cards compact">', self.home)
        n_q = sum(self.site.st[w["water_id"]]["qualifies"] for w in self.site.waters)
        self.assertIn(f'<b id="o-count">{20 - n_q}</b> other validated lakes', self.home)

    def test_no_distance_without_location(self):
        self.assertNotRegex(self.home, r'class="dist">[^<]+<')   # empty until the user gives a place

    def test_home_links_are_plain_and_resettable(self):
        self.assertIn('<a class="brand" href="/" data-home-reset>', self.home)
        self.assertNotRegex(self.home, r'href="/#')

    def test_url_state_unit_tests_pass(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        import subprocess
        r = subprocess.run([node, "--test", str(MVP / "tests/url_state.test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class LakeDetailRedesign(unittest.TestCase):
    """Presentation-only redesign of lake pages: trip decision first, quick facts in plain
    language, evidence secondary. Every fact, warning and source must still be on the page."""

    @classmethod
    def setUpClass(cls):
        cls.out, cls.site = built()
        cls.waters = json.loads((DATA / "waters.json").read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out)

    def page(self, slug):
        return (self.out / "lakes" / slug / "index.html").read_text()

    def decision(self, slug):
        s = self.page(slug)
        return s[s.index('<section class="decision"'):s.index('<div class="details">')]

    def rows(self, html_):
        out = {}
        for k, v in re.findall(r'<div class="row [a-z]+"><dt>(.*?)</dt><dd><span class="v">(.*?)</span>', html_):
            out[html.unescape(k)] = html.unescape(re.sub(r"<[^>]+>", "", v)).strip()
        return out

    def test_quick_facts_are_never_a_bare_category(self):
        bare = {"Yes", "No", "Limited", "Unknown", "Not stated", "Closed", "Required", "See details"}
        for w in self.waters:
            q = self.rows(self.decision(w["slug"]))
            self.assertEqual(list(q)[:6], ["Recent stocking", "Shore access", "Pier / dock", "Parking", "Pass / fee", "Hours"], w["slug"])
            for k, v in q.items():
                self.assertNotIn(v, bare, (w["slug"], k))
                self.assertGreater(len(v), 8, (w["slug"], k, v))

    def test_shore_and_dock_show_sourced_explanation(self):
        for w in self.waters:
            a = self.site.access[w["water_id"]]
            q = self.rows(self.decision(w["slug"]))
            shore, dock = a["bank_fishing_status"], a["fishing_pier_or_dock"]
            if shore["state"] != "UNKNOWN":
                self.assertTrue(q["Shore access"].startswith(shore["value"]), w["slug"])
                tag = {"YES": "Public shore fishing", "LIMITED": "Limited shore access", "NO": "No public shore access"}[shore["state"]]
                self.assertTrue(q["Shore access"].endswith(tag), w["slug"])
            if dock["state"] in ("YES", "NO"):
                self.assertIn(dock["value"], q["Pier / dock"], w["slug"])
            elif "CONFLICT" in dock["value"]:
                self.assertEqual(q["Pier / dock"], "Unclear: official sources conflict")
            else:
                self.assertEqual(q["Pier / dock"], "Pier or dock not stated by official sources", w["slug"])
        self.assertEqual(self.rows(self.decision("ward-lake"))["Hours"], "Hours not stated by WDFW")
        self.assertEqual(self.rows(self.decision("ward-lake"))["Parking"], "1 parking lot")
        self.assertTrue(self.rows(self.decision("spanaway-lake"))["Pier / dock"].startswith("Closed · "))
        self.assertEqual(self.rows(self.decision("longs-pond"))["Pass / fee"], "Pass / fee not stated by City of Lacey")

    def test_unknown_is_never_presented_as_no(self):
        for w in self.waters:
            a = self.site.access[w["water_id"]]
            prim = next(x for x in a["access_points"] if x["primary"])
            q = self.rows(self.decision(w["slug"]))
            for label, f in (("Parking", prim["parking_available"]), ("Hours", prim["operating_hours"]),
                             ("Pier / dock", a["fishing_pier_or_dock"])):
                if f["state"] == "UNKNOWN":
                    self.assertTrue(re.search(r"not stated by|^Unclear", q[label]), (w["slug"], label, q[label]))

    def test_every_active_warning_is_in_the_trip_decision(self):
        for w in self.waters:
            st, d = self.site.st[w["water_id"]], self.decision(w["slug"])
            active = [f for f in st["flags"] if f["level"] in ("blocking", "warn", "restricted")]
            for f in active:
                self.assertIn(html.escape(f["text"]), d, (w["slug"], f["key"]))
            self.assertEqual('class="trip-alert' in d, bool(active), w["slug"])
            self.assertEqual("No current issues found" in d, not active, w["slug"])
            if any(f["level"] == "blocking" for f in active):
                self.assertIn("trip-alert sev-block", d)
        self.assertIn("outside its listed open dates", self.decision("ward-lake"))
        sp = self.decision("spanaway-lake")
        self.assertIn("Fantasy Lights", sp)
        self.assertIn("Toxic algae", sp)
        self.assertIn("juvenile anglers", self.decision("longs-pond"))
        self.assertIn("juvenile anglers", self.decision("bradley-lake"))

    def test_warnings_not_hidden_in_collapsed_sections(self):
        for w in self.waters:
            s = self.page(w["slug"])
            for blk in re.findall(r"<details.*?</details>", s, re.S):
                self.assertNotIn('class="flag', blk, w["slug"])
            n = s[s.index('id="notices"'):s.index('id="nearby"')]
            for f in self.site.st[w["water_id"]]["flags"]:
                if f["level"] != "inactive":
                    self.assertIn(html.escape(f["text"]), n, (w["slug"], f["key"]))

    def test_sources_are_secondary_but_all_reachable(self):
        for w in self.waters:
            s, d = self.page(w["slug"]), self.decision(w["slug"])
            self.assertNotIn('class="src', d, w["slug"])              # no inline source links in the decision layer
            self.assertIn('href="#sources"', d)
            self.assertNotIn('class="fresh', d)                        # freshness lives in Sources & freshness
            a = self.site.access[w["water_id"]]
            urls = [p["source_url"].split(" (")[0] for k in ("bank_fishing_status", "fishing_pier_or_dock") for p in a[k]["provenance"]]
            for ap in a["access_points"]:
                urls.append(ap["url"])
                urls += [p["source_url"].split(" (")[0] for v in ap.values() if isinstance(v, dict) for p in v.get("provenance", [])]
            for u in set(urls):
                self.assertIn(f'href="{html.escape(u)}"', s, (w["slug"], u))
            for p in a["bank_fishing_status"]["provenance"]:
                self.assertIn(html.escape(p["quote"]), s)               # verbatim evidence still on the page
            self.assertIn('id="sources"', s)
            self.assertLess(s.index('class="decision"'), s.index('id="sources"'))

    def test_stale_data_is_flagged_in_the_decision_layer(self):
        tmp = Path(tempfile.mkdtemp())
        for f in DATA.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        st = json.loads((tmp / "source_status.json").read_text())
        st["ecology_toxic_algae"]["last_success"] = "2026-10-20T00:00:00+00:00"
        (tmp / "source_status.json").write_text(json.dumps(st))
        out, _ = built(data_dir=tmp)
        s = (out / "lakes/battle-ground-lake/index.html").read_text()
        d = s[s.index('<section class="decision"'):s.index('<div class="details">')]
        self.assertIn("STALE", d)
        self.assertIn("Ecology toxic-algae list", d)
        self.assertNotIn("STALE", self.decision("battle-ground-lake"))
        shutil.rmtree(out)
        shutil.rmtree(tmp)


class Production(unittest.TestCase):
    """Production path, verified with a temporary config whose only change is a test-only
    contact address (never committed, never deployed)."""

    @classmethod
    def setUpClass(cls):
        cfg = dict(CONFIG, contact_email="launch-check@shorelio.test")
        cls.cfg_path = Path(tempfile.mkdtemp()) / "config.json"
        cls.cfg_path.write_text(json.dumps(cfg))
        cls.out, cls.site = built(production=True, config_path=cls.cfg_path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out)

    def test_indexable_with_production_urls(self):
        self.assertEqual(BASE, "https://shorelio.com")
        robots = (self.out / "robots.txt").read_text()
        self.assertIn("Allow: /", robots)
        self.assertNotIn("Disallow", robots)
        self.assertIn("Sitemap: https://shorelio.com/sitemap.xml", robots)
        locs = re.findall(r"<loc>(.*?)</loc>", (self.out / "sitemap.xml").read_text())
        self.assertEqual(len(locs), len(set(locs)))
        for loc in locs:
            self.assertTrue(loc.startswith("https://shorelio.com/") and "?" not in loc and "#" not in loc, loc)
            f = self.out / loc[len("https://shorelio.com/"):] / "index.html" if loc.endswith("/") else self.out / loc[len("https://shorelio.com/"):]
            t = f.read_text()
            self.assertNotIn("noindex", t, loc)
            self.assertIn(f'<link rel="canonical" href="{loc}">', t)
            self.assertIn(f'<meta property="og:url" content="{loc}">', t)
        paths = {l[len("https://shorelio.com"):] for l in locs}
        for must in ("/", "/recently-stocked/", "/lakes/", "/methodology/", "/data-quality/",
                     "/near/seattle/", "/near/tacoma/", "/near/vancouver/", "/near/olympia/"):
            self.assertIn(must, paths)
        self.assertNotIn("/near/puyallup/", paths)
        self.assertNotIn("/404.html", paths)
        self.assertEqual(sum(p.startswith("/lakes/") and p != "/lakes/" for p in paths), 20)

    def test_no_dev_or_placeholder_urls_in_output(self):
        for f in list(self.out.rglob("*.html")) + [self.out / "sitemap.xml", self.out / "robots.txt"]:
            t = f.read_text()
            for bad in ("example.invalid", "localhost", "127.0.0.1", "github.io", "http://shorelio", "Washington Stocked Lake Finder"):
                self.assertNotIn(bad, t, (f, bad))

    def test_finder_state_never_creates_urls(self):
        js = (MVP / "site/static/finder.js").read_text()
        self.assertIn('history.replaceState(null, "", s ? clean + "#" + s : clean)', js)
        self.assertNotRegex(js, r"location\.search|pushState|\?from=")
        home = (self.out / "index.html").read_text()
        self.assertIn('<link rel="canonical" href="https://shorelio.com/">', home)
        self.assertNotRegex(home, r'href="/\?')


class Identity(unittest.TestCase):
    def setUp(self):
        self.aliases = json.loads((DATA / "aliases.json").read_text())

    def test_only_confirmed_aliases_publish(self):
        for a in self.aliases:
            if a["status"] == "confirmed":
                self.assertTrue(a["level"] in ("A", "B") or a["level"].endswith("_reviewed"), a)
            else:
                self.assertIsNone(a["water_id"])

    def test_known_exclusions_present(self):
        ex = {a["alias"] for a in self.aliases if a["status"] == "excluded"}
        for k in ("LONG LK (THUR)", "MARTHA LK (WB) (SNOH)", "MORTON DERBY (LEWI)", "KLINELINE PONDS"):
            self.assertIn(k, ex)
        conf = {a["alias"]: a["water_id"] for a in self.aliases if a["status"] == "confirmed"}
        self.assertEqual(conf["LONGS PD (THUR)"], "wa-w-longs-pond")
        self.assertEqual(conf["MARTHA LK (AM) (SNOH)"], "wa-w-martha-alderwood-manor")

    def test_stocking_never_attached_by_geo_code(self):
        """Fixture: WDFW returns Long Lake's rows (code L2818 = Long's Pond's code) and a new
        name carrying L2818. Neither may attach; the new name goes to review."""
        tmp = Path(tempfile.mkdtemp())
        for f in ("aliases.json", "waters.json"):
            shutil.copy(DATA / f, tmp / f)
        rows = [{"release_location": "LONGS PD (THUR)", "release_start_date": "2026-10-26T00:00:00.000", "species": "Cutthroat",
                 "species_type": "Trout/Kokanee", "number_released": "150", "number_of_fish_per_pound": "1.6", "geo_code": "L2818"},
                {"release_location": "LONG LK (THUR)", "release_start_date": "2026-10-20T00:00:00.000", "species": "Rainbow",
                 "species_type": "Trout/Kokanee", "number_released": "3000", "number_of_fish_per_pound": "2.5", "geo_code": "L2818"}]
        groups = [{"release_location": "LONG LK (THUR)", "geo_code": "L2818", "county": "Thurston", "latest": "2026-10-20", "n": "1"},
                  {"release_location": "LONGS PD NORTH (THUR)", "geo_code": "L2818", "county": "Thurston", "latest": "2026-10-21", "n": "2"}]
        calls = []

        def fake_soda(params):
            calls.append(params["$where"])
            return (rows if "release_location in" in params["$where"] else groups), "https://data.wa.gov/fixture"
        orig_soda, orig_get = refresh_stocking.soda, refresh_stocking._http.get_json
        refresh_stocking.soda = fake_soda
        refresh_stocking._http.get_json = lambda *a, **k: ({"status": 200, "error": None}, {"rowsUpdatedAt": 1793432004})
        try:
            self.assertEqual(refresh_stocking.main(str(tmp), today=TRIP), 0)
        finally:
            refresh_stocking.soda, refresh_stocking._http.get_json = orig_soda, orig_get
        ev = json.loads((tmp / "stocking_events.json").read_text())["events"]
        self.assertEqual([e["alias"] for e in ev], ["LONGS PD (THUR)"])
        self.assertIn("release_location in", calls[0])
        self.assertNotIn("geo_code", calls[0])
        q = json.loads((tmp / "review_queue.json").read_text())["items"]
        self.assertEqual([i["release_location"] for i in q], ["LONGS PD NORTH (THUR)"])   # excluded LONG LK not re-queued
        shutil.rmtree(tmp)

    def test_martha_decision_recorded(self):
        conf = {a["alias"]: a for a in self.aliases}
        am, wb = conf["MARTHA LK (AM) (SNOH)"], conf["MARTHA LK (WB) (SNOH)"]
        self.assertEqual(am["human_decision"]["status"], "confirmed")
        self.assertEqual(am["human_decision"]["decision"], "Martha Lake = Martha Lake (Alderwood Manor / Lynnwood), Snohomish County")
        self.assertTrue(am["evidence"])                       # evidence preserved
        self.assertEqual(wb["status"], "excluded")
        self.assertIsNone(wb["water_id"])
        w = {x["slug"]: x for x in json.loads((DATA / "waters.json").read_text())}["martha-lake-lynnwood"]
        self.assertEqual(w["wdfw_geo_code"], "L3217")
        self.assertIn("confirmed by the product owner", w["identity_decision"])

    def test_live_snapshot_has_no_excluded_or_unconfirmed_rows(self):
        ev = json.loads((DATA / "stocking_events.json").read_text())["events"]
        conf = {a["alias"] for a in self.aliases if a["status"] == "confirmed"}
        self.assertTrue(ev)
        self.assertTrue(all(e["alias"] in conf and e["record_kind"] == "reported_plant" for e in ev))


class Eligibility(unittest.TestCase):
    base = {"record_kind": "reported_plant", "species_type": "Trout/Kokanee", "number_released": 100}

    def test_classification(self):
        c = lambda **k: el.classify({**self.base, **k})[0]
        self.assertEqual(c(number_of_fish_per_pound=2.6), "catchable")
        self.assertEqual(c(number_of_fish_per_pound=3.0), "catchable")
        self.assertEqual(c(number_of_fish_per_pound=3.01), "below_catchable_size")
        self.assertEqual(c(number_of_fish_per_pound=40.5), "below_catchable_size")
        for v in (None, 0, 999999):
            self.assertEqual(c(number_of_fish_per_pound=v), "size_not_reported")
        self.assertEqual(c(species_type="Salmon", number_of_fish_per_pound=1.7), "not_counted")
        self.assertEqual(c(number_released=0, number_of_fish_per_pound=2), "not_counted")

    def test_planned_records_rejected(self):
        with self.assertRaises(ValueError):
            el.classify({**self.base, "record_kind": "planned_stocking", "number_of_fish_per_pound": 2})

    def test_recent_window(self):
        evs = [{**self.base, "release_start_date": d, "number_of_fish_per_pound": 2.5, "species": "Rainbow"}
               for d in ("2026-10-01", "2026-09-30", "2026-11-05")]
        s = el.stocking_summary(evs, TRIP, TRIP)
        self.assertEqual([r["release_start_date"] for r in s["recent"]], ["2026-10-01"])   # 30 days back, not future


class Freshness(unittest.TestCase):
    def test_failed_refresh_keeps_data_and_last_success(self):
        tmp = Path(tempfile.mkdtemp())
        for f in DATA.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        before = (tmp / "stocking_events.json").read_text()
        prev = json.loads((tmp / "source_status.json").read_text())["stocking"]["last_success"]
        orig = refresh_stocking._http.get_json
        refresh_stocking._http.get_json = lambda *a, **k: ({"status": None, "error": "Connection reset"}, None)
        try:
            self.assertEqual(refresh_stocking.main(str(tmp), today=TRIP), 1)
        finally:
            refresh_stocking._http.get_json = orig
        st = json.loads((tmp / "source_status.json").read_text())["stocking"]
        self.assertEqual(st["status"], "failed")
        self.assertEqual(st["last_success"], prev)
        self.assertEqual((tmp / "stocking_events.json").read_text(), before)
        out, _ = built(data_dir=tmp)
        home = text(out / "index.html")
        self.assertIn("STALE", home)
        self.assertIn("latest refresh failed", home)
        shutil.rmtree(out)
        shutil.rmtree(tmp)

    def test_suspicious_drop_is_treated_as_failure(self):
        tmp = Path(tempfile.mkdtemp())
        for f in DATA.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        before = (tmp / "stocking_events.json").read_text()
        prev = json.loads((tmp / "source_status.json").read_text())["stocking"]["last_success"]
        orig_soda, orig_get = refresh_stocking.soda, refresh_stocking._http.get_json
        refresh_stocking.soda = lambda params: ([], "https://data.wa.gov/fixture")   # "successful" empty result
        refresh_stocking._http.get_json = lambda *a, **k: ({"status": 200, "error": None}, {"rowsUpdatedAt": 1793432004})
        try:
            self.assertEqual(refresh_stocking.main(str(tmp), today=TRIP), 1)
        finally:
            refresh_stocking.soda, refresh_stocking._http.get_json = orig_soda, orig_get
        st = json.loads((tmp / "source_status.json").read_text())["stocking"]
        self.assertEqual((st["status"], st["last_success"]), ("failed", prev))
        self.assertIn("suspicious drop", st["error"])
        self.assertEqual((tmp / "stocking_events.json").read_text(), before)
        shutil.rmtree(tmp)

    def test_old_success_is_stale_even_without_failure(self):
        tmp = Path(tempfile.mkdtemp())
        for f in DATA.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        st = json.loads((tmp / "source_status.json").read_text())
        st["ecology_toxic_algae"]["last_success"] = "2026-10-20T00:00:00+00:00"
        (tmp / "source_status.json").write_text(json.dumps(st))
        out, _ = built(data_dir=tmp)
        self.assertIn("STALE", text(out / "lakes/spanaway-lake/index.html"))
        shutil.rmtree(out)
        shutil.rmtree(tmp)


class Notices(unittest.TestCase):
    def test_ecology_ambiguous_names_not_attached(self):
        tmp = Path(tempfile.mkdtemp())
        for f in DATA.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        page = ('<table id="c_ExceedanceGridView"><tr><th>Location</th></tr>'
                '<tr><td><a href="Data.aspx?SiteID=55">Spanaway Lake</a></td><td>10/27/2026</td></tr>'
                '<tr><td><a href="Data.aspx?SiteID=901">Green Lake</a></td><td>10/20/2026</td></tr>'
                '<tr><td><a href="Data.aspx?SiteID=902">Clear Lake</a></td><td>10/20/2026</td></tr>'
                '<tr><td><a href="Data.aspx?SiteID=903">Lake Meridian</a></td><td>10/20/2026</td></tr></table>')
        orig = refresh_notices.fetch
        refresh_notices.fetch = lambda url: page
        try:
            refresh_notices.main(str(tmp), only=["health"])
        finally:
            refresh_notices.fetch = orig
        n = json.loads((tmp / "notices.json").read_text())["health"]
        self.assertEqual(n["wa-w-spanaway-lake"][0]["match"], "ecology_site_id")
        self.assertEqual(n["wa-w-lake-meridian"][0]["match"], "unique_name")
        self.assertNotIn("wa-w-green-lake-king", n)
        self.assertNotIn("wa-w-clear-lake-pierce", n)
        kinds = [i["kind"] for i in json.loads((tmp / "review_queue.json").read_text())["items"]]
        self.assertEqual(kinds.count("advisory_ambiguous_name"), 2)
        shutil.rmtree(tmp)

    def test_curated_notices_are_verified_quotes(self):
        cur = json.loads((DATA / "curated_notices.json").read_text())["notices"]
        acc = {r["water_id"]: r for r in json.loads((DATA / "access_facts.json").read_text())["waters"]}
        for wid, items in cur.items():
            quotes = {n["quote"] for n in acc[wid]["current_notices"]}
            for n in items:
                self.assertIn(n["quote"], quotes)


class Provenance(unittest.TestCase):
    def test_every_known_access_field_has_verified_provenance(self):
        acc = json.loads((DATA / "access_facts.json").read_text())["waters"]
        for r in acc:
            fields = [r["bank_fishing_status"], r["fishing_pier_or_dock"]]
            for a in r["access_points"]:
                fields += [v for v in a.values() if isinstance(v, dict) and "state" in v]
            for f in fields:
                if f["state"] != "UNKNOWN" and f.get("confidence") != "ASSESSMENT":
                    self.assertTrue(f["provenance"], (r["water_id"], f))
                    self.assertTrue(all(p["verified_in_cache"] and p["source_url"] for p in f["provenance"]))


class Pipeline(unittest.TestCase):
    def test_content_hash_matches_step1_scheme(self):
        raw = json.loads((common.VALIDATION / "samples/raw_sample.json").read_text())["rows"]
        norm = json.loads((common.VALIDATION / "samples/normalized_sample.json").read_text())
        self.assertEqual(common.content_hash_ids(raw), [n["source_record_id"] for n in norm])

    def test_duplicate_rows_get_distinct_ids(self):
        row = {"release_location": "X", "number_released": "1"}
        self.assertEqual(common.content_hash_ids([row, copy.deepcopy(row)])[1][-2:], "-2")


if __name__ == "__main__":
    unittest.main()
