# tests/test_rules.py
# Regression tests for bank-supply limits, the same-resource bank-trade ban,
# and the robber's "must move to a different hex" rule.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game import Game, PHASE_MAIN, PHASE_ROLL
from game.resources import ResourceType as R, ROAD_COST

def check(cond, msg):
    if not cond:
        print("FAIL:", msg); sys.exit(1)
    print("ok:", msg)

def new_main_game(seed=7, n=4):
    g = Game(num_players=n, seed=seed)
    g.phase = PHASE_MAIN
    return g

# ---------- 1. same-resource bank trade is forbidden ----------
def test_same_resource_bank_trade():
    g = new_main_game()
    p = g.current_player()
    p.resources[R.WOOD] = 10
    before = p.resources[R.WOOD]
    check(g.trade_bank(R.WOOD, R.WOOD) is False, "wood->wood bank trade rejected")
    check(p.resources[R.WOOD] == before, "wood unchanged after rejected same trade")
    check(g.trade_bank(R.ORE, R.ORE) is False, "ore->ore bank trade rejected")
    # a legitimate different-resource trade still works
    check(g.trade_bank(R.WOOD, R.ORE) is True, "wood->ore bank trade allowed")

# ---------- 2. bank supply: production is all-or-nothing ----------
def test_bank_supply_all_or_nothing():
    g = new_main_game()
    b = g.board
    # find a numbered, non-desert hex
    hex_ = next(h for h in b.hexes.values() if h.number is not None)
    verts = b.vertices_of_hex(hex_.q, hex_.r)
    # place two settlements on this hex, owned by P0 and P1
    for i, v in enumerate(verts[:2]):
        b.vertices[v]["building"] = "settlement"
        b.vertices[v]["owner"] = i
    rt = hex_.resource
    check(rt is not None, "hex has a resource")

    # enough in the bank -> both receive, bank decreases by 2
    g.bank[rt] = 19
    p0b = g.players[0].resources[rt]
    p1b = g.players[1].resources[rt]
    g._distribute_resources(hex_.number)
    check(g.players[0].resources[rt] == p0b + 1, "P0 received 1")
    check(g.players[1].resources[rt] == p1b + 1, "P1 received 1")
    check(g.bank[rt] == 17, "bank decreased by 2")

    # insufficient bank -> nobody receives, bank unchanged
    g.bank[rt] = 1
    p0b = g.players[0].resources[rt]
    p1b = g.players[1].resources[rt]
    g._distribute_resources(hex_.number)
    check(g.players[0].resources[rt] == p0b, "P0 received nothing (bank short)")
    check(g.players[1].resources[rt] == p1b, "P1 received nothing (bank short)")
    check(g.bank[rt] == 1, "bank untouched when short")

# ---------- 3. bank is replenished when resources are spent ----------
def test_bank_replenished_on_build():
    g = new_main_game()
    p = g.current_player()
    # give resources and a valid road spot: settle a vertex then road adjacent
    v = list(g.board.vertices.keys())[0]
    g.board.vertices[v]["building"] = "settlement"
    g.board.vertices[v]["owner"] = p.id
    edge = next(ek for ek in g.board.edges if v in ek)
    p.resources[R.WOOD] = 5
    p.resources[R.BRICK] = 5
    wood_before = g.bank[R.WOOD]
    brick_before = g.bank[R.BRICK]
    check(g.build_road_at(edge) is True, "road built")
    check(g.bank[R.WOOD] == wood_before + 1, "bank regained 1 wood")
    check(g.bank[R.BRICK] == brick_before + 1, "bank regained 1 brick")

# ---------- 4. discards return to the bank ----------
def test_discard_returns_to_bank():
    g = new_main_game()
    p = g.players[0]
    p.resources[R.WOOD] = 10
    g.pending_discards = {0: 5}
    wood_before = g.bank[R.WOOD]
    check(g.discard_cards({"wood": 5}, 0) is True, "discard accepted")
    check(g.bank[R.WOOD] == wood_before + 5, "bank regained 5 wood")

# ---------- 5. robber must move to a different hex ----------
def test_robber_must_move():
    g = new_main_game()
    g.robber_pending = True
    here = g.board.robber_hex
    check(g.move_robber_and_steal(here) is False, "robber cannot stay on the same hex")
    check(g.robber_pending is True, "robber still pending after rejected move")
    other = next((q, r) for (q, r) in g.board.hexes if (q, r) != here)
    check(g.move_robber_and_steal(other) is True, "robber moved to a different hex")
    check(g.robber_pending is False, "robber resolved")

