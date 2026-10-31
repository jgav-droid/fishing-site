#!/usr/bin/env python3
"""Post-build SEO + internal-link validation of a built site (deploy gate in CI).

  python3 mvp/tests/check_dist.py mvp/dist [--production]

Exits non-zero (and the workflow stops before upload) if any page is missing a canonical,
title, description or single <h1>; JSON-LD does not parse; an internal link or in-page anchor
is broken; or, for --production, any page is noindex, robots.txt does not allow crawling,
the sitemap does not match the indexable pages, or titles/descriptions are not unique.
A non-production build must be noindex everywhere and disallow crawling.
Validation only: reads the built files, changes nothing.
"""
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

MVP = Path(__file__).resolve().parents[1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    production = "--production" in sys.argv
    root = Path(args[0] if args else MVP / "dist")
    base = json.loads((MVP / "config.json").read_text())["base_url"].rstrip("/")
    problems, titles, descs, indexable = [], {}, {}, set()
    links = anchors = 0
    pages = sorted(root.rglob("*.html"))
    if not pages:
        sys.exit(f"check_dist: no HTML pages under {root}")
    for p in pages:
        s = p.read_text(encoding="utf-8")
        rel = "/" + p.relative_to(root).as_posix()
        rel = rel[: -len("index.html")] if rel.endswith("/index.html") or rel == "/index.html" else rel
        noindex = 'name="robots" content="noindex"' in s
        if rel != "/404.html":
            if production and noindex:
                problems.append(f"{rel}: noindex in a production build")
            if not production and not noindex:
                problems.append(f"{rel}: non-production build is indexable")
            can = re.search(r'<link rel="canonical" href="([^"]+)"', s)
            if not can or can.group(1) != base + rel:
                problems.append(f"{rel}: canonical {can.group(1) if can else None!r} != {base + rel!r}")
            t = re.search(r"<title>(.+?)</title>", s, re.S)
            d = re.search(r'<meta name="description" content="([^"]+)"', s)
            if not t or not d:
                problems.append(f"{rel}: missing title or description")
            else:
                titles.setdefault(t.group(1), []).append(rel)
                descs.setdefault(d.group(1), []).append(rel)
            if len(re.findall(r"<h1[\s>]", s)) != 1:
                problems.append(f"{rel}: expected exactly one <h1>")
            if not noindex:
                indexable.add(base + rel)
        for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S):
            try:
                json.loads(j)
            except ValueError as e:
                problems.append(f"{rel}: invalid JSON-LD ({e})")
        ids = set(re.findall(r'\bid="([^"]+)"', s))
        for h in re.findall(r'href="([^"]+)"', s):
            h = html.unescape(h)
            if h.startswith("#"):
                anchors += 1
                if len(h) > 1 and h[1:] not in ids:
                    problems.append(f"{rel}: broken in-page anchor {h}")
            elif h.startswith("/") and not h.startswith("//"):
                links += 1
                target = root / urlparse(h).path.lstrip("/")
                if not (target.is_file() or (target / "index.html").is_file()):
                    problems.append(f"{rel}: broken internal link {h}")
    robots = (root / "robots.txt").read_text() if (root / "robots.txt").exists() else ""
    sitemap = set(re.findall(r"<loc>(.*?)</loc>", (root / "sitemap.xml").read_text())) if (root / "sitemap.xml").exists() else set()
    if production:
        if "Allow: /" not in robots or f"Sitemap: {base}/sitemap.xml" not in robots:
            problems.append("robots.txt does not allow crawling / list the sitemap")
        if sitemap != indexable:
            problems.append(f"sitemap mismatch: missing {sorted(indexable - sitemap)[:5]}, extra {sorted(sitemap - indexable)[:5]}")
        problems += [f"duplicate title on {v}" for v in titles.values() if len(v) > 1]
        problems += [f"duplicate description on {v}" for v in descs.values() if len(v) > 1]
    elif "Disallow: /" not in robots:
        problems.append("non-production robots.txt must disallow crawling")
    mode = "production" if production else "non-production"
    print(f"check_dist ({mode}): {len(pages)} HTML files, {len(indexable)} indexable, sitemap {len(sitemap)}, "
          f"internal links {links}, in-page anchors {anchors}, problems {len(problems)}")
    for x in problems[:50]:
        print("  FAIL", x)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
