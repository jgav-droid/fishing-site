#!/usr/bin/env python3
"""Template-reuse test: extract the access-relevant labelled fields from ALL cached WDFW
lowland-lake pages (Step 2 crawl, 710 pages): 'Shoreline access' rating + note,
'Two-pole fishing', 'Special fishing restrictions'. Prints success rates and the
rating distribution. Output: out/access/wdfw_lake_access_fields.json
"""
import collections
import glob
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    out, c = {}, collections.Counter()
    for f in glob.glob(str(ROOT / "out/identity/pages/*lowland-lakes_*.html")):
        slug = f.rsplit("lowland-lakes_", 1)[1][:-5]
        if slug.startswith("name"):
            continue
        s = open(f, encoding="utf-8").read()
        m = re.search(r"<main.*?</main>", s, re.S)
        t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", m.group(0) if m else s, flags=re.S))).split())
        sa = re.search(r"Shoreline access: (Good|Fair|Poor|Limited|None|Excellent)\s*(.*?)\s*Two-pole fishing", t)
        tp = re.search(r"Two-pole fishing is (NOT allowed|allowed)", t)
        sr = re.search(r"Special fishing restrictions: (.*?) Shoreline access", t)
        out[slug] = {"shoreline_rating": sa.group(1) if sa else None, "shoreline_note": sa.group(2) if sa else None,
                     "two_pole": tp.group(1) if tp else None, "special_restrictions": sr.group(1) if sr else None}
        c["pages"] += 1
        c["shoreline_parsed"] += bool(sa)
        c["two_pole_parsed"] += bool(tp)
        c["has_special_restrictions"] += bool(sr)
        c["rating:" + (sa.group(1) if sa else "missing")] += 1
    (ROOT / "out/access/wdfw_lake_access_fields.json").write_text(json.dumps(out, indent=1))
    print(dict(c))


if __name__ == "__main__":
    main()
