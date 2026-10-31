#!/usr/bin/env python3
"""Change-detection feasibility: is a normalized content hash stable between fetches?

For every source page in access_dataset.json provenance (plus the emergency-rule lake
filters), compare the cached copy with a fresh fetch, using
  raw   = sha256 of the whole HTML
  main  = sha256 of the <main> text with digits-run timestamps, nonces and tokens removed
A page whose 'main' hash differs without a material edit would be monitoring noise.
Output: access/change_detection_test.json
"""
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _http  # noqa: E402

CACHE = ROOT / "out/access/pages"


def cname(url):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", url.split("://", 1)[1])[:180] + ".html"


def main_text(s):
    m = re.search(r"<main.*?</main>", s, re.S | re.I)
    b = m.group(0) if m else s
    b = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", b, flags=re.S)
    b = re.sub(r'\s(?:data-[a-z-]+|nonce|id|class)="[^"]*"', "", b)          # volatile attributes
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", b)).split())
    t = re.sub(r"js-view-dom-id-\w+|form-[A-Za-z0-9_-]{20,}", "", t)
    return t


def h(x):
    return hashlib.sha256(x.encode()).hexdigest()[:16]


def main():
    ds = json.loads((ROOT / "access/access_dataset.json").read_text())
    urls = set()
    for r in ds:
        for f in ("bank_fishing_status", "fishing_pier_or_dock"):
            urls |= {p["source_url"] for p in r[f]["provenance"] if p["source_url"].startswith("http") and "MapServer" not in p["source_url"]}
        for a in r["access_points"]:
            for v in a.values():
                if isinstance(v, dict) and "provenance" in v:
                    urls |= {p["source_url"] for p in v["provenance"] if "MapServer" not in p["source_url"]}
    urls = sorted(u for u in urls if (CACHE / cname(u)).exists())
    res = []
    for u in urls:
        old = (CACHE / cname(u)).read_text(encoding="utf-8")
        time.sleep(1.0)
        r = _http.get(u, accept="text/html")
        new = r["body"].decode("utf-8", "replace")
        a, b = main_text(old), main_text(new)
        diff = None
        if h(a) != h(b):
            i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            diff = {"old": a[max(0, i - 60):i + 80], "new": b[max(0, i - 60):i + 80]}
        res.append({"url": u, "status": r["status"], "raw_changed": h(old) != h(new), "main_changed": h(a) != h(b), "first_diff": diff})
        print(f"{r['status']} raw_changed={h(old) != h(new)!s:5} main_changed={h(a) != h(b)!s:5} {u}")
    summ = {"pages": len(res), "raw_hash_changed": sum(x["raw_changed"] for x in res),
            "main_text_hash_changed": sum(x["main_changed"] for x in res)}
    print(summ)
    (ROOT / "access/change_detection_test.json").write_text(json.dumps({"summary": summ, "pages": res}, indent=1))


if __name__ == "__main__":
    main()
