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
    print("\nRULES TEST OK")
