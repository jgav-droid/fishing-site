#!/usr/bin/env python3
"""Daily observation of dataset 6fex-3r7d (about one week; validation only).

Each run records a compact snapshot and diffs it against the previous one
to observe refresh frequency, corrections to prior records, reporting lag
and content-hash behaviour. Not production infrastructure.

  python3 monitor/daily_snapshot.py

Writes monitor/snapshots/<UTC date>.json (small) and appends one line to
monitor/MONITOR_LOG.md. The full export is downloaded gzipped (~4.6 MB) to
memory only.

Row hash = SHA-256 of the bulk-CSV row values. It differs from the
API-based hash in normalize.py; it is only compared day to day.
"""
import csv
import gzip
import hashlib
import io
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import _http  # noqa: E402

DOMAIN = "https://data.wa.gov"
DS = "6fex-3r7d"
SNAP = HERE / "snapshots"
LOG = HERE / "MONITOR_LOG.md"
WINDOW_DAYS = 120


def soda(**params):
    url = f"{DOMAIN}/resource/{DS}.json?" + urllib.parse.urlencode({f"${k}": v for k, v in params.items()})
    res, data = _http.get_json(url)
    if data is None:
        raise SystemExit(f"query failed {res['status']} {res['error']}: {url}")
    return data, res


def full_csv():
    req = urllib.request.Request(f"{DOMAIN}/api/views/{DS}/rows.csv?accessType=DOWNLOAD",
                                 headers={"User-Agent": _http.HONEST_UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=600) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8"), {k.lower(): v for k, v in r.headers.items()}


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    meta_res, meta = _http.get_json(f"{DOMAIN}/api/views/{DS}.json")
    if meta is None:
        raise SystemExit(f"metadata failed {meta_res['status']} {meta_res['error']}")
    sysf, sres = soda(select="count(*) as n, count(distinct :id) as ids, min(:created_at) as c0, "
                             "max(:created_at) as c1, max(release_start_date) as maxd")
    ids, _ = soda(select=":id", order=":id", limit=200000)
    text, hdrs = full_csv()
    rows = list(csv.reader(io.StringIO(text)))
    header, body = rows[0], rows[1:]
    i_start = header.index("Release Start Date")
    i_year = header.index("Release Year")

    cutoff = (now.date() - timedelta(days=WINDOW_DAYS))
    per_year, window, by_date = defaultdict(list), [], Counter()
    for r in body:
        h = hashlib.sha256("\x1f".join(r).encode()).hexdigest()[:24]
        per_year[r[i_year]].append(h)
        d = datetime.strptime(r[i_start].split()[0], "%m/%d/%Y").date()
        if d >= cutoff:
            window.append(h)
            by_date[d.isoformat()] += 1
    snap = {
        "taken_at": now.isoformat(),
        "rowsUpdatedAt": datetime.fromtimestamp(meta["rowsUpdatedAt"], timezone.utc).isoformat(),
        "last_modified_header": sres["headers"].get("last-modified"),
        "row_count": int(sysf[0]["n"]), "csv_rows": len(body),
        "distinct_ids": int(sysf[0]["ids"]),
        "created_at_range": [sysf[0]["c0"], sysf[0]["c1"]],
        "id_set_sha": hashlib.sha256("\n".join(sorted(x[":id"] for x in ids)).encode()).hexdigest()[:24],
        "max_release_start_date": sysf[0]["maxd"][:10],
        "lag_days_now_minus_max_release": (now.date() - date.fromisoformat(sysf[0]["maxd"][:10])).days,
        "duplicate_rows": sum(n - 1 for n in Counter(tuple(r) for r in body).values() if n > 1),
        "per_year": {y: {"rows": len(v), "digest": hashlib.sha256("".join(sorted(v)).encode()).hexdigest()[:24]}
                     for y, v in sorted(per_year.items())},
        "window_days": WINDOW_DAYS,
        "window_rows_by_release_date": dict(sorted(by_date.items())),
        "window_hashes": sorted(window),
    }

    SNAP.mkdir(exist_ok=True)
    prev_files = sorted(p for p in SNAP.glob("*.json") if p.stem < now.date().isoformat())
    diff = {}
    if prev_files:
        prev = json.loads(prev_files[-1].read_text())
        pw, cw = Counter(prev["window_hashes"]), Counter(snap["window_hashes"])
        new_dates = {d: n - prev["window_rows_by_release_date"].get(d, 0)
                     for d, n in snap["window_rows_by_release_date"].items()
                     if n != prev["window_rows_by_release_date"].get(d, 0)}
        diff = {
            "vs": prev_files[-1].stem,
            "refreshed": snap["rowsUpdatedAt"] != prev["rowsUpdatedAt"],
            "row_count_delta": snap["row_count"] - prev["row_count"],
            "ids_regenerated": snap["id_set_sha"] != prev["id_set_sha"],
            "window_hashes_added": sum((cw - pw).values()),
            "window_hashes_removed": sum((pw - cw).values()),
            "per_release_date_count_changes": new_dates,
            "late_reported_dates": sorted(d for d, n in new_dates.items()
                                          if n > 0 and d <= prev["max_release_start_date"]),
            "historical_years_changed": sorted(y for y, v in snap["per_year"].items()
                                               if y in prev["per_year"] and v["digest"] != prev["per_year"][y]["digest"]
                                               and int(y) < now.year),
        }
    snap["diff_vs_previous"] = diff
    out = SNAP / f"{now.date().isoformat()}.json"
    out.write_text(json.dumps(snap, indent=1))

    if not LOG.exists():
        LOG.write_text("# 6fex-3r7d daily monitor\n\n| taken_at (UTC) | rowsUpdatedAt | rows | max release | lag d | "
                       "refreshed | ids regenerated | window +/- | late-reported dates | historical years changed |\n"
                       "|---|---|---|---|---|---|---|---|---|---|\n")
    with LOG.open("a") as fh:
        fh.write(f"| {snap['taken_at']} | {snap['rowsUpdatedAt']} | {snap['row_count']} | "
                 f"{snap['max_release_start_date']} | {snap['lag_days_now_minus_max_release']} | "
                 f"{diff.get('refreshed', 'baseline')} | {diff.get('ids_regenerated', '-')} | "
                 f"{diff.get('window_hashes_added', '-')}/{diff.get('window_hashes_removed', '-')} | "
                 f"{', '.join(diff.get('late_reported_dates', [])) or '-'} | "
                 f"{', '.join(diff.get('historical_years_changed', [])) or '-'} |\n")
    print(json.dumps({k: v for k, v in snap.items() if k not in ("window_hashes", "per_year")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
