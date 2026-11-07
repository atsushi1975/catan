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
  * /state resolves THREE views: a real pid, 'spectator' (public only) or
    'debug' (everything - only while CATAN_HOTSEAT=1).
  * handle_action(actor=None) refuses every game action unless the operator
    explicitly set CATAN_HOTSEAT=1. The client address / X-Forwarded-For is
    never used for authorization.

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


def set_hotseat(on):
    """Turn the explicit token-less (hot-seat) switch on/off for one check."""
    if on:
        os.environ["CATAN_HOTSEAT"] = "1"
    else:
        os.environ.pop("CATAN_HOTSEAT", None)


def fresh_started_room():
    """Two joined players, drafted, game started - using the public API only."""
    set_hotseat(True)
    handle_lobby("room_reset", {})
    set_hotseat(False)
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
    set_hotseat(True)
    handle_action("auto_setup", {}, None)
    set_hotseat(False)


def state_players(token, view=None):
    """Read /state through route_get (so the real viewer resolution runs)."""
    q = {"token": [token]} if token else {}
    if view:
        q["view"] = [view]
    status, ctype, body = route_get("/state", q)
    import json
    return json.loads(body)


# ===========================================================================
# 段階1: /state must not leak to token-less / bad-token callers
# ===========================================================================
ta, tb, g = fresh_started_room()
g.players[0].new_dev_cards = ["victory_point"]

# --- no token / bogus token -> spectator, nothing secret --------------------
set_hotseat(False)
st = state_players(None)
check(st.get("role") == SPECTATOR_VIEW, "no-token: role is spectator")
check(st.get("you") is None, "no-token: you is null")
for p in st["players"]:
    for k in SECRET_KEYS:
        check(k not in p, f"no-token: no '{k}' for P{p['id']}")

st = state_players("totally-made-up")
check(st.get("role") == SPECTATOR_VIEW, "bad-token: role is spectator")
for p in st["players"]:
    for k in SECRET_KEYS:
        check(k not in p, f"bad-token: no '{k}' for P{p['id']}")

# --- a real token still gets that player's own private view -----------------
st = state_players(ta)
me = next(p for p in st["players"] if p["id"] == st["you"])
others = [p for p in st["players"] if p["id"] != st["you"]]
check(st.get("role") == "player", "valid token: role is player")
check(all(k in me for k in ("resources", "dev_cards", "hidden_vp")),
      "valid token: own secrets present")
check(all(("resources" not in p and "hidden_vp" not in p) for p in others),
      "valid token: other players' secrets still hidden")

# --- monitor view is gated by the explicit switch, never by the address -----
st = state_players(None, view="monitor")
check(st.get("role") == SPECTATOR_VIEW,
      "view=monitor is a spectator while hot-seat is off")
for p in st["players"]:
    check("resources" not in p and "hidden_vp" not in p,
          f"monitor view (off): no secrets for P{p['id']}")

set_hotseat(True)
st = state_players(None, view="monitor")
check(st.get("role") == DEBUG_VIEW, "view=monitor is debug with CATAN_HOTSEAT=1")
for p in st["players"]:
    check(all(k in p for k in ("resources", "dev_cards", "hidden_vp")),
          f"monitor view (on): full view for P{p['id']}")
set_hotseat(False)

# a player page never gets the monitor view just by asking for it
st = state_players(ta, view="monitor")
check(st.get("role") == "player", "a valid player token stays a player view")


# ===========================================================================
# 段階2: token-less /action must be refused unless CATAN_HOTSEAT=1
# ===========================================================================
ta, tb, g = fresh_started_room()
set_hotseat(False)
cur = g.current_player_idx

# every player-turn action, with no token and the switch off
for act in ("roll", "end_turn", "buy_dev"):
    r = handle_action(act, {}, None)
    check(r and r.get("ok") is False and "ホットシート" in r.get("error", ""),
          f"no-token (off): {act} refused")

# build_settlement: the original exploit - must NOT change the game
before = g.current_player().settlements_left
r = handle_action("build_settlement", {"vertex": 0}, None)
after = g.current_player().settlements_left
check(r and r.get("ok") is False, "no-token (off): build_settlement refused")
check(before == after, "no-token (off): build_settlement did not change the game")

# discard / trade_respond
r = handle_action("discard", {"player": cur, "resources": {}}, None)
check(r and r.get("ok") is False, "no-token (off): discard refused")
r = handle_action("trade_respond", {"player": cur, "accept": True}, None)
check(r and r.get("ok") is False, "no-token (off): trade_respond refused")

# the monitor-only helpers are refused too
for act in ("room_init", "monitor_new", "auto_setup", "give_resources"):
    r = handle_action(act, {}, None)
    check(r and r.get("ok") is False, f"no-token (off): {act} refused")

# --- with the explicit switch on, a token-less hot-seat request may act -----
finish_setup(g)
set_hotseat(True)
r = handle_action("roll", {}, None)
check(r and r.get("ok") is True, "hot-seat on: token-less roll works")
set_hotseat(False)

# --- a token WITH a valid token plays normally ------------------------------
ta2, tb2, g2 = fresh_started_room()
finish_setup(g2)
set_hotseat(False)
cur2 = g2.current_player_idx
r = handle_action("roll", {}, cur2)
check(r and r.get("ok") is True, "valid token: current player may roll")

# and that same valid token can't act out of turn
nxt = (cur2 + 1) % len(g2.players)
r = handle_action("roll", {}, nxt)
check(r and r.get("ok") is False, "valid token: out-of-turn roll refused")

# ===========================================================================
# route_post end-to-end (token in the JSON body; no client address involved)
# ===========================================================================
set_hotseat(True)
handle_lobby("room_reset", {})
set_hotseat(False)
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

set_hotseat(False)
r = route_post({"action": "give_resources"}, {})
check(r.get("ok") is False, "route_post: tokenless give_resources refused when off")
set_hotseat(True)
r = route_post({"action": "give_resources"}, {})
check(r.get("ok") is True, "route_post: tokenless give_resources allowed when on")
set_hotseat(False)

# --- lobby power actions without a seat ------------------------------------
# A forwarded link must not be able to wipe / hijack the room.
set_hotseat(True)
handle_lobby("room_reset", {})
set_hotseat(False)
pa = handle_lobby("join", {"name": "p"})
pb = handle_lobby("join", {"name": "q"})
r = route_post({"action": "room_reset"}, {})
check(r.get("ok") is False, "route_post: tokenless room_reset refused when off")
check(len(ROOM["seats"]) == 2, "refused room_reset did not wipe the room")
r = route_post({"action": "room_setting", "key": "desert", "value": "center"}, {})
check(r.get("ok") is False, "route_post: room_setting without a seat refused")
r = route_post({"action": "room_start"}, {})
check(r.get("ok") is False, "route_post: room_start without a seat refused")
set_hotseat(True)
handle_lobby("room_reset", {})   # leave the room clean
set_hotseat(False)

print()
print("AUTHZ TEST OK" if fails == 0 else "AUTHZ TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
