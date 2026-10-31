#!/usr/bin/env python3
"""One refresh cycle: stocking -> notices -> tests -> site build.

  python3 mvp/run.py [--production] [--skip-refresh]

Each refresh step records its own success/failure in mvp/data/source_status.json and
keeps last-known data on failure, so the build always runs and shows STALE labels
instead of silently presenting old data as current. Tests must pass before the build.
"""
import argparse
import subprocess
import sys
from pathlib import Path

MVP = Path(__file__).resolve().parent


def sh(*args):
    print("$", " ".join(args), flush=True)
    return subprocess.call([sys.executable, *args])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--production", action="store_true")
    ap.add_argument("--skip-refresh", action="store_true")
    a = ap.parse_args()
    if not a.skip_refresh:
        sh(str(MVP / "pipeline/refresh_stocking.py"))      # failure is recorded, not fatal
        sh(str(MVP / "pipeline/refresh_notices.py"))
    if sh("-m", "unittest", "discover", "-s", str(MVP / "tests")) != 0:
        sys.exit("tests failed; not building")
    sys.exit(sh(str(MVP / "site/build_site.py"), *(["--production"] if a.production else [])))


if __name__ == "__main__":
    main()
