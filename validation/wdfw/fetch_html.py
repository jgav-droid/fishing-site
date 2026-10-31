#!/usr/bin/env python3
"""Probe the two WDFW HTML stocking pages with ordinary GETs.

  plants: https://wdfw.wa.gov/fishing/reports/stocking/trout-plants/all
          (current-year catchable trout plants -- reported activity?)
  plan:   https://wdfw.wa.gov/fishing/reports/stocking/statewide
          (annual hatchery trout & kokanee stocking plan -- intended activity?)

For each page: one request with the honest UA; if that is refused, one
comparison request with a normal browser UA (allowed by the brief). No
challenge solving, no cookies replayed, no retries beyond that.

If the page is HTML with <table>s, the tables are extracted generically
(header row -> dict) and a small sample is saved. Pager links (?page=N) are
followed up to --max-pages with a polite delay.

Outputs:
  out/html_probe.json                 machine summary (gitignored)
  samples/html_<name>_sample.json     header + first rows of each table
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import os

import _http

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SAMPLES = HERE / "samples"
_BASE = os.environ.get("WDFW_TEST_BASE", "https://wdfw.wa.gov")  # mock override for smoke tests
PAGES = {
    "plants": f"{_BASE}/fishing/reports/stocking/trout-plants/all",
    "plan": f"{_BASE}/fishing/reports/stocking/statewide",
}
CHALLENGE_MARKERS = ("just a moment", "cf-chl", "captcha", "access denied", "request unsuccessful",
                     "incapsula", "akamai", "bot detection")
DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.links = [], []
        self._t = self._row = self._cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._t = {"caption": None, "header": [], "rows": []}
        elif tag == "tr" and self._t is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"th": tag == "th", "text": ""}
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            cells = [" ".join(c["text"].split()) for c in self._row]
            if self._row and all(c["th"] for c in self._row) and not self._t["header"]:
                self._t["header"] = cells
            elif cells:
                self._t["rows"].append(cells)
            self._row = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self._t = None


def parse_date(s):
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def fetch(url):
    res = _http.get(url, accept="text/html")
    attempts = [res]
    if res["status"] != 200:
        time.sleep(3)
        attempts.append(_http.get(url, ua=_http.BROWSER_UA, accept="text/html"))
    return attempts


def summarize_attempt(res):
    text = res["body"][:20000].decode("utf-8", "replace").lower()
    return {**{k: v for k, v in _http.loggable(res).items() if k != "body_preview"},
            "challenge_markers": [m for m in CHALLENGE_MARKERS if m in text]}


def probe(name, url, max_pages, delay):
    out = {"url": url, "attempts": [], "tables": []}
    attempts = fetch(url)
    out["attempts"] = [summarize_attempt(a) for a in attempts]
    ok = next((a for a in attempts if a["status"] == 200), None)
    if not ok:
        return out
    ua = _http.BROWSER_UA if ok["user_agent"] == "browser" else _http.HONEST_UA
    p = TableParser()
    p.feed(ok["body"].decode("utf-8", "replace"))
    page_links = sorted({l for l in p.links if re.search(r"[?&]page=\d+", l)})
    out["pager_links"] = page_links[:20]
    # Drupal pager is 0-based; the "last" link gives the final page index
    last_page = max((int(m.group(1)) for l in page_links if (m := re.search(r"page=(\d+)", l))), default=0)
    out["last_page_index"] = last_page
    tables = p.tables
    prev_rows = [t["rows"] for t in p.tables]
    # follow the pager (?page=1, 2, ...) up to the last linked page or max_pages
    pages_fetched = 1
    for n in range(1, min(max_pages, last_page + 1)):
        time.sleep(delay)
        nxt = _http.get(f"{url}?{urllib.parse.urlencode({'page': n})}", ua=ua, accept="text/html")
        out["attempts"].append(summarize_attempt(nxt))
        if nxt["status"] != 200:
            break
        q = TableParser()
        q.feed(nxt["body"].decode("utf-8", "replace"))
        if not q.tables or not any(t["rows"] for t in q.tables):
            break
        if [t["rows"] for t in q.tables] == prev_rows:
            out["stopped_on_repeated_page"] = n
            break
        prev_rows = [t["rows"] for t in q.tables]
        for t, extra in zip(tables, q.tables):
            t["rows"].extend(extra["rows"])
        pages_fetched += 1
    out["pages_fetched"] = pages_fetched

    sample_tables = []
    for t in tables:
        header = t["header"]
        rows = [dict(zip(header, r)) if header and len(r) == len(header) else {"_cells": r} for r in t["rows"]]
        date_cols = [h for h in header if "date" in h.lower()]
        dates = sorted(d for h in date_cols for r in rows if (d := parse_date(r.get(h, ""))))
        info = {"header": header, "row_count_seen": len(rows), "date_columns": date_cols,
                "min_date": dates[0] if dates else None, "max_date": dates[-1] if dates else None,
                "unparsed_date_values": sorted({r.get(h, "") for h in date_cols for r in rows
                                                if r.get(h) and not parse_date(r[h])})[:10]}
        out["tables"].append(info)
        sample_tables.append({**info, "rows": rows[:200]})
    OUT.mkdir(exist_ok=True)
    (OUT / f"html_{name}_all.json").write_text(json.dumps(
        {"retrieved_at": ok["requested_at"], "source_url": url,
         "tables": [{"header": t["header"], "rows": t["rows"]} for t in tables]}))
    SAMPLES.mkdir(exist_ok=True)
    (SAMPLES / f"html_{name}_sample.json").write_text(json.dumps(
        {"retrieved_at": ok["requested_at"], "source_url": url, "user_agent": ok["user_agent"],
         "pages_fetched": pages_fetched, "tables": sample_tables}, indent=2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=3, help="cap; the pager's last link also bounds it")
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--repeat", type=int, default=2, help="re-request each first page N extra times")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    result = {"run_started_at": _http.now_iso(), "pages": {}}
    for name, url in PAGES.items():
        result["pages"][name] = probe(name, url, args.max_pages, args.delay)
        for a in result["pages"][name]["attempts"]:
            print(f"[html:{name}] {a['status'] or a['error_kind']} ua={a['user_agent']} {a['bytes_read']}B {a['url']}")
    result["repeats"] = []
    for i in range(args.repeat):
        for name, url in PAGES.items():
            time.sleep(args.delay)
            r = _http.get(url, accept="text/html")
            result["repeats"].append({"page": name, "status": r["status"], "error_kind": r["error_kind"],
                                      "bytes": r["bytes_read"], "at": r["requested_at"]})
            print(f"[html:repeat{i}:{name}] {r['status'] or r['error_kind']} {r['bytes_read']}B")
    (OUT / "html_probe.json").write_text(json.dumps(result, indent=2))
    print(f"wrote {OUT / 'html_probe.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
