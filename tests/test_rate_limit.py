#!/usr/bin/env python3
"""Per-IP rate limiting (Copilot review #3).

The limits are deliberately simple:
  * join  : 5 requests / minute / IP
  * action: 120 requests / minute / IP (every POST /action, joins included)

The address is used ONLY for rate limiting. Authorization (who may act) never
depends on it - see tests/test_authz.py.

Time is faked through app_core._rate_now, so nothing here sleeps.
"""
import io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["CATAN_RATE_LIMIT"] = "1"
os.environ.pop("CATAN_HOTSEAT", None)

import app_core
from app_core import route_post

fails = 0
def check(cond, msg):
    global fails
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        fails += 1


clock = [1000.0]
real_rate_now = app_core._rate_now
app_core._rate_now = lambda: clock[0]


def reset():
    """Forget every bucket (each scenario starts from a full one)."""
    app_core._rate_buckets.clear()


def post(action, ip, **extra):
    payload = {"action": action}
    payload.update(extra)
    return route_post(payload, {}, ip)


# ===========================================================================
# join: 5 per minute
# ===========================================================================
reset()
ip = "198.51.100.10"
for i in range(5):
    r = post("join", ip, name="p%d" % i)
    check(not r.get("rate_limited"), "join #%d allowed" % (i + 1))

r = post("join", ip, name="p6")
check(r.get("rate_limited") is True, "6th join from the same IP is refused")
check(r.get("retry_after") == 12, "join retry_after is 12 s (one token at 5/min)")
check("リクエストが多すぎます" in r.get("error", ""), "join limit has a user-facing error")

r = post("join", "198.51.100.11", name="other")
check(not r.get("rate_limited"), "a different IP has its own bucket")

clock[0] += 6
r = post("join", ip, name="p7")
check(r.get("rate_limited") is True and r.get("retry_after") == 6,
      "after 6 s the bucket still holds less than one token (retry 6 s)")

clock[0] += 6
r = post("join", ip, name="p8")
check(not r.get("rate_limited"), "after 12 s one join is allowed again")


# ===========================================================================
# action: 120 per minute (any action name is counted before it is handled)
# ===========================================================================
reset()
ip = "198.51.100.20"
limited_at = None
for i in range(120):
    r = post("unknown-probe", ip)
    if r.get("rate_limited"):
        limited_at = i + 1
        break
check(limited_at is None, "120 requests to /action are allowed")
r = post("unknown-probe", ip)
check(r.get("rate_limited") is True, "the 121st request is refused")
check(r.get("retry_after") == 1, "action retry_after is 1 s (120/min = 2/s)")

clock[0] += 1
r = post("unknown-probe", ip)
check(not r.get("rate_limited"), "after 1 s the action bucket refills")

# joins also draw from the action bucket
reset()
ip = "198.51.100.30"
for i in range(5):
    post("join", ip, name="q%d" % i)
for i in range(115):
    post("unknown-probe", ip)
r = post("unknown-probe", ip)
check(r.get("rate_limited") is True,
      "5 joins + 115 actions fill the 120/min action bucket")


# ===========================================================================
# switching the limiter off, and internal callers without an address
# ===========================================================================
reset()
os.environ["CATAN_RATE_LIMIT"] = "0"
ok = True
for i in range(12):
    if post("join", "198.51.100.40", name="r%d" % i).get("rate_limited"):
        ok = False
        break
check(ok, "CATAN_RATE_LIMIT=0 disables the limiter")
os.environ["CATAN_RATE_LIMIT"] = "1"

reset()
ok = True
for _ in range(10):
    if route_post({"action": "unknown-probe"}, {}).get("rate_limited"):
        ok = False
        break
check(ok, "no client address -> the limiter is skipped (internal API only)")


# ===========================================================================
# WSGI adapter: the LAST X-Forwarded-For hop is the rate-limit key
# ===========================================================================
from wsgiref.util import setup_testing_defaults
import wsgi as appmod


def wsgi_post(action, remote="10.0.0.1", xff=None, **extra):
    environ = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = "POST"
    environ["PATH_INFO"] = "/action"
    environ["QUERY_STRING"] = ""
    environ["REMOTE_ADDR"] = remote
    if xff is not None:
        environ["HTTP_X_FORWARDED_FOR"] = xff
    body = {"action": action}
    body.update(extra)
    data = json.dumps(body).encode()
    environ["CONTENT_LENGTH"] = str(len(data))
    environ["wsgi.input"] = io.BytesIO(data)
    out = {}
    def start_response(status, headers):
        out["status"] = status
        out["headers"] = dict(headers)
    chunks = appmod.application(environ, start_response)
    return out["status"], out.get("headers", {}), json.loads(b"".join(chunks))


reset()
# Different client-supplied prefixes, same last hop: they share one bucket.
for i in range(5):
    st, hdrs, r = wsgi_post("join", xff="10.9.9.%d, 203.0.113.7" % i,
                            name="w%d" % i)
    check(st.startswith("200") and not r.get("rate_limited"),
          "wsgi join #%d allowed for the last XFF hop" % (i + 1))

st, hdrs, r = wsgi_post("join", xff="10.9.9.99, 203.0.113.7", name="w6")
check(st.startswith("429"), "wsgi returns 429 once the last hop is over the limit")
check(r.get("rate_limited") is True and r.get("retry_after") == 12,
      "wsgi body carries rate_limited + retry_after")
check(hdrs.get("Retry-After") == "12", "wsgi sends a Retry-After header")

st, hdrs, r = wsgi_post("join", xff="10.9.9.1, 203.0.113.8", name="w7")
check(st.startswith("200") and not r.get("rate_limited"),
      "a different last hop has its own wsgi bucket")

st, hdrs, r = wsgi_post("join", remote="203.0.113.9", name="w8")
check(st.startswith("200") and not r.get("rate_limited"),
      "wsgi falls back to REMOTE_ADDR when there is no X-Forwarded-For")


# ---------------------------------------------------------------------------
app_core._rate_now = real_rate_now
os.environ["CATAN_RATE_LIMIT"] = "1"

print()
print("RATE LIMIT TEST OK" if fails == 0 else "RATE LIMIT TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
