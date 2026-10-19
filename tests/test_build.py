# tests/test_build.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import Board
from game.game import Game
from game.resources import ResourceType

def setup_game():
    g = Game(num_players=4, seed=3)
    b = g.board
    verts = list(b.vertices.keys())
    placed = 0
    while g.phase == "setup" and placed < 16:
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

def test_give_resources_and_build():
    g = setup_game()
    p = g.current_player()
    # roll to main phase first
    g.roll_dice()
    # give resources after roll (avoid 7-discard)
    p.resources[ResourceType.WOOD] = 10
    p.resources[ResourceType.BRICK] = 10
    p.resources[ResourceType.SHEEP] = 10
    p.resources[ResourceType.WHEAT] = 10
    p.resources[ResourceType.ORE] = 10
    # find an edge adjacent to player's road/settlement to build road
    built_road = False
    for ek, einfo in g.board.edges.items():
        if einfo["road_owner"] is None:
            # check adjacency
            pts = list(ek)
            ok = False
            for pt in pts:
                vi = g.board.vertices[pt]
                if vi["owner"] == p.id:
                    ok = True
                    break
            if not ok:
                for pt in pts:
                    for ek2, ei2 in g.board.edges.items():
                        if pt in ek2 and ei2["road_owner"] == p.id and ek2 != ek:
                            ok = True
                            break
                    if ok:
                        break
            if ok:
                if g.build_road_at(ek):
                    built_road = True
                    break
    print("built road:", built_road)
    assert built_road

if __name__ == "__main__":
    test_give_resources_and_build()
    print("BUILD OK")
