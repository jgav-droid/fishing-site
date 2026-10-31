#!/usr/bin/env python3
"""Fetch non-WDFW land-manager pages once (cached) and extract access-relevant sentences.

Ordinary GET, honest User-Agent, 1.5 s between requests. Output:
  out/access/manager_pages.json  {url: {status, final_url, last_modified, etag, bytes, hits:{keyword:[sentences]}}}
The hits are only a reading aid; every fact in access_dataset.json is checked by hand
against the page text.
"""
import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _http  # noqa: E402

URLS = [
    "https://parks.wa.gov/find-parks/state-parks/battle-ground-lake-state-park",
    "https://parks.wa.gov/passes-permits/get-park-pass/discover-pass",
    "https://clark.wa.gov/public-works/lacamas-regional-park",
    "https://clark.wa.gov/public-works/salmon-creek-regional-park/klineline-pond",
    "https://clark.wa.gov/public-works/parking-fees",
    "https://www.seattle.gov/parks/parks/green-lake-park",
    "https://www.seatacwa.gov/Community-and-recreation/Parks-and-trails/Angle-Lake-Park",
    "https://www.kentwa.gov/departments/kent-parks/parks-places/parks-trails/lake-meridian-park",
    "https://www.kentwa.gov/departments/kent-parks/about-kent-parks/park-rules",
    "https://snohomishcountywa.gov/Facilities/Facility/Details/Martha-Lake-88",
    "https://cityoflacey.org/city-government/city-departments/parks-and-recreation/parks-and-facilities/municipal-parks/woodland-creek-community-park",
    "https://cityoflakewood.us/american-lake-park/",
    "https://www.mytpu.org/community-environment-parks/parks-recreation/alder-lake-park/",
    "https://www.mytpu.org/community-environment-parks/parks-recreation/reservations-fees/",
    "https://www.puyallupwa.gov/2503/Bradley-Lake-Park",  # old cityofpuyallup.org/545/... 301s to a 404
    "https://www.piercecountywa.gov/1336/Spanaway-Park",
    "https://www.piercecountywa.gov/2430/Fees",
    "https://snohomishcountywa.gov/5281/Passes",
]
KEYS = r"hour|a\.m\.|p\.m\.|\bam\b|\bpm\b|dusk|dawn|fee|\$\d|pass\b|discover|parking|park(?:ing)? lot|pier|dock|fish|closed|closure|construction|open|juvenile|ada|accessib|restroom|launch"


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if 20 < len(s.strip()) < 400]


def main():
    cache = ROOT / "out/access/pages"
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for u in URLS:
        p = cache / (re.sub(r"[^A-Za-z0-9_.-]+", "_", u.split("://", 1)[1])[:180] + ".html")
        meta = {}
        if p.exists():
            body = p.read_text(encoding="utf-8")
            meta = json.loads(p.with_suffix(".meta.json").read_text()) if p.with_suffix(".meta.json").exists() else {}
        else:
            time.sleep(1.5)
            r = _http.get(u, accept="text/html")
            body = r["body"].decode("utf-8", "replace")
            meta = {"status": r["status"], "final_url": r["final_url"], "redirects": r["redirects"],
                    "last_modified": r["headers"].get("last-modified"), "etag": r["headers"].get("etag"),
                    "content_type": r["content_type"], "bytes": r["bytes_read"], "retrieved_at": r["requested_at"],
                    "error": r["error"]}
            p.write_text(body, encoding="utf-8")
            p.with_suffix(".meta.json").write_text(json.dumps(meta))
        m = re.search(r"<main.*?</main>", body, re.S | re.I)
        b = m.group(0) if m else body
        b = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<footer.*?</footer>|<header.*?</header>", " ", b, flags=re.S | re.I)
        text = html.unescape(re.sub(r"<(br|p|li|h\d|div|tr|td)[^>]*>", "\n", b))
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t\xa0]+", " ", text)
        hits = [s for s in sentences(text) if re.search(KEYS, s, re.I)]
        out[u] = {**meta, "main_found": bool(m), "hits": hits[:80]}
        print(f"{meta.get('status')} {meta.get('bytes')}B lm={meta.get('last_modified')} hits={len(hits)} {u}")
    (ROOT / "out/access/manager_pages.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
