#!/usr/bin/env python3
"""House rule: where the desert goes (initial desert placement).

Lobby radio boxes:
  center    - always the middle hex
  coast_ng  - anywhere inland, so NO coastal hex is desert (the default)
  none      - anywhere on the board, coast included

Covers both the board generation and the lobby plumbing (the room setting,
the action that changes it, and that the map is rebuilt with the new rule).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import Board
from game.resources import TerrainType
import app_core
from app_core import handle_lobby, handle_action, serialize_room, ROOM, DESERT_MODES

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


# ===========================================================================
# 段階1: board generation for each mode
# ===========================================================================
# center -> always (0,0)
ok = all(desert_key(Board(seed=s, desert="center")) == (0, 0) for s in range(30))
check(ok, "center: the desert is always the middle hex")

# coast_ng -> never coastal
ok = True
for s in range(60):
    b = Board(seed=s, desert="coast_ng")
    if is_coastal(b, desert_key(b)):
        ok = False
check(ok, "coast_ng: the desert is never on the coast")

# none -> can be coastal and can be central
coastal_seen = any(is_coastal(Board(seed=s, desert="none"), desert_key(Board(seed=s, desert="none")))
                   for s in range(60))
center_seen = any(desert_key(Board(seed=s, desert="none")) == (0, 0) for s in range(60))
check(coastal_seen, "none: the desert can land on the coast")
check(center_seen, "none: the desert can land in the centre")

# the default is coast_ng (unchanged behaviour for old callers)
check(Board(seed=1).desert_mode == "coast_ng", "default mode is coast_ng")
check(desert_key(Board(seed=1)) == desert_key(Board(seed=1, desert="coast_ng")),
      "default matches coast_ng")


# ===========================================================================
# 段階2: lobby plumbing
# ===========================================================================
handle_lobby("room_reset", {})
r = serialize_room()
check(r["settings"].get("desert") == "coast_ng", "room starts with the coast_ng rule")

# two players so a preview board exists
handle_lobby("join", {"name": "アリス"})
handle_lobby("join", {"name": "ボブ"})

def preview_desert():
    st = serialize_room()
    if not st.get("board"):
        return None
    for h in st["board"]["hexes"]:
        if h["terrain"] == "desert":
            return (h["q"], h["r"])
    return None

# switch to center -> the preview must be rebuilt and the desert must be central
res = handle_lobby("room_setting", {"key": "desert", "value": "center"})
check(res and res.get("ok"), "room_setting(center) is accepted")
check(serialize_room()["settings"]["desert"] == "center", "the setting is stored")
dk = preview_desert()
check(dk == (0, 0), f"after center, the previewed desert is the middle hex (got {dk})")

# an invalid value is refused and changes nothing
res = handle_lobby("room_setting", {"key": "desert", "value": "nonsense"})
check(res and res.get("ok") is False, "an invalid desert value is refused")
check(serialize_room()["settings"]["desert"] == "center", "the setting is untouched")

# an unknown key is refused
res = handle_lobby("room_setting", {"key": "nope", "value": "x"})
check(res and res.get("ok") is False, "an unknown setting key is refused")

# non-lobby (playing) must refuse changes
ROOM["phase"] = "playing"
res = handle_lobby("room_setting", {"key": "desert", "value": "none"})
check(res and res.get("ok") is False, "the rule cannot be changed once playing")
ROOM["phase"] = "lobby"

# the setting must survive a reset back to defaults
handle_lobby("room_reset", {})
check(serialize_room()["settings"].get("desert") == "coast_ng", "room_reset restores the default rule")

# end-to-end: choose "center", start a game, and the played board respects it
handle_lobby("join", {"name": "x"})
handle_lobby("join", {"name": "y"})
handle_lobby("room_setting", {"key": "desert", "value": "center"})
seats = ROOM["seats"]
toks = [s["token"] for s in seats]
handle_lobby("room_roll", {"token": toks[0]})
handle_lobby("room_roll", {"token": toks[1]})
order = sorted(range(2), key=lambda i: -sum(seats[i]["roll"]))
handle_lobby("room_pick", {"token": toks[order[0]], "slot": 1})
handle_lobby("room_pick", {"token": toks[order[1]], "slot": 2})
res = handle_lobby("room_start", {})
check(res and res.get("ok"), "the game starts with the chosen rule")
g = ROOM["g"]
dk = desert_key(g.board)
check(dk == (0, 0), f"the played board puts the desert in the centre (got {dk})")
check(g.board.desert_mode == "center", "the board records the chosen mode")

handle_lobby("room_reset", {})

print()
print("HOUSE RULES TEST OK" if fails == 0 else "HOUSE RULES TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
