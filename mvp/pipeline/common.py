"""Shared paths, I/O and reused validation helpers for the MVP pipeline.

The MVP deliberately reuses the Step 1-3 validation code instead of re-implementing it:
  validation/wdfw/_http.py                         ordinary logged GETs (Step 1)
  validation/wdfw/access/probes/change_detection.py main_text() normaliser (Step 3)
  validation/wdfw/access/access_dataset.json       verified access facts + provenance (Step 3)
  validation/wdfw/access/identity_review_decisions.json  reviewed aliases (Step 2/3)
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MVP = Path(__file__).resolve().parents[1]
REPO = MVP.parent
VALIDATION = REPO / "validation" / "wdfw"
DATA = MVP / "data"

for p in (VALIDATION, VALIDATION / "access" / "probes"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import _http  # noqa: E402  (Step 1 helper)
from change_detection import main_text  # noqa: E402,F401  (Step 3 normaliser)

DATASET = "6fex-3r7d"
SODA = f"https://data.wa.gov/resource/{DATASET}.json"
METADATA = f"https://data.wa.gov/api/views/{DATASET}.json"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load(name, data_dir=None):
    p = Path(data_dir or DATA) / name
    return json.loads(p.read_text()) if p.exists() else None


def save(name, obj, data_dir=None):
    p = Path(data_dir or DATA) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=False) + "\n")


def content_hash_ids(rows):
    """Step 1 record identity: Socrata :id is regenerated on every nightly full replace, so
    the ID is a hash of the official columns, plus an occurrence suffix because exact
    duplicate rows exist (1,146 in the full export). Same scheme as
    validation/wdfw/normalize.py (tested for equality in tests/test_pipeline.py)."""
    seen, ids = {}, []
    for row in rows:
        content = json.dumps({k: v for k, v in sorted(row.items()) if not k.startswith(":")})
        h = hashlib.sha256(content.encode()).hexdigest()[:20]
        seen[h] = seen.get(h, 0) + 1
        ids.append(f"{h}-{seen[h]}")
    return ids


def update_source_status(data_dir, key, ok, error=None, extra=None):
    """Record each refresh attempt. last_success only moves on success, so a failed
    refresh can never make old data look fresh."""
    st = load("source_status.json", data_dir) or {}
    s = st.get(key, {})
    s["last_attempt"] = now_iso()
    s["status"] = "ok" if ok else "failed"
    s["error"] = None if ok else str(error)[:300]
    if ok:
        s["last_success"] = s["last_attempt"]
    if extra:
        s.update(extra)
    st[key] = s
    save("source_status.json", st, data_dir)
    return s
