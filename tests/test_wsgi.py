#!/usr/bin/env python3
"""End-to-end test of the WSGI app (wsgi.py) via wsgiref's test client.

This exercises the SAME routes the PythonAnywhere deployment uses, without
needing a running HTTP server. State is in-process, so we drive one room here.
"""
import io, json, os, sys

sys.path.insert(0, "/home/atsushi/Arduino/test/catan")
from wsgiref.util import setup_testing_defaults
import wsgi as appmod

fails = 0
def check(cond, msg):
    global fails
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        fails += 1

def call(method, path, body=None, query="", ip="127.0.0.1", headers=None):
    """Call the WSGI application directly."""
    environ = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = method
    environ["PATH_INFO"] = path
    environ["QUERY_STRING"] = query
    environ["REMOTE_ADDR"] = ip
    for k, v in (headers or {}).items():
        environ[k] = v
    data = b""
    if body is not None:
        data = json.dumps(body).encode()
    environ["CONTENT_LENGTH"] = str(len(data))
    environ["wsgi.input"] = io.BytesIO(data)
    captured = {}
    def start_response(status, hdrs):
        captured["status"] = status
        captured["headers"] = dict(hdrs)
    out = b"".join(appmod.application(environ, start_response))
    return captured["status"], captured["headers"], out

def get_json(path, **kw):
    s, h, b = call("GET", path, **kw)
    return s, json.loads(b)

def post_json(payload, ip="127.0.0.1"):
    s, h, b = call("POST", "/action", body=payload, ip=ip)
    return json.loads(b)

# --- static files -----------------------------------------------------------
s, h, b = call("GET", "/")
check(s == "200 OK" and b"<html" in b.lower(), "GET / serves client.html")
check("text/html" in h["Content-Type"], "GET / content-type is html")
s, h, b = call("GET", "/monitor")
check(s == "200 OK" and b"<html" in b.lower(), "GET /monitor serves index.html")
s, h, b = call("GET", "/game.js")
check(s == "200 OK" and "javascript" in h["Content-Type"], "GET /game.js serves JS")
s, h, b = call("GET", "/style.css")
check(s == "200 OK" and "text/css" in h["Content-Type"], "GET /style.css serves CSS")
s, h, b = call("GET", "/nope")
check(s == "404 Not Found", "unknown path -> 404")
# path traversal must not escape web/
s, h, b = call("GET", "/../server.py")
check(s == "404 Not Found", "path traversal blocked")

# --- /env debug gate --------------------------------------------------------
s, j = get_json("/env", ip="127.0.0.1")
check(j["debug_allowed"] is True, "/env from loopback allows debug")
s, j = get_json("/env", ip="203.0.113.9")
check(j["debug_allowed"] is False, "/env from a public address denies debug")
# X-Forwarded-For (PythonAnywhere proxy) is honoured
s, j = get_json("/env", ip="127.0.0.1", headers={"HTTP_X_FORWARDED_FOR": "203.0.113.9, 10.0.0.1"})
check(j["debug_allowed"] is False, "/env uses X-Forwarded-For (remote) ")
s, j = get_json("/env", ip="127.0.0.1", headers={"HTTP_X_FORWARDED_FOR": "127.0.0.1"})
check(j["debug_allowed"] is True, "/env uses X-Forwarded-For (local)")

# --- room reset + lobby -----------------------------------------------------
r = post_json({"action": "room_reset"})
check(r.get("ok") is True, "room_reset ok")

s, j = get_json("/room")
check(j.get("phase") == "lobby", "/room reports lobby after reset")

# join two players
a = post_json({"action": "join", "name": "アリス"})
check(a.get("ok") is True and a.get("token"), "join returns a token")

# join the same name twice should not create duplicates silently? just join 2nd
b2 = post_json({"action": "join", "name": "ボブ"})
check(b2.get("ok") is True and b2.get("token") and b2["token"] != a["token"],
      "second join gets a distinct token")

tok_a, tok_b = a["token"], b2["token"]
s, j = get_json("/room")
check(len(j.get("seats", [])) == 2, "/room shows 2 seats")

# --- monitor-only actions denied from remote, allowed locally ---------------
r = post_json({"action": "monitor_new"}, ip="203.0.113.9")
check(r.get("ok") is False and "外部" in r.get("error", ""),
      "monitor_new denied from remote address")
r = post_json({"action": "auto_setup"}, ip="203.0.113.9")
check(r.get("ok") is False, "auto_setup denied from remote address")
r = post_json({"action": "give_resources"}, ip="203.0.113.9")
check(r.get("ok") is False, "give_resources denied from remote address")

# --- drafts (roll + pick) ---------------------------------------------------
r = post_json({"action": "room_roll", "token": tok_a})
check(r.get("ok") is True, "room_roll accepted")
r = post_json({"action": "room_roll", "token": tok_b})
check(r.get("ok") is True, "second room_roll accepted")

s, j = get_json("/room")
rolls = [seat.get("roll") for seat in j["seats"]]
check(all(r is not None for r in rolls), "both seats have dice")

# pick positions in dice order: the highest roll picks first.
s, j = get_json("/room")
totals = {seat["name"]: sum(seat["roll"]) for seat in j["seats"]}
names = list(totals)
name_tok = {"アリス": tok_a, "ボブ": tok_b}
order_names = sorted(names, key=lambda n: -totals[n])
first, second = name_tok[order_names[0]], name_tok[order_names[1]]
r = post_json({"action": "room_pick", "token": second, "slot": 1})
check(r.get("ok") is False, "out-of-order pick is refused")
r = post_json({"action": "room_pick", "token": first, "slot": 1})
check(r.get("ok") is True, "first picker claims slot 1")
r = post_json({"action": "room_pick", "token": second, "slot": 2})
check(r.get("ok") is True, "second picker claims slot 2")
r = post_json({"action": "room_pick", "token": second, "slot": 1})
check(r.get("ok") is False, "a taken slot cannot be picked")

r = post_json({"action": "room_start"})
check(r.get("ok") is True, "room_start accepted")

s, j = get_json("/state")
check(j.get("phase") != "lobby" or j.get("started"), "/state reports a started game")

# --- play a little: a full turn through the API ----------------------------
def as_player(tok):
    s, j = get_json("/state", query="token=" + tok)
    return j

# whoever goes first in PLAY order is the one with slot 1 (tok = first)
st = as_player(first)
check("you" in st and st["you"] is not None, "/state with token gives a viewer id")
check(st.get("board") and st["board"].get("hexes"), "board data present in started game")

# the viewer's own resources are present, other players' are hidden
me = next(p for p in st["players"] if p["id"] == st["you"])
others = [p for p in st["players"] if p["id"] != st["you"]]
check("resources" in me, "own resources visible")
check(all("resources" not in p for p in others), "other players' resources hidden")

# both tokens resolve to distinct viewer ids
sa = as_player(first); sb = as_player(second)
check(sa["you"] != sb["you"], "each token maps to a distinct player")

# --- 405 --------------------------------------------------------------------
s, h, b = call("DELETE", "/")
check(s.startswith("405"), "unsupported method -> 405")

# leave the room clean for later tests
post_json({"action": "room_reset"})

print()
print("WSGI TEST OK" if fails == 0 else "WSGI TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
