#!/usr/bin/env python3
"""Authorization holes (token-less / bad-token access).

Two problems were found by testing against a running server:

  1. GET /state with no token (or a bogus one) returned the FULL monitor view:
     everyone's resources, dev cards and hidden victory points. The cause was
     `viewer = token_to_pid(token)` yielding None, and None meaning "monitor =
     see everything".

  2. POST /action with no token ran game actions for the current player, because
     the per-turn checks were guarded by `actor is not None`.

Fix:
  * /state now resolves THREE views: a real pid, 'spectator' (public only) or
    'debug' (everything - only ever handed out to a LOCAL monitor).
  * handle_action(actor=None, local=False) refuses every game action; a token-
    less request is only allowed when it comes from a trusted/local address.

These checks are done at the app_core level (no HTTP needed) so they describe
the contract directly.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_core
from app_core import (handle_lobby, handle_action, serialize, route_get,
                      route_post, token_to_pid, ROOM,
                      DEBUG_VIEW, SPECTATOR_VIEW)
from game.game import Game

fails = 0
def check(cond, msg):
    global fails
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        fails += 1

SECRET_KEYS = ("resources", "dev_cards", "new_dev_cards", "hidden_vp")


def fresh_started_room():
    """Two joined players, drafted, game started - using the public API only."""
    handle_lobby("room_reset", {})
    a = handle_lobby("join", {"name": "アリス"})
    b = handle_lobby("join", {"name": "ボブ"})
    ta, tb = a["token"], b["token"]
    # all house rules must be fixed before starting
    for key,val in (("desert","center"),("numbers","official"),("victory",10)):
        handle_lobby("room_setting", {"token": ta, "key": key, "value": val})
    handle_lobby("room_roll", {"token": ta})
    handle_lobby("room_roll", {"token": tb})
    seats = ROOM["seats"]
    toks = [ta, tb]
    totals = {i: sum(seats[i]["roll"]) for i in range(len(seats))}
    order = sorted(totals, key=lambda i: -totals[i])
    handle_lobby("room_pick", {"token": toks[order[0]], "slot": 1})
    handle_lobby("room_color", {"token": toks[order[0]], "color": "red"})
    handle_lobby("room_pick", {"token": toks[order[1]], "slot": 2})
    handle_lobby("room_color", {"token": toks[order[1]], "color": "blue"})
    handle_lobby("room_start", {"token": ta})
    # give the players something worth hiding
    g = ROOM["g"]
    for r in g.players[0].resources:
        g.players[0].resources[r] = 3
    g.players[0].dev_cards = ["knight", "monopoly"]
    g.players[0].hidden_vp = 1
    return ta, tb, g


def finish_setup(g):
    """Run the initial placement locally so the game reaches the roll phase."""
    handle_action("auto_setup", {}, None, local=True)


def state_players(token, ip, view=None):
    """Read /state through route_get (so the real viewer resolution runs)."""
    q = {"token": [token]} if token else {}
    if view:
        q["view"] = [view]
    status, ctype, body = route_get("/state", q, ip)
    import json
    return json.loads(body)


# ===========================================================================
# 段階1: /state must not leak to token-less / bad-token callers
# ===========================================================================
ta, tb, g = fresh_started_room()
g.players[0].new_dev_cards = ["victory_point"]

REMOTE = "203.0.113.7"    # not a trusted address
LOCAL = "127.0.0.1"       # trusted (default CATAN_DEBUG_CIDRS)

# --- remote, no token -> spectator, nothing secret --------------------------
st = state_players(None, REMOTE)
check(st.get("role") == SPECTATOR_VIEW, "remote no-token: role is spectator")
check(st.get("you") is None, "remote no-token: you is null")
for p in st["players"]:
    for k in SECRET_KEYS:
        check(k not in p, f"remote no-token: no '{k}' for P{p['id']}")

# --- remote, bogus token -> spectator, nothing secret -----------------------
st = state_players("totally-made-up", REMOTE)
check(st.get("role") == SPECTATOR_VIEW, "remote bad-token: role is spectator")
for p in st["players"]:
    for k in SECRET_KEYS:
        check(k not in p, f"remote bad-token: no '{k}' for P{p['id']}")

# --- a real token still gets that player's own private view -----------------
st = state_players(ta, REMOTE)
me = next(p for p in st["players"] if p["id"] == st["you"])
others = [p for p in st["players"] if p["id"] != st["you"]]
check(st.get("role") == "player", "valid token: role is player")
check(all(k in me for k in ("resources", "dev_cards", "hidden_vp")),
      "valid token: own secrets present")
check(all(("resources" not in p and "hidden_vp" not in p) for p in others),
      "valid token: other players' secrets still hidden")

# --- the local monitor keeps its full view (view=monitor) -------------------
st = state_players(None, LOCAL, view="monitor")
check(st.get("role") == DEBUG_VIEW, "local monitor (view=monitor): role is debug")
for p in st["players"]:
    check(all(k in p for k in ("resources", "dev_cards", "hidden_vp")),
          f"local monitor: full view for P{p['id']}")

# a local request WITHOUT view=monitor is NOT the monitor: public only
st = state_players(None, LOCAL)
check(st.get("role") == SPECTATOR_VIEW,
      "local page without view=monitor is a spectator (no upgrade by IP)")
for p in st["players"]:
    check("resources" not in p and "hidden_vp" not in p,
          f"local non-monitor: no secrets for P{p['id']}")

# a REMOTE request asking for view=monitor is refused the full view
st = state_players(None, REMOTE, view="monitor")
check(st.get("role") == SPECTATOR_VIEW, "remote view=monitor is still a spectator")


# ===========================================================================
# 段階2: token-less /action must be refused for remote callers
# ===========================================================================
ta, tb, g = fresh_started_room()
cur = g.current_player_idx

# every player-turn action, remotely, with no token
for act in ("roll", "end_turn", "buy_dev"):
    r = handle_action(act, {}, None, local=False)
    check(r and r.get("ok") is False and "外部" in r.get("error", ""),
          f"remote no-token: {act} refused")

# build_settlement: the original exploit - must NOT change the game
before = g.current_player().settlements_left
r = handle_action("build_settlement", {"vertex": 0}, None, local=False)
after = g.current_player().settlements_left
check(r and r.get("ok") is False, "remote no-token: build_settlement refused")
check(before == after, "remote no-token: build_settlement did not change the game")

# discard / trade_respond
r = handle_action("discard", {"player": cur, "resources": {}}, None, local=False)
check(r and r.get("ok") is False, "remote no-token: discard refused")
r = handle_action("trade_respond", {"player": cur, "accept": True}, None, local=False)
check(r and r.get("ok") is False, "remote no-token: trade_respond refused")

# the monitor-only helpers are refused too
for act in ("room_init", "monitor_new", "auto_setup", "give_resources"):
    r = handle_action(act, {}, None, local=False)
    check(r and r.get("ok") is False, f"remote no-token: {act} refused")

# --- locally, a token-less (hot-seat) request may still act ------------------
finish_setup(g)
r = handle_action("roll", {}, None, local=True)
check(r and r.get("ok") is True, "local no-token: hot-seat roll still works")

# --- a remote request WITH a valid token plays normally ---------------------
ta2, tb2, g2 = fresh_started_room()
finish_setup(g2)
cur2 = g2.current_player_idx
r = handle_action("roll", {}, cur2, local=False)
check(r and r.get("ok") is True, "remote valid token: current player may roll")

# and that same valid token can't act out of turn
nxt = (cur2 + 1) % len(g2.players)
r = handle_action("roll", {}, nxt, local=False)
check(r and r.get("ok") is False, "remote valid token: out-of-turn roll refused")

# ===========================================================================
# route_post end-to-end (token in the JSON body, remote IP)
# ===========================================================================
handle_lobby("room_reset", {})
a = handle_lobby("join", {"name": "x"})
b = handle_lobby("join", {"name": "y"})
for key, val in (("desert", "center"), ("numbers", "official"), ("victory", 10)):
    handle_lobby("room_setting", {"token": a["token"], "key": key, "value": val})
handle_lobby("room_roll", {"token": a["token"]})
handle_lobby("room_roll", {"token": b["token"]})
seats = ROOM["seats"]
toks = [a["token"], b["token"]]
order = sorted(range(2), key=lambda i: -sum(seats[i]["roll"]))
handle_lobby("room_pick", {"token": toks[order[0]], "slot": 1})
handle_lobby("room_color", {"token": toks[order[0]], "color": "red"})
handle_lobby("room_pick", {"token": toks[order[1]], "slot": 2})
handle_lobby("room_color", {"token": toks[order[1]], "color": "blue"})
handle_lobby("room_start", {"token": a["token"]})

r = route_post({"action": "give_resources"}, {}, REMOTE)
check(r.get("ok") is False, "route_post: remote tokenless give_resources refused")
r = route_post({"action": "give_resources"}, {}, LOCAL)
check(r.get("ok") is True, "route_post: local tokenless give_resources allowed")

# --- lobby power actions from a remote caller ------------------------------
# A forwarded link must not be able to wipe / hijack the room.
handle_lobby("room_reset", {})
pa = handle_lobby("join", {"name": "p"})
pb = handle_lobby("join", {"name": "q"})
r = route_post({"action": "room_reset"}, {}, REMOTE)
check(r.get("ok") is False, "route_post: remote room_reset refused")
check(len(ROOM["seats"]) == 2, "remote room_reset did not wipe the room")
r = route_post({"action": "room_setting", "key": "desert", "value": "center"}, {}, REMOTE)
check(r.get("ok") is False, "route_post: remote room_setting refused")
r = route_post({"action": "room_start"}, {}, REMOTE)
check(r.get("ok") is False, "route_post: remote room_start refused")
handle_lobby("room_reset", {})   # leave the room clean

print()
print("AUTHZ TEST OK" if fails == 0 else "AUTHZ TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
