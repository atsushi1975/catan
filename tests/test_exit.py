#!/usr/bin/env python3
"""Leaving a game: after the game (leave) and during it (consent of the others).

  A. leave after a winner exists: ONE player pressing sends everybody back to
     the lobby (room reset + notice). While the game runs it is refused.
  B. exit_request / exit_vote / exit_cancel: every other player must agree
  C. state: the pending request is shown only to seated players (no votes of
     others); the "game aborted" notice is public for NOTICE_SECONDS
  D. all of it needs the token of a seat; remote room_reset stays refused
  E. a finished game nobody seated has touched for a while is reset lazily

Time is faked through app_core._now, so nothing here sleeps.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_core
from app_core import handle_lobby, route_get, route_post, ROOM

fails = 0
def check(cond, msg):
    global fails
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        fails += 1


REMOTE = "203.0.113.7"    # not a trusted address: players really play from here
LOCAL = "127.0.0.1"
NAMES = ["アリス", "ボブ", "カレン", "ダン"]

# --- fake clock --------------------------------------------------------------
real_now = app_core._now
clock = [1000.0]
app_core._now = lambda: clock[0]


def at(t):
    clock[0] = float(t)


def start_game(n=2):
    """n players join, fix the rules, draft and start. Returns their tokens."""
    handle_lobby("room_reset", {})
    toks = [handle_lobby("join", {"name": NAMES[i]})["token"] for i in range(n)]
    for key, val in (("desert", "center"), ("numbers", "official"), ("victory", 10)):
        handle_lobby("room_setting", {"token": toks[0], "key": key, "value": val})
    for t in toks:
        handle_lobby("room_roll", {"token": t})
    seats = ROOM["seats"]
    order = sorted(range(n), key=lambda i: (-sum(seats[i]["roll"]), i))
    colors = ["red", "blue", "white", "orange"]
    for rank, i in enumerate(order):
        handle_lobby("room_pick", {"token": toks[i], "slot": rank + 1})
        handle_lobby("room_color", {"token": toks[i], "color": colors[rank]})
    r = handle_lobby("room_start", {"token": toks[0]})
    assert r.get("ok"), r
    return toks


def state(token=None, ip=REMOTE, view=None):
    q = {}
    if token:
        q["token"] = [token]
    if view:
        q["view"] = [view]
    status, ctype, body = route_get("/state", q, ip)
    return json.loads(body)


def act(action, token, ip=REMOTE, **kw):
    p = {"action": action}
    if token is not None:
        p["token"] = token
    p.update(kw)
    return route_post(p, {}, ip)


def finish(winner=0):
    ROOM["g"].winner = winner


def in_game():
    return ROOM["phase"] == "playing" and ROOM["g"] is not None


def in_lobby_empty():
    return ROOM["phase"] == "lobby" and ROOM["seats"] == [] and ROOM["g"] is None


# ===========================================================================
# A. leave
# ===========================================================================
at(1000)
t = start_game(2)
r = act("leave", t[0])
check(r.get("ok") is False and "退出要求" in r.get("error", ""),
      "leave while the game runs (no winner) is refused, pointing at the exit request")
check(in_game() and len(ROOM["seats"]) == 2, "a refused leave changes nothing")

finish()
st = state(t[1])
check(st.get("phase") != "lobby" and st.get("winner") == 0,
      "before anybody leaves, the others can read the finished game")
r = act("leave", t[0])
check(r.get("ok") is True, "leave after a winner exists is accepted")
check(in_lobby_empty(), "ONE player leaving sends everybody back: the room is reset")
st = state(t[1])
check(st.get("phase") == "lobby" and "players" not in st,
      "the others now get the lobby from /state")
check(st.get("notice", {}).get("text") == "アリスさんがロビーに戻りました",
      "...with a notice that names who went back")
check(state(None).get("notice") is not None, "the notice is public (no token needed)")
r = act("leave", t[1])
check(r.get("ok") is False and in_lobby_empty(),
      "the other player's seat is gone too: a second leave is refused, nothing breaks")

# three players: still one press is enough
t = start_game(3)
finish()
check(act("leave", t[2]).get("ok") is True and in_lobby_empty(),
      "3 players: one leave resets the room for all of them")
check("カレン" in state(None).get("notice", {}).get("text", ""), "...and names the player who pressed")
# the seats are gone, so the old tokens cannot act in the new lobby
check(all(act("room_roll", x).get("ok") is False for x in t), "old tokens no longer have a seat")
r = handle_lobby("join", {"name": "新しい人"})
check(r.get("ok") is True and len(ROOM["seats"]) == 1, "everybody can join the fresh lobby again")
handle_lobby("room_reset", {})

# D: no seat, no leave
t = start_game(2)
finish()
check(act("leave", None).get("ok") is False, "leave without a token is refused")
check(act("leave", "made-up-token").get("ok") is False, "leave with an unknown token is refused")
check(in_game() and len(ROOM["seats"]) == 2, "...and the finished game is untouched")
handle_lobby("room_reset", {})

# the old lobby leave still works
handle_lobby("room_reset", {})
a = handle_lobby("join", {"name": "アリス"})["token"]
handle_lobby("join", {"name": "ボブ"})
check(act("leave", a).get("ok") is True and len(ROOM["seats"]) == 1,
      "lobby leave still removes the seat")
handle_lobby("room_reset", {})

# ===========================================================================
# B. exit_request: everybody else agrees
# ===========================================================================
at(1000)
t = start_game(3)
r = act("exit_request", t[0])
check(r.get("ok") is True, "a seated player may ask to leave a running game")
rid = r["id"]
check(ROOM["exit_request"]["seat"] == 0 and ROOM["exit_request"]["expires"] == 1030.0,
      "the request records the seat and expires after 30 s")
r = act("exit_vote", t[1], id=rid, approve=True)
check(r.get("ok") is True and in_game(), "one yes of two is not enough yet")
r = act("exit_vote", t[2], id=rid, approve=True)
check(r.get("ok") is True, "the last yes is accepted")
check(in_lobby_empty(), "all others approved -> the game is aborted and the room reset")
check(ROOM["exit_request"] is None, "...and no request is left over")
st = state(None)
check(st.get("phase") == "lobby" and st.get("notice", {}).get("text") == "ゲームは中止されました（アリスさんの退出）",
      "the notice names the player who left")
check(state(None, ip=LOCAL, view="monitor").get("notice") is not None,
      "the notice is public: the monitor sees it too")
check(state(t[1]).get("notice") is not None, "a former player (no seat any more) sees it")

# two-player game
at(1000)
t = start_game(2)
rid = act("exit_request", t[1])["id"]
act("exit_vote", t[0], id=rid, approve=True)
check(in_lobby_empty(), "2-player game: the one other player agreeing aborts it")
check("ボブ" in state(None).get("notice", {}).get("text", ""), "...and the notice names the asker")

# notice lifetime and ids
first_id = state(None)["notice"]["id"]
at(1000 + 60)
check(state(None).get("notice") is not None, "the notice is still shown after exactly 60 s")
at(1000 + 61)
check("notice" not in state(None), "the notice is gone after 60 s")
at(2000)
t = start_game(2)
rid = act("exit_request", t[0])["id"]
act("exit_vote", t[1], id=rid, approve=True)
check(state(None)["notice"]["id"] > first_id, "notice ids keep growing across resets")

# ===========================================================================
# B. exit_request: refusal, timeout, cooldown
# ===========================================================================
at(1000)
t = start_game(3)
notice_before = ROOM["notice"]      # (left over from an earlier abort above)
rid = act("exit_request", t[0])["id"]
r = act("exit_vote", t[1], id=rid, approve=False)
check(r.get("ok") is True, "a refusal is accepted")
check(in_game() and ROOM["exit_request"] is None,
      "one refusal ends the request at once; the game goes on (even before the 3rd voted)")
check(ROOM["notice"] is notice_before, "a refused request creates no notice")
check(act("exit_request", t[0]).get("ok") is False,
      "the refused player is in the cooldown")
check(act("exit_request", t[1]).get("ok") is True, "another player may ask during that cooldown")
act("exit_cancel", t[1])

# timeout
at(1000)
t = start_game(3)
rid = act("exit_request", t[0])["id"]
act("exit_vote", t[1], id=rid, approve=True)
at(1029)
check(state(t[2]).get("exit_request") is not None, "still pending 1 s before the deadline")
at(1031)
check("exit_request" not in state(t[2]), "after 30 s the request is gone from the state")
check(in_game() and ROOM["exit_request"] is None, "an expired request does not abort the game")
r = act("exit_vote", t[2], id=rid, approve=True)
check(r.get("ok") is False, "a late vote on the expired request is refused")
check(in_game(), "...so the late yes did not abort the game")
at(1100)
r = act("exit_request", t[0])
check(r.get("ok") is False and "秒" in r.get("error", ""), "re-asking inside the 120 s cooldown is refused")
at(1149)
check(act("exit_request", t[0]).get("ok") is False, "still cooling down just before expiry+120 s")
at(1151)
r = act("exit_request", t[0])
check(r.get("ok") is True, "after the cooldown (counted from the expiry) it may ask again")

# a request that nobody touches is also settled by a plain handle_lobby call
at(1000)
t = start_game(2)
rid = handle_lobby("exit_request", {"token": t[0]})["id"]
at(1031)
r = handle_lobby("exit_vote", {"token": t[1], "id": rid, "approve": True})
check(r.get("ok") is False and in_game(), "expiry is judged inside the action itself, no timer needed")

# ===========================================================================
# B. who may vote, and how often
# ===========================================================================
at(1000)
t = start_game(3)
rid = act("exit_request", t[0])["id"]
check(act("exit_vote", t[0], id=rid, approve=True).get("ok") is False,
      "the requester cannot vote on their own request")
check(ROOM["exit_request"]["votes"] == {}, "...and nothing was recorded")
check(act("exit_request", t[1]).get("ok") is False, "only one request at a time")
check(act("exit_vote", t[1], id=rid, approve=True).get("ok") is True, "first vote counts")
r = act("exit_vote", t[1], id=rid, approve=False)
check(r.get("ok") is False, "a second vote is refused")
check(ROOM["exit_request"] is not None and ROOM["exit_request"]["votes"] == {1: True},
      "...and it cannot flip the first vote")
check(act("exit_vote", t[2], id=rid + 99, approve=True).get("ok") is False,
      "a vote for a different request id is refused")
check(act("exit_vote", t[2], id=rid, approve="yes").get("ok") is False,
      "approve must be true / false")
check(act("exit_vote", None, id=rid, approve=True).get("ok") is False,
      "no token -> no vote")
check(act("exit_vote", "made-up-token", id=rid, approve=True).get("ok") is False,
      "a token without a seat cannot vote")
check(act("exit_vote", "made-up-token", id=rid, approve=False).get("ok") is False
      and ROOM["exit_request"] is not None, "...not even a refusal can be forced by an outsider")
check(act("exit_request", None).get("ok") is False and act("exit_cancel", None).get("ok") is False,
      "no token -> no request, no cancel")
check(act("exit_cancel", t[1]).get("ok") is False and ROOM["exit_request"] is not None,
      "only the requester may cancel")
check(act("exit_cancel", t[0]).get("ok") is True and ROOM["exit_request"] is None,
      "the requester can cancel")
check(act("exit_request", t[0]).get("ok") is True, "a cancel is no refusal: no cooldown")
check(act("exit_vote", t[1], id=rid, approve=True).get("ok") is False,
      "votes for the cancelled (old) id are refused")

# spectators / monitor
start_game(2)
check(handle_lobby("exit_request", {}).get("ok") is False, "monitor (no token) cannot ask")
check(route_post({"action": "exit_request"}, {}, LOCAL).get("ok") is False,
      "...even from a trusted address")

# no request during the lobby or after the game
handle_lobby("room_reset", {})
a = handle_lobby("join", {"name": "アリス"})["token"]
check(act("exit_request", a).get("ok") is False, "no exit request in the lobby")
t = start_game(2)
finish()
check(act("exit_request", t[0]).get("ok") is False, "no exit request once a winner exists (use leave)")
check(ROOM["exit_request"] is None, "...and none was stored")

# a pending request dies by itself when the game ends
at(1000)
t = start_game(2)
act("exit_request", t[0])
finish()
check("exit_request" not in state(t[1]), "a request pending while the game ends disappears")

# ===========================================================================
# C. what the state shows
# ===========================================================================
at(1000)
t = start_game(3)
rid = act("exit_request", t[0])["id"]
act("exit_vote", t[1], id=rid, approve=True)
at(1010)
mine = state(t[0])["exit_request"]
b = state(t[1])["exit_request"]
c = state(t[2])["exit_request"]
check(set(c) == {"id", "by", "mine", "my_vote", "remaining"}, "the request view has exactly the agreed fields")
check(c["id"] == rid and c["by"] == "アリス" and c["mine"] is False, "id / by / mine for a bystander")
check(c["my_vote"] is None and b["my_vote"] is True, "my_vote shows only the player's own vote")
check(mine["mine"] is True and mine["my_vote"] is None, "the requester sees mine=true and no votes")
check(c["remaining"] == 20, "remaining is computed from the server clock (30 s - 10 s)")
check("votes" not in json.dumps(c) and "votes" not in json.dumps(mine),
      "the votes of others are not in the response")
check("exit_request" not in state(None) and "exit_request" not in state("made-up-token"),
      "spectators and seat-less tokens get no request")
check("exit_request" not in state(None, ip=LOCAL, view="monitor"), "the monitor gets none either")
act("exit_vote", t[2], id=rid, approve=False)
check("exit_request" not in state(t[1]), "a settled request is no longer shown")

# ===========================================================================
# D. remote callers
# ===========================================================================
at(1000)
t = start_game(2)
r = route_post({"action": "room_reset"}, {}, REMOTE)
check(r.get("ok") is False, "room_reset from outside is still refused")
check(handle_lobby("room_reset", {}, local=False).get("ok") is False,
      "...also straight on handle_lobby(local=False)")
check(in_game() and len(ROOM["seats"]) == 2, "...and the running game survived")
check(act("exit_request", t[0], ip=REMOTE).get("ok") is True,
      "a remote seated player can still use the exit request")
act("exit_cancel", t[0])

# ===========================================================================
# E. idle clean-up of a finished game
# ===========================================================================
at(5000)
t = start_game(2)
state(t[0])                                  # a seated visit: last_seen = 5000
check(ROOM["last_seen"] == 5000.0, "a seated token's visit is recorded")
at(105000)
check(state(None).get("phase") != "lobby" and in_game(),
      "a game in progress is never reset for being idle")
finish()
at(5000)
state(t[0])
at(5300)
state(None, ip=LOCAL, view="monitor")
at(5500)
state(None)
check(ROOM["last_seen"] == 5000.0, "spectator / monitor visits do not count as activity")
at(5599)
state(None)
check(in_game(), "finished, 599 s idle: still there")
at(5600)
st = state(None)
check(st.get("phase") == "lobby" and in_lobby_empty(), "finished + 600 s without a seated visit -> reset")

# a seated visit pushes the deadline
at(7000)
t = start_game(2)
finish()
state(t[0])
at(7500)
state(t[1])
at(8000)
state(None)
check(in_game(), "a seated visit at +500 s moved the deadline (only 500 s since)")
at(8100)
state(None)
check(in_lobby_empty(), "...and 600 s after that visit it resets")

# the visit that arrives too late cannot save the room
at(9000)
t = start_game(2)
finish()
state(t[0])
at(9600)
st = state(t[0])
check(st.get("phase") == "lobby" and in_lobby_empty(), "a seated visit after the limit finds the room reset")

# the limit is a constant the tests can change
at(11000)
t = start_game(2)
finish()
state(t[0])
old = app_core.IDLE_RESET_SECONDS
app_core.IDLE_RESET_SECONDS = 5
at(11006)
state(None)
app_core.IDLE_RESET_SECONDS = old
check(in_lobby_empty(), "IDLE_RESET_SECONDS can be replaced (5 s here)")

# hot-seat monitor game (no seats): nothing to time, nothing is reset
handle_lobby("room_reset", {})
route_post({"action": "monitor_new"}, {}, LOCAL)
finish()
at(99999999)
state(None, ip=LOCAL, view="monitor")
check(in_game(), "a seat-less hot-seat game is not auto-reset")

# ---------------------------------------------------------------------------
handle_lobby("room_reset", {})
app_core._now = real_now

print()
print("EXIT TEST OK" if fails == 0 else "EXIT TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
