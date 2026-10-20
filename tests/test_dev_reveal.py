#!/usr/bin/env python3
"""End-of-game development-card reveal.

Rule added: once a winner is determined, every player's development-card
holding is made public - showing both what has been played (使用済) and what
is still held (未使用), so everyone can check the win.

Checks:
  * during play, other players' cards stay hidden (only counts / used log)
  * once the game is over, every player's remaining cards are visible
  * used cards are still reported distinctly from held cards
  * the owner can still see their own cards while playing
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_core
from app_core import serialize, serialize_player
from game.game import Game
from game.resources import ResourceType, VICTORY_TARGET

fails = 0
def check(cond, msg):
    global fails
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        fails += 1


def setup_game(n=3):
    g = Game(num_players=n, seed=7)
    b = g.board
    verts = list(b.vertices.keys())
    placed = 0
    while g.phase == "setup" and placed < 2 * n:
        candidate = None
        for v in verts:
            info = b.vertices[v]
            if info["building"] is not None:
                continue
            ok = True
            for adj in b.adjacent_vertices(v):
                if b.vertices[adj]["building"] is not None:
                    ok = False
                    break
            if ok:
                candidate = v
                break
        assert candidate is not None
        assert g.place_setup_settlement(candidate)
        road_edge = None
        for ek in b.edges:
            if candidate in ek and b.edges[ek]["road_owner"] is None:
                road_edge = ek
                break
        assert g.place_setup_road(road_edge)
        placed += 1
    return g


g = setup_game(3)

# Give each player a distinct dev-card situation.
g.players[0].dev_cards = ["knight", "monopoly"]
g.players[0].used_dev_cards = ["road_building"]
g.players[1].new_dev_cards = ["victory_point", "knight"]
g.players[1].used_dev_cards = []
g.players[2].dev_cards = []
g.players[2].used_dev_cards = ["year_of_plenty"]

# --- while playing ---------------------------------------------------------
while_playing = serialize(g, viewer=0)
p0 = while_playing["players"][0]
p1 = while_playing["players"][1]

check(p0.get("revealed") is False, "during play revealed=False")
check(p0.get("dev_cards") == ["knight", "monopoly"], "own cards visible during play")
check(p0.get("used_dev_cards") == ["road_building"], "own used cards visible during play")
check("dev_cards" not in p1, "other players' held cards hidden during play")
check(p1.get("used_dev_cards") == [], "other players' used log still public during play")
check(p1.get("dev_count") == 2, "other players' dev_count shown during play")

# monitor (viewer=None) always sees everything, but not "revealed"
mon = serialize(g, viewer=None)
check(mon["players"][1].get("revealed") is False, "monitor view: revealed stays False before win")
check(mon["players"][1].get("dev_cards") == ["victory_point", "knight"] or
      mon["players"][1].get("new_dev_cards") == ["victory_point", "knight"],
      "monitor always sees held cards")

# --- force a win ------------------------------------------------------------
g.players[1].vp = VICTORY_TARGET
g._check_win()
check(g.winner == 1, "winner is set")
check(g.phase == "end", "phase becomes end")

# viewer=0 (a loser) should now see everyone's cards
after = serialize(g, viewer=0)
a0, a1, a2 = after["players"]

check(a0.get("revealed") is True, "revealed=True after the game ends")
check(a1.get("revealed") is True, "revealed=True for every player after the game ends")

# the loser now sees the winner's still-held card
check(a1.get("dev_cards") == [], "winner's dev_cards reflects remaining held list")
check(a1.get("new_dev_cards") == ["victory_point", "knight"], "winner's fresh cards revealed")
check(a1.get("hidden_vp") == 0, "revealed view carries hidden_vp (here 0)")

# used vs held remain distinct
check(a0.get("used_dev_cards") == ["road_building"], "used cards listed separately")
check(a0.get("dev_cards") == ["knight", "monopoly"], "held cards listed separately")

# a player with no cards shows an empty list, not undefined
check(a2.get("dev_cards") == [], "empty holding is an empty list")

# total_vp equals vp + hidden once revealed (sanity on the serializer)
check(a0.get("total_vp") == a0.get("vp") + a0.get("hidden_vp"),
      "revealed total_vp = vp + hidden_vp")

# --- serialize_player unit check -------------------------------------------
class FakePlayer:
    def __init__(self):
        self.id = 5; self.name = "x"; self.color = "#000"
        self.dev_cards = ["knight"]; self.new_dev_cards = []
        self.used_dev_cards = ["monopoly"]; self.knights_played = 0
        self.roads_left = 15; self.settlements_left = 5; self.cities_left = 4
        self.longest_road = False; self.largest_army = False; self.free_roads = 0
        self.vp = 10; self.hidden_vp = 1
        self.resources = {r: 0 for r in ResourceType if r != ResourceType.DESERT}
    def total_resources(self):
        return 0
    def total_vp(self):
        return self.vp + self.hidden_vp

fp = FakePlayer()
d_play = serialize_player(fp, viewer=99)
check("dev_cards" not in d_play, "unit: hidden for other viewer while playing")
d_end = serialize_player(fp, viewer=99, reveal=True)
check(d_end.get("dev_cards") == ["knight"], "unit: revealed for other viewer when reveal=True")
check(d_end.get("revealed") is True, "unit: revealed flag set")

print()
print("DEV REVEAL TEST OK" if fails == 0 else "DEV REVEAL TEST FAILED (%d)" % fails)
sys.exit(0 if fails == 0 else 1)