# ---------- 6. setup is a fixed settlement -> road sequence ----------
def test_setup_order_enforced():
    g = Game(num_players=1, seed=5)   # setup_order = [0, 0] (two placements)
    vs = [vv for vv in g.board.vertices if g._distance_rule_ok(vv)]
    v1 = vs[0]
    e1 = next(ek for ek in g.board.edges if v1 in ek)
    # road first is rejected
    check(g.place_setup_road(e1) is False, "setup: road before settlement rejected")
    check(g.place_setup_settlement(v1) is True, "setup: settlement placed")
    # a second settlement in the same step is rejected
    v2 = next(vv for vv in vs if vv != v1 and g._distance_rule_ok(vv))
    check(g.place_setup_settlement(v2) is False, "setup: second settlement in one step rejected")
    # a road adjacent to the just-placed settlement is accepted
    check(g.place_setup_road(e1) is True, "setup: road after settlement accepted")
    # ---- round 2 (same player): a road next to the round-1 settlement must NOT
    #      be accepted before the round-2 settlement is placed ----
    e_adj_round1 = next(ek for ek in g.board.edges if v1 in ek and g.board.edges[ek]["road_owner"] is None)
    check(g.place_setup_road(e_adj_round1) is False, "setup round2: road before settlement rejected")
    check(g.setup_placed_settlement is False, "setup round2: still awaiting the settlement")
    v3 = next(vv for vv in vs
              if vv != v1 and g.board.vertices[vv]["building"] is None and g._distance_rule_ok(vv))
    check(g.place_setup_settlement(v3) is True, "setup round2: settlement placed")
    e3 = next(ek for ek in g.board.edges if v3 in ek and g.board.edges[ek]["road_owner"] is None)
    check(g.place_setup_road(e3) is True, "setup round2: road after settlement accepted")
    check(g.phase == PHASE_ROLL, "setup finished -> roll phase")

def test_knight_before_roll():
    g = Game(num_players=4, seed=3)
    p = g.current_player()
    p.dev_cards.append("knight")           # a playable knight
    g.phase = PHASE_ROLL                   # still before rolling this turn
    here = g.board.robber_hex
    other = next((q, r) for (q, r) in g.board.hexes if (q, r) != here)
    check(g.play_dev_card("knight", hex=other) is True, "knight played before rolling")
    check(g.board.robber_hex == other, "robber moved before rolling")
    check(g.robber_pending is False, "robber resolved before rolling (no deadlock)")

def test_victory_point_card_is_not_playable():
    g = Game(num_players=4, seed=5)
    p = g.current_player()
    p.dev_cards.append("victory_point")
    g.phase = PHASE_MAIN
    hidden_before = p.hidden_vp
    check(g.play_dev_card("victory_point") is False, "victory point card cannot be played")
    check("victory_point" not in p.used_dev_cards, "victory point card is not marked as used")
    check("victory_point" in p.dev_cards, "victory point card stays in hand")
    check(p.hidden_vp == hidden_before, "victory point score unchanged")
    check(p.played_dev_this_turn is False, "the turn is not consumed by a VP card")

def test_stale_trade_offer_does_not_block_new_turn():
    g = Game(num_players=2, seed=11)
    g.phase = PHASE_MAIN
    p = g.current_player()
    p.resources[R.WOOD] = 5
    other = g.players[1]
    other.resources[R.ORE] = 5
    check(g.create_trade_offer({R.WOOD.value: 1}, {R.ORE.value: 1}, [1]) is True,
          "offer created")
    # nobody answers and the player ends the turn
    check(g.end_turn() is True, "turn ended with an open offer")
    check(g.trade_offer is None, "open offer does not survive the turn")
    # the next player rolls and proposes their own trade
    g.phase = PHASE_ROLL
    check(g.roll_dice() is not None, "next player rolls")
    p2 = g.current_player()
    p2.resources[R.WOOD] = 5
    check(g.trade_offer is None, "roll does not inherit the old offer")
    check(g.create_trade_offer({R.WOOD.value: 1}, {R.ORE.value: 1}, [0]) is True,
          "the next player can propose a trade (取引中にならない)")

# ---------- 10. longest road / largest army: re-decided from everyone's value ----------
def _adjacency(g, used):
    adj = {}
    for ek, info in g.board.edges.items():
        if ek in used:
            continue
        a, b = list(ek)
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj

