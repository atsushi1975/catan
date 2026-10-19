# tests/test_vp.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import Board
from game.game import Game
from game.resources import ResourceType, VICTORY_TARGET

def setup_game():
    g = Game(num_players=4, seed=5)
    b = g.board
    verts = list(b.vertices.keys())
    placed = 0
    while g.phase == "setup" and placed < 16:
        candidate = None
        for v in verts:
            info = b.vertices[v]
            if info["building"] is not None: continue
            ok = True
            for adj in b.adjacent_vertices(v):
                if b.vertices[adj]["building"] is not None:
                    ok = False; break
            if ok:
                candidate = v; break
        assert candidate is not None
        assert g.place_setup_settlement(candidate)
        road_edge = None
        for ek in b.edges:
            if candidate in ek and b.edges[ek]["road_owner"] is None:
                road_edge = ek; break
        assert g.place_setup_road(road_edge)
        placed += 1
    return g

def test_city_and_vp():
    g = setup_game()
    p = g.current_player()
    g.roll_dice()
    p.resources[ResourceType.WOOD] = 10
    p.resources[ResourceType.BRICK] = 10
    p.resources[ResourceType.SHEEP] = 10
    p.resources[ResourceType.WHEAT] = 10
    p.resources[ResourceType.ORE] = 10
    # build a city on an existing settlement owned by p
    settled_vertex = None
    for v, info in g.board.vertices.items():
        if info["owner"] == p.id and info["building"] == "settlement":
            settled_vertex = v
            break
    assert settled_vertex is not None
    # need a road adjacent? city doesn't require road, just upgrade settlement
    # but build_city_at checks building==settlement and owner==p
    before_vp = p.total_vp()
    ok = g.build_city_at(settled_vertex)
    print("city built:", ok)
    assert ok
    assert p.total_vp() == before_vp + 1
    print("VP ok", p.total_vp())

if __name__ == "__main__":
    test_city_and_vp()
    print("VP TEST OK")
