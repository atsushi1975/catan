#!/usr/bin/env python3
"""House rule: where the desert goes (initial desert placement)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import Board
from game.resources import TerrainType
import app_core
from app_core import handle_lobby, serialize_room, ROOM

fails = 0
def check(cond, msg):
    global fails
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        fails += 1


def desert_key(b):
    for k, h in b.hexes.items():
        if h.terrain == TerrainType.DESERT:
            return k
    return None


def is_coastal(b, k):
    return k in set(b._ring(2))


# board gen
ok = all(desert_key(Board(seed=s, desert="center")) == (0, 0) for s in range(30))
check(ok, "center: the desert is always the middle hex")

ok = True
for s in range(60):
    b = Board(seed=s, desert="coast_ng")
    if is_coastal(b, desert_key(b)):
        ok = False
check(ok, "coast_ng: the desert is never on the coast")

coastal_seen = any(is_coastal(Board(seed=s, desert="none"), desert_key(Board(seed=s, desert="none")))
                   for s in range(60))
center_seen = any(desert_key(Board(seed=s, desert="none")) == (0, 0) for s in range(60))
check(coastal_seen, "none: the desert can land on the coast")
check(center_seen, "none: the desert can land in the centre")

check(Board(seed=1).desert_mode == "coast_ng", "default mode is coast_ng")
check(desert_key(Board(seed=1)) == desert_key(Board(seed=1, desert="coast_ng")),
      "default matches coast_ng")


# lobby plumbing
handle_lobby("room_reset", {})
r = serialize_room()
f = r.get("rules_fixed") or {}
check(f.get("desert") is False and f.get("numbers") is False and f.get("victory") is False, "rules start unfixed")

TOK_A = handle_lobby("join", {"name": "アリス"})["token"]
handle_lobby("join", {"name": "ボブ"})

def preview_desert():
    st = serialize_room()
    if not st.get("board"):
        return None
    for h in st["board"]["hexes"]:
        if h["terrain"] == "desert":
            return (h["q"], h["r"])
    return None

# fix desert only
res = handle_lobby("room_setting", {"token": TOK_A, "key": "desert", "value": "center"})
check(res and res.get("ok"), "room_setting(desert) is accepted")
f = serialize_room().get("rules_fixed") or {}
check(f.get("desert") is True and f.get("numbers") is False and f.get("victory") is False, "only desert is fixed")
dk = preview_desert()
check(dk == (0, 0), f"desert fixed to center (got {dk})")

# cannot change desert again
res = handle_lobby("room_setting", {"token": TOK_A, "key": "desert", "value": "none"})
check(res and res.get("ok") is False, "fixed desert cannot be changed")

# fix numbers
res = handle_lobby("room_setting", {"token": TOK_A, "key": "numbers", "value": "random"})
check(res and res.get("ok"), "room_setting(numbers) is accepted")
f = serialize_room().get("rules_fixed") or {}
check(f.get("desert") is True and f.get("numbers") is True and f.get("victory") is False, "desert+numbers fixed")

# fix victory
res = handle_lobby("room_setting", {"token": TOK_A, "key": "victory", "value": 7})
check(res and res.get("ok"), "room_setting(victory) is accepted")
f = serialize_room().get("rules_fixed") or {}
check(all(f.get(k) for k in ("desert","numbers","victory")), "all rules fixed")

# cannot change others
res = handle_lobby("room_setting", {"token": TOK_A, "key": "numbers", "value": "official"})
check(res and res.get("ok") is False, "fixed numbers cannot be changed")
res = handle_lobby("room_setting", {"token": TOK_A, "key": "victory", "value": 10})
check(res and res.get("ok") is False, "fixed victory cannot be changed")

# unknown invalid
res = handle_lobby("room_setting", {"token": TOK_A, "key": "desert", "value": "nonsense"})
check(res and res.get("ok") is False, "invalid value refused")
res = handle_lobby("room_setting", {"token": TOK_A, "key": "nope", "value": "x"})
check(res and res.get("ok") is False, "unknown key refused")

# playing refuses
ROOM["phase"] = "playing"
res = handle_lobby("room_setting", {"token": TOK_A, "key": "numbers", "value": "official"})
check(res and res.get("ok") is False, "cannot change rules while playing")
ROOM["phase"] = "lobby"

# reset unlocks
handle_lobby("room_reset", {})
r2 = serialize_room()
f2 = r2.get("rules_fixed") or {}
check(f2.get("desert") is False and f2.get("numbers") is False and f2.get("victory") is False, "room_reset unlocks all rules")
check(r2["settings"] == {}, "room_reset clears settings")

# start requires all fixed
handle_lobby("join", {"name": "x"})
handle_lobby("join", {"name": "y"})
seats = ROOM["seats"]
toks = [s["token"] for s in seats]
# fix all rules first
handle_lobby("room_setting", {"token": toks[0], "key": "desert", "value": "center"})
handle_lobby("room_setting", {"token": toks[0], "key": "numbers", "value": "official"})
handle_lobby("room_setting", {"token": toks[0], "key": "victory", "value": 10})
handle_lobby("room_roll", {"token": toks[0]})
handle_lobby("room_roll", {"token": toks[1]})
order = sorted(range(2), key=lambda i: -sum(seats[i]["roll"]))
handle_lobby("room_pick", {"token": toks[order[0]], "slot": 1})
handle_lobby("room_color", {"token": toks[order[0]], "color": "red"})
handle_lobby("room_pick", {"token": toks[order[1]], "slot": 2})
handle_lobby("room_color", {"token": toks[order[1]], "color": "blue"})
res = handle_lobby("room_start", {"token": toks[0]})
check(res and res.get("ok"), "can start after all rules fixed")
g = ROOM["g"]
check(g.board.numbers_mode == "official", "board uses chosen numbers")
check(g.victory_target == 10, "board uses chosen victory")

handle_lobby("room_reset", {})

print()
print("HOUSE RULES TEST OK" if fails == 0 else "HOUSE RULES TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
