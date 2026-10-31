"""Minimal stdlib HTTP helper that records everything needed for the validation log.

No retries-on-block, no proxy rotation, no anti-bot evasion. Each call is one
ordinary GET. Honors HTTPS_PROXY / SSL_CERT_FILE from the environment.
"""
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HONEST_UA = "wdfw-stocking-validation/0.1 (open-data feasibility test; python-urllib)"
# Used only as a one-off comparison for HTML pages, as permitted by the brief.
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

INTERESTING_HEADER = re.compile(
    r"ratelimit|retry-after|x-socrata|x-soda2|last-modified|etag|cache-control|"
    r"content-length|content-type|content-disposition|age|server|cf-|x-cache|akamai",
    re.I,
)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _RecordingRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        self.hops = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops.append({"status": code, "location": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _classify_urlerror(err):
    text = str(getattr(err, "reason", err))
    if "Tunnel connection failed" in text:
        # The CONNECT was refused by the local egress proxy: the request
        # never reached the destination server.
        return "egress_proxy_denied", text
    if "timed out" in text.lower():
        return "timeout", text
    return "network_error", text


def get(url, *, ua=HONEST_UA, accept=None, max_bytes=None, timeout=90, sink=None):
    """GET url. Returns a result dict; body bytes are in result['body'].

    max_bytes: stop reading after this many bytes (marks truncated=True).
    sink: optional open binary file; body is streamed there instead of kept.
    """
    redirects = _RecordingRedirects()
    opener = urllib.request.build_opener(redirects)
    headers = {"User-Agent": ua, "Accept-Encoding": "identity"}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    res = {
        "url": url,
        "requested_at": now_iso(),
        "user_agent": "browser" if ua == BROWSER_UA else "honest",
        "status": None,
        "error_kind": None,
        "error": None,
        "final_url": None,
        "redirects": redirects.hops,
        "headers": {},
        "content_type": None,
        "content_length_header": None,
        "bytes_read": 0,
        "truncated": False,
        "elapsed_s": None,
        "body": b"",
    }
    t0 = time.monotonic()
    resp = None
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
        res["error_kind"] = "http_error"
        res["error"] = f"HTTP {e.code} {e.reason}"
    except urllib.error.URLError as e:
        res["error_kind"], res["error"] = _classify_urlerror(e)
    except TimeoutError as e:
        res["error_kind"], res["error"] = "timeout", str(e)

    if resp is not None:
        res["status"] = resp.status if hasattr(resp, "status") else resp.code
        res["final_url"] = resp.geturl()
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        res["headers"] = {k: v for k, v in hdrs.items() if INTERESTING_HEADER.search(k)}
        res["content_type"] = hdrs.get("content-type")
        res["content_length_header"] = hdrs.get("content-length")
        chunks = []
        try:
            while True:
                want = 1 << 16
                if max_bytes is not None:
                    want = min(want, max_bytes - res["bytes_read"])
                    if want <= 0:
                        res["truncated"] = bool(resp.read(1))
                        break
                chunk = resp.read(want)
                if not chunk:
                    break
                res["bytes_read"] += len(chunk)
                if sink is not None:
                    sink.write(chunk)
                else:
                    chunks.append(chunk)
        except Exception as e:  # mid-stream reset etc.
            res["error_kind"] = res["error_kind"] or "read_error"
            res["error"] = (res["error"] or "") + f" read: {e}"
        res["body"] = b"".join(chunks)
        resp.close()
    res["elapsed_s"] = round(time.monotonic() - t0, 3)
    return res


def loggable(res, body_preview=300):
    """Result dict without the raw body (keeps a short text preview)."""
    out = {k: v for k, v in res.items() if k != "body"}
    if res["body"]:
        out["body_preview"] = res["body"][:body_preview].decode("utf-8", "replace")
    return out


def get_json(url, **kw):
    res = get(url, accept="application/json", **kw)
    data = None
    if res["status"] == 200 and res["body"]:
        try:
            data = json.loads(res["body"])
        except ValueError as e:
            res["error_kind"], res["error"] = "json_parse_error", str(e)
    return res, data
