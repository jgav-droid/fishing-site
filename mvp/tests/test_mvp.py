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


def built(trip=TRIP, data_dir=None, production=False):
    out = Path(tempfile.mkdtemp(prefix="mvp-dist-"))
    site = build_site.Site(str(data_dir or DATA), out, trip, production)
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
            t = re.search(r"<title>(.*?)</title>", s).group(1)
            d = re.search(r'<meta name="description" content="(.*?)">', s).group(1)
            self.assertIn(f'<link rel="canonical" href="https://example.invalid/lakes/{w["slug"]}/">', s)
            self.assertIn(f"/lakes/{w['slug']}/</loc>", sitemap)
            self.assertGreater(len(d), 80)
            titles.add(t)
            descs.add(d)
            self.assertIn('name="viewport"', s)
        self.assertEqual(len(titles), 20)
        self.assertEqual(len(descs), 20)
        self.assertNotIn("?", sitemap.replace('<?xml version="1.0" encoding="UTF-8"?>', ""))

    def test_non_production_is_noindex_and_production_refuses_placeholders(self):
        self.assertIn('content="noindex"', (self.out / "index.html").read_text())
        self.assertIn("Disallow: /", (self.out / "robots.txt").read_text())
        with self.assertRaises(SystemExit):
            built(production=True)

    def test_decision_block_precedes_long_content(self):
        s = (self.out / "lakes/battle-ground-lake/index.html").read_text()
        self.assertLess(s.index('class="decision"'), s.index("<h2>Recent stocking</h2>"))
        self.assertLess(s.index("Shore fishing"), s.index("<h2>Sources</h2>"))

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
        self.assertRegex(b, r"Shore fishing</dt><dd><strong>Limited</strong>")   # WDFW rating says "Good"
        sp = (self.out / "lakes/spanaway-lake/index.html").read_text()
        self.assertRegex(sp, r"Pier / dock</dt><dd><strong>Closed</strong>")

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
