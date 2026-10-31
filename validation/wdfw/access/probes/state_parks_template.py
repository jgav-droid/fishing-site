#!/usr/bin/env python3
"""Does one parser handle Washington State Parks park pages? (template-reuse test)

Parses the labelled 'Alerts', 'Hours' and 'Fees' blocks from park pages and prints them.
"""
import html
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _http  # noqa: E402

PARKS = ["battle-ground-lake-state-park", "lake-sylvia-state-park", "lake-sammamish-state-park", "rasar-state-park"]


def blocks(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())
    out = {}
    m = re.search(r"\bAlerts (.*?)(?: See all photos| Get Directions)", t)
    out["alerts"] = m.group(1)[:200] if m else None
    m = re.search(r"\bHours (.*?) Fees ", t)
    out["hours"] = m.group(1)[:160] if m else None
    m = re.search(r"\bFees (.*?) (?:See more about fees|Contact)", t)
    out["fees"] = m.group(1)[:200] if m else None
    return out


def main():
    ok = 0
    for p in PARKS:
        r = _http.get(f"https://parks.wa.gov/find-parks/state-parks/{p}", accept="text/html")
        b = blocks(r["body"].decode("utf-8", "replace")) if r["status"] == 200 else {}
        good = bool(b.get("hours") and b.get("fees"))
        ok += good
        print(f"{r['status']} {p}: {'PARSED' if good else 'FAILED'} {b}")
        time.sleep(1.5)
    print(f"template parse success {ok}/{len(PARKS)}")


if __name__ == "__main__":
    main()