def road_chain(g, n, used):
    """A simple path of n unused edges; returns its vertices (n+1 points)."""
    adj = _adjacency(g, used)
    def dfs(path):
        if len(path) == n + 1:
            return path
        for nb in adj.get(path[-1], []):
            if nb in path:
                continue
            r = dfs(path + [nb])
            if r:
                return r
        return None
    for start in adj:
        r = dfs([start])
        if r:
            return r
    raise AssertionError("no chain of %d edges on this board" % n)

def lay_roads(g, pid, verts, used):
    for a, b in zip(verts, verts[1:]):
        ek = frozenset([a, b])
        g.board.edges[ek]["road_owner"] = pid
        used.add(ek)

def extend_road(g, pid, verts, used, extra_vertex):
    ek = frozenset([verts[-1], extra_vertex])
    g.board.edges[ek]["road_owner"] = pid
    used.add(ek)
    verts.append(extra_vertex)

def road_events(g):
    return [e for e in g.events if e["kind"] == "longest_road"]

def army_events(g):
    return [e for e in g.events if e["kind"] == "largest_army"]

def test_longest_road_vp_not_stacked():
    g = new_main_game()
    used = set()
    chain = road_chain(g, 7, used)
    p0 = g.players[0]
    base = p0.vp
    lay_roads(g, 0, chain[:5], used)       # 4 edges: below the minimum
    g._update_longest_road()
    check(g.longest_road_owner is None and p0.vp == base, "4 roads: no title yet")
    lay_roads(g, 0, chain[4:6], used)      # now 5 edges
    g._update_longest_road()
    check(g.longest_road_owner == 0 and p0.longest_road, "5 roads: P0 takes the title")
    check(p0.vp == base + 2, "5 roads: +2 VP")
    lay_roads(g, 0, chain[5:7], used)      # 6 edges
    g._update_longest_road()
    check(p0.vp == base + 2, "6 roads: VP still +2 (not stacked)")
    lay_roads(g, 0, chain[6:8], used)      # 7 edges
    g._update_longest_road()
    check(p0.vp == base + 2, "7 roads: VP still +2 (not stacked)")
    check(g.longest_road_length == 7, "stored length is the current maximum (7)")
    check(len(road_events(g)) == 1, "the title was announced exactly once")

def test_largest_army_vp_not_stacked():
    g = new_main_game()
    p0 = g.players[0]
    base = p0.vp
    p0.knights_played = 2
    g._update_largest_army()
    check(g.largest_army_owner is None and p0.vp == base, "2 knights: no title yet")
    for n in (3, 4, 5):
        p0.knights_played = n
        g._update_largest_army()
        check(g.largest_army_owner == 0 and p0.largest_army, "%d knights: P0 holds the army" % n)
        check(p0.vp == base + 2, "%d knights: VP stays +2 (not stacked)" % n)
    check(g.largest_army_count == 5, "stored count is the current maximum (5)")
    check(len(army_events(g)) == 1, "the army was announced exactly once")

def test_title_moves_when_overtaken():
    g = new_main_game()
    used = set()
    p0, p1 = g.players[0], g.players[1]
    b0, b1 = p0.vp, p1.vp
    # road: P0 has 5, P1 builds 6
    lay_roads(g, 0, road_chain(g, 5, used), used)
    g._update_longest_road()
    check(p0.vp == b0 + 2 and p0.longest_road, "road: P0 holds it with 5")
    lay_roads(g, 1, road_chain(g, 6, used), used)
    g._update_longest_road()
    check(g.longest_road_owner == 1 and p1.longest_road, "road: P1 overtakes with 6")
    check(not p0.longest_road and p0.vp == b0, "road: P0 loses the title and its 2 VP")
    check(p1.vp == b1 + 2, "road: P1 gains 2 VP")
    # army: P0 has 3, P1 plays 4
    p0.knights_played = 3
    g._update_largest_army()
    check(g.largest_army_owner == 0 and p0.vp == b0 + 2, "army: P0 holds it with 3")
    p1.knights_played = 4
    g._update_largest_army()
    check(g.largest_army_owner == 1 and p1.largest_army, "army: P1 overtakes with 4")
    check(not p0.largest_army and p0.vp == b0, "army: P0 loses the title and its 2 VP")
    check(p1.vp == b1 + 4, "army: P1 now holds both titles (+4)")

