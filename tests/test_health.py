#!/usr/bin/env python3
"""Health check API: GET /health -> {"title": "カタン", "version": "...", "status": "idle|waiting|playing"}.

Contract (common to server.py / wsgi.py / Docker):
  * GET /health, no auth, lightweight, tiny JSON body (title / version / status only).
  * status:
      "idle"      -> started, no one seated (or unexpected state -> idle)
      "waiting"   -> started, lobby has >= 1 seated player, game not started
      "playing"   -> a game is in progress
  * No "stopped" value: the liveness of the process is judged by the caller when
    the server stops answering at all.

Run: python3 tests/test_health.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_core

fails = 0
def check(cond, msg):
    global fails
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        fails += 1

def get_health():
    """Call the shared router directly (no HTTP server needed)."""
    status, ctype, body = app_core.route_get("/health", {}, "127.0.0.1")
    return status, json.loads(body)

def reset_room():
    app_core.reset_room()
    app_core.ROOM["phase"] = "lobby"
    app_core.ROOM["seats"] = []
    app_core.ROOM["g"] = None

def test_status_lifecycle():
    # --- idle: fresh room, nobody seated ---
    reset_room()
    s, j = get_health()
    check(s == 200, "GET /health -> 200")
    check(set(j.keys()) == {"title", "version", "status"},
          "response keys are exactly title/version/status (%s)" % sorted(j.keys()))
    check(j.get("title") == "カタン", "title is 'カタン'")
    check(isinstance(j.get("version"), str) and j["version"] != "", "version is a non-empty string")
    check(j.get("status") == "idle", "fresh room -> status idle")

    # --- waiting: somebody in the lobby, game not started yet ---
    reset_room()
    app_core.ROOM["seats"].append({"token": "tok-a", "name": "プレイヤー1", "roll": None})
    s, j = get_health()
    check(j.get("status") == "waiting", "1 seated player in lobby -> status waiting")

    # a full table is still 'waiting' until the game starts
    reset_room()
    for i in range(4):
        app_core.ROOM["seats"].append({"token": f"tok-{i}", "name": f"プレイヤー{i+1}", "roll": None})
    s, j = get_health()
    check(j.get("status") == "waiting", "4 seated players (full) -> still waiting")

    # --- playing: a game is in progress ---
    reset_room()
    app_core.ROOM["phase"] = "playing"
    app_core.ROOM["g"] = None      # not auto-reset while phase=='playing' w/o winner
    s, j = get_health()
    check(j.get("status") == "playing", "phase playing -> status playing")

    # --- back to idle after the game is over (reset -> lobby, nobody seated) ---
    reset_room()
    s, j = get_health()
    check(j.get("status") == "idle", "after reset -> status idle again")

def test_version_fallback():
    """VERSION file missing -> version is 'dev' (cached once per process)."""
    orig_root = app_core.APP_ROOT
    orig_cache = app_core.HEALTH_VERSION_CACHE
    app_core.APP_ROOT = "/nonexistent-path-for-version-test"   # forces FileNotFoundError
    app_core.HEALTH_VERSION_CACHE = None
    try:
        v = app_core._health_version()
        check(v == "dev", "VERSION file missing -> version is 'dev'")
    finally:
        app_core.APP_ROOT = orig_root
        app_core.HEALTH_VERSION_CACHE = orig_cache
    # the real project root must resolve to the file's stripped content (or 'dev')
    app_core.HEALTH_VERSION_CACHE = None
    v = app_core._health_version()
    check(isinstance(v, str) and v != "", "VERSION at project root resolves to a version string (got %r)" % v)
    app_core.HEALTH_VERSION_CACHE = orig_cache

def test_status_values():
    reset_room()
    allowed = {"idle", "waiting", "playing"}
    for phase, seats, want in (("lobby", [], "idle"),
                               ("lobby", [{"token": "t", "name": "x", "roll": None}], "waiting"),
                               ("playing", [], "playing")):
        app_core.reset_room()
        app_core.ROOM["phase"] = phase
        app_core.ROOM["seats"] = seats
        app_core.ROOM["g"] = None
        s, j = get_health()
        check(j.get("status") in allowed, "status %r is one of idle/waiting/playing" % j.get("status"))
        check(j.get("status") == want, "status mapping %s -> %s" % (phase, want))

if __name__ == "__main__":
    test_status_lifecycle()
    test_version_fallback()
    test_status_values()
    print()
    print("HEALTH TEST OK" if fails == 0 else "HEALTH TEST FAILED (%d)" % fails)
    sys.exit(0 if fails == 0 else 1)
