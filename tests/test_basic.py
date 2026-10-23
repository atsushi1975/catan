# tests/test_basic.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import Board
from game.game import Game
from game.resources import ResourceType, TerrainType

def test_board_creation():
    b = Board(seed=42)
    assert len(b.hexes) == 19
    assert len(b.vertices) > 0
    assert len(b.edges) > 0
    print("board ok", b)

def test_game_setup_flow():
    g = Game(num_players=4, seed=1)
    assert g.phase == "setup"
    # place 8 settlements + 8 roads total
    # first player places settlement
    # find a valid vertex
    b = g.board
    # pick first vertex
    v = list(b.vertices.keys())[0]
    # ensure distance rule: just try
    # We'll place via setup: need vertex with no adjacent settlements
    placed = 0
    attempts = 0
    idx = 0
    verts = list(b.vertices.keys())
    while placed < 8 and attempts < 1000:
        attempts += 1
        vi = g.setup_order[g.setup_index] if g.setup_index < len(g.setup_order) else None
        # get current player
        p = g.current_player()
        # find a vertex not adjacent to any settlement
        candidate = None
        for v in verts:
            info = b.vertices[v]
            if info["building"] is not None:
                continue
            # distance rule
            ok = True
            for adj in b.adjacent_vertices(v):
                if b.vertices[adj]["building"] is not None:
                    ok = False
                    break
            if ok:
                candidate = v
                break
        if candidate is None:
            print("no candidate")
            break
        ok = g.place_setup_settlement(candidate)
        if not ok:
            print("settle fail", candidate)
            break
        # place road adjacent
        # find edge containing candidate
        road_edge = None
        for ek in b.edges:
            if candidate in ek:
                if b.edges[ek]["road_owner"] is None:
                    road_edge = ek
                    break
        ok = g.place_setup_road(road_edge)
        if not ok:
            print("road fail")
            break
        placed += 1
    print("placed", placed, "phase", g.phase)
    assert g.phase in ("setup", "roll")
    print("setup flow ok")

def test_roll_and_distribute():
    g = Game(num_players=4, seed=2)
    # quick setup using helper
    _auto_setup(g)
    assert g.phase == "roll"
    total = g.roll_dice()
    print("rolled", total)
    assert g.phase == "main"
    print("roll ok")

def _auto_setup(g):
    b = g.board
    verts = list(b.vertices.keys())
    placed = 0
    while g.phase == "setup" and placed < 16:
        # find valid vertex
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

def test_ports_one_of_each():
    """Every board must offer all five 2:1 ports (and four 3:1 ones).

    Regression: the old alternating rule dropped one resource whenever the
    pattern started on an odd slot, so a board could have no brick port.
    """
    want = sorted(r.value for r in ResourceType if r is not ResourceType.DESERT)
    for seed in range(200):
        b = Board(seed=seed)
        types = [pt if isinstance(pt, str) else pt.value for _, pt in b.port_edges]
        assert len(types) == 9, (seed, types)
        specific = sorted(t for t in types if t != "generic")
        assert specific == want, (seed, specific)
        assert types.count("generic") == 4, (seed, types)
    print("port layout ok")

if __name__ == "__main__":
    test_board_creation()
    test_game_setup_flow()
    test_roll_and_distribute()
    test_ports_one_of_each()
    print("ALL OK")