def test_tie_keeps_current_owner():
    g = new_main_game()
    used = set()
    p0, p1 = g.players[0], g.players[1]
    b0, b1 = p0.vp, p1.vp
    lay_roads(g, 0, road_chain(g, 5, used), used)
    g._update_longest_road()
    lay_roads(g, 1, road_chain(g, 5, used), used)
    g._update_longest_road()
    check(g.longest_road_owner == 0 and p0.longest_road, "road: a tie does not move the title")
    check(p0.vp == b0 + 2 and p1.vp == b1 and not p1.longest_road, "road: VP unchanged on a tie")
    p0.knights_played = 3
    g._update_largest_army()
    p1.knights_played = 3
    g._update_largest_army()
    check(g.largest_army_owner == 0 and p0.largest_army, "army: a tie does not move the title")
    check(p0.vp == b0 + 4 and p1.vp == b1 and not p1.largest_army, "army: VP unchanged on a tie")

def _cut_at(g, vertex, by_pid):
    """An opponent settlement on `vertex` breaks the road passing through it."""
    g.board.vertices[vertex]["building"] = "settlement"
    g.board.vertices[vertex]["owner"] = by_pid

def test_cut_road_drops_the_title():
    g = new_main_game()
    used = set()
    p0 = g.players[0]
    b0 = p0.vp
    chain = road_chain(g, 5, used)
    lay_roads(g, 0, chain, used)
    g._update_longest_road()
    check(g.longest_road_owner == 0 and p0.vp == b0 + 2, "P0 holds the road with 5")
    _cut_at(g, chain[2], 1)
    g._update_longest_road()
    check(g.longest_road_owner is None and not p0.longest_road, "cut below 5: the title is removed")
    check(p0.vp == b0, "cut below 5: P0 loses the 2 VP")
    check(g.longest_road_length < 5, "stored length reflects the cut")

def test_cut_road_via_build_settlement():
    # the same, but through the real build path (a settlement can cut a road)
    g = new_main_game()
    used = set()
    p0, p1 = g.players[0], g.players[1]
    b0 = p0.vp
    chain = road_chain(g, 5, used)
    lay_roads(g, 0, chain, used)
    g._update_longest_road()
    check(g.longest_road_owner == 0, "P0 holds the road before the cut")
    adj = _adjacency(g, used)
    cut = None
    for v in chain[1:-1]:
        if adj.get(v):            # a free third edge at this vertex for P1's road
            cut = (v, adj[v][0])
            break
    check(cut is not None, "found a vertex where P1 can connect and cut")
    v, other = cut
    g.board.edges[frozenset([v, other])]["road_owner"] = 1
    g.current_player_idx = 1
    for r in (R.WOOD, R.BRICK, R.SHEEP, R.WHEAT):
        p1.resources[r] = 2
    check(g.build_settlement_at(v) is True, "P1 builds the cutting settlement")
    check(g.longest_road_owner is None and not p0.longest_road, "building it removed P0's title")
    check(p0.vp == b0, "P0 lost the 2 VP")

def test_cut_into_a_tie_gives_it_to_nobody():
    g = new_main_game()
    used = set()
    p0, p1, p2 = g.players[0], g.players[1], g.players[2]
    b0, b1, b2 = p0.vp, p1.vp, p2.vp
    c0 = road_chain(g, 6, used)
    lay_roads(g, 0, c0, used)
    lay_roads(g, 1, road_chain(g, 5, used), used)
    lay_roads(g, 2, road_chain(g, 5, used), used)
    g._update_longest_road()
    check(g.longest_road_owner == 0 and p0.vp == b0 + 2, "P0 holds the road with 6")
    check(p1.vp == b1 and p2.vp == b2, "P1/P2 (5 each) have nothing")
    _cut_at(g, c0[3], 3)     # P0 drops to 3; P1 and P2 are tied at 5
    g._update_longest_road()
    check(g.longest_road_owner is None, "tied P1/P2 and P0 no longer in it: nobody holds it")
    check(not (p0.longest_road or p1.longest_road or p2.longest_road), "no player has the flag")
    check(p0.vp == b0 and p1.vp == b1 and p2.vp == b2, "P0 -2, nobody +2")
    check(g.longest_road_length == 5, "stored length is the tied maximum (5)")


if __name__ == "__main__":
    test_same_resource_bank_trade()
    test_bank_supply_all_or_nothing()
    test_bank_replenished_on_build()
    test_discard_returns_to_bank()
    test_robber_must_move()
    test_setup_order_enforced()
    test_knight_before_roll()
    test_victory_point_card_is_not_playable()
    test_stale_trade_offer_does_not_block_new_turn()
    test_longest_road_vp_not_stacked()
    test_largest_army_vp_not_stacked()
    test_title_moves_when_overtaken()
    test_tie_keeps_current_owner()
    test_cut_road_drops_the_title()
    test_cut_road_via_build_settlement()
    test_cut_into_a_tie_gives_it_to_nobody()
    print("\nRULES TEST OK")
