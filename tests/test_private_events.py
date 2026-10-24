# tests/test_private_events.py
# Private events: text that only ONE player may see (which resource was stolen,
# which dev card was drawn, how many cards a monopoly took from them). It must
# never reach other players, spectators or the monitor.
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_core
from app_core import serialize, DEBUG_VIEW, SPECTATOR_VIEW
from game.game import Game, PHASE_MAIN
from game.cards import DevCardType
from game.resources import ResourceType as R

def check(cond, msg):
    if not cond:
        print("FAIL:", msg); sys.exit(1)
    print("ok:", msg)

def new_game():
    g = Game(num_players=4, seed=7, names=["A", "B", "C", "D"])
    g.phase = PHASE_MAIN
    return g

def settle_on(g, hex_, pid):
    """Put a settlement of `pid` on a corner of hex_ (the victim of a robber move)."""
    v = g.board.vertices_of_hex(*hex_)[0]
    g.board.vertices[v]["building"] = "settlement"
    g.board.vertices[v]["owner"] = pid

def other_hex(g):
    return next(k for k, h in g.board.hexes.items() if k != g.board.robber_hex)

def texts(g, pid):
    return [e["text"] for e in g.private_events if e["to"] == pid]

def view_json(g, viewer):
    return json.dumps(serialize(g, viewer), ensure_ascii=False)

# ---------- steal via the 7's robber ----------
def test_robber_steal():
    g = new_game()
    hx = other_hex(g)
    settle_on(g, hx, 1)
    g.players[1].resources = {r: 0 for r in R if r != R.DESERT}
    g.players[1].resources[R.WOOD] = 3
    g.robber_pending = True
    pub_before = len(g.events)
    check(g.move_robber_and_steal(hx, 1), "P0 moves the robber and steals from P1")
    check(texts(g, 0) == ["Bから 木 を1枚奪いました"], "thief is told what was taken: %r" % texts(g, 0))
    check(texts(g, 1) == ["Aに盗賊で 木 を1枚取られました"], "victim is told what was taken: %r" % texts(g, 1))
    check(texts(g, 2) == [] and texts(g, 3) == [], "nobody else gets a private event")
    pub = [e["text"] for e in g.events[pub_before:]]
    check(len(pub) == 1 and "木" not in pub[0], "the public log line has no resource name: %r" % pub)

def test_robber_no_cards_no_private_event():
    g = new_game()
    hx = other_hex(g)
    settle_on(g, hx, 1)
    g.players[1].resources = {r: 0 for r in R if r != R.DESERT}
    g.robber_pending = True
    check(g.move_robber_and_steal(hx, 1), "robber moves; the victim has no cards")
    check(g.private_events == [], "nothing was stolen -> no private event")

# ---------- steal via a Knight ----------
def test_knight_steal():
    g = new_game()
    hx = other_hex(g)
    settle_on(g, hx, 2)
    g.players[2].resources = {r: 0 for r in R if r != R.DESERT}
    g.players[2].resources[R.ORE] = 2
    g.players[0].dev_cards = [DevCardType.KNIGHT.value]
    check(g.play_dev_card(DevCardType.KNIGHT.value, hex=hx, victim=2), "P0 plays a Knight on P2")
    check(texts(g, 0) == ["Cから 鉄 を1枚奪いました"], "knight thief is told: %r" % texts(g, 0))
    check(texts(g, 2) == ["Aに盗賊で 鉄 を1枚取られました"], "knight victim is told: %r" % texts(g, 2))
    check(texts(g, 1) == [] and texts(g, 3) == [], "nobody else gets a private event")

# ---------- buying a development card ----------
def test_buy_dev_card():
    names = {DevCardType.MONOPOLY: "独占", DevCardType.KNIGHT: "騎士",
             DevCardType.ROAD_BUILDING: "街道建設", DevCardType.YEAR_OF_PLENTY: "収穫"}
    for card, ja in names.items():
        g = new_game()
        p = g.players[0]
        p.resources[R.SHEEP] = p.resources[R.WHEAT] = p.resources[R.ORE] = 1
        g.dev_deck = [card]
        check(g.buy_dev_card_action() == card.value, "P0 buys %s" % ja)
        check(texts(g, 0) == ["発展カード『%s』を引きました(今ターンは使えません)" % ja],
              "buyer sees the card name: %r" % texts(g, 0))
        check(all(texts(g, i) == [] for i in (1, 2, 3)), "%s: nobody else sees it" % ja)
    g = new_game()
    p = g.players[0]
    p.resources[R.SHEEP] = p.resources[R.WHEAT] = p.resources[R.ORE] = 1
    g.dev_deck = [DevCardType.VICTORY_POINT]
    g.buy_dev_card_action()
    check(texts(g, 0) == ["発展カード『勝利点』を引きました(隠し持ちになります)"],
          "victory point card has its own wording: %r" % texts(g, 0))
    check(all(texts(g, i) == [] for i in (1, 2, 3)), "victory point: nobody else sees it")

# ---------- Monopoly ----------
def test_monopoly():
    g = new_game()
    for p in g.players:
        p.resources = {r: 0 for r in R if r != R.DESERT}
    g.players[1].resources[R.WOOD] = 3
    g.players[2].resources[R.WOOD] = 2
    g.players[3].resources[R.BRICK] = 4          # has no wood
    g.players[0].dev_cards = [DevCardType.MONOPOLY.value]
    pub_before = len(g.events)
    check(g.play_dev_card(DevCardType.MONOPOLY.value, resource="wood"), "P0 plays Monopoly on wood")
    check(texts(g, 1) == ["Aの独占で 木 を3枚取られました"], "P1 sees their own count: %r" % texts(g, 1))
    check(texts(g, 2) == ["Aの独占で 木 を2枚取られました"], "P2 sees their own count: %r" % texts(g, 2))
    check(texts(g, 3) == [], "P3 (had none) gets nothing")
    check(texts(g, 0) == ["独占で 木 を合計5枚獲得しました"], "the player sees the total: %r" % texts(g, 0))

def test_monopoly_nobody_has_it():
    g = new_game()
    for p in g.players:
        p.resources = {r: 0 for r in R if r != R.DESERT}
    g.players[0].dev_cards = [DevCardType.MONOPOLY.value]
    check(g.play_dev_card(DevCardType.MONOPOLY.value, resource="ore"), "P0 plays Monopoly on ore")
    check(texts(g, 0) == ["独占で 鉄 は誰も持っていませんでした"], "total 0 is still reported: %r" % texts(g, 0))
    check(all(texts(g, i) == [] for i in (1, 2, 3)), "nobody else gets anything")

# ---------- bookkeeping ----------
def test_ids_and_limit():
    g = new_game()
    g.add_event("public", "info")
    a = g.add_private_event(0, "x", "info")
    b = g.add_private_event(1, "y", "info")
    check(b["id"] == a["id"] + 1 and a["to"] == 0 and set(a) == {"id", "to", "text", "kind"},
          "private events have their own counter and the agreed shape")
    for i in range(50):
        g.add_private_event(0, "n%d" % i, "info")
    check(len(g.private_events) == 30, "only the latest 30 are kept")
    check(g.private_events[-1]["text"] == "n49", "the newest is kept")

# ---------- nothing leaks through serialize ----------
def test_serialize_does_not_leak():
    g = new_game()
    hx = other_hex(g)
    settle_on(g, hx, 1)
    for p in g.players:
        p.resources = {r: 0 for r in R if r != R.DESERT}
    g.players[1].resources[R.WOOD] = 3
    g.players[2].resources[R.WOOD] = 5
    g.robber_pending = True
    g.move_robber_and_steal(hx, 1)
    g.players[0].resources[R.SHEEP] = g.players[0].resources[R.WHEAT] = g.players[0].resources[R.ORE] = 1
    g.dev_deck = [DevCardType.MONOPOLY]
    g.buy_dev_card_action()
    g.players[0].dev_cards = [DevCardType.MONOPOLY.value]
    g.play_dev_card(DevCardType.MONOPOLY.value, resource="wood")
    check(len(g.private_events) >= 4, "several private events exist (%d)" % len(g.private_events))

    # each player gets exactly their own, and only their own
    for pid in range(4):
        mine = serialize(g, pid)["private_events"]
        check(all(e["to"] == pid for e in mine), "P%d's view holds only events addressed to P%d" % (pid, pid))
        check([e["text"] for e in mine] == texts(g, pid), "P%d gets all of their own events" % pid)
    # the monitor, spectators and unidentified viewers get none
    for viewer, label in ((DEBUG_VIEW, "monitor"), (SPECTATOR_VIEW, "spectator"), (None, "no viewer")):
        check(serialize(g, viewer)["private_events"] == [], "%s view: private_events is empty" % label)
    # and the text itself appears nowhere else in what other viewers receive
    secrets = [e["text"] for e in g.private_events]
    for viewer, label in ((DEBUG_VIEW, "monitor"), (SPECTATOR_VIEW, "spectator"), (None, "no viewer")):
        blob = view_json(g, viewer)
        check(not any(t in blob for t in secrets), "%s payload contains no private text" % label)
    for pid in range(4):
        blob = view_json(g, pid)
        own = set(texts(g, pid))
        others = [e["text"] for e in g.private_events if e["to"] != pid and e["text"] not in own]
        check(not any(t in blob for t in others), "P%d payload contains nobody else's private text" % pid)
    # the public log carries no per-player resource info from these actions
    pub = " ".join(e["text"] for e in g.events if e["kind"] in ("robber", "knight"))
    check("を3枚" not in pub and "取られ" not in pub, "public robber log has no private detail")

if __name__ == "__main__":
    test_robber_steal()
    test_robber_no_cards_no_private_event()
    test_knight_steal()
    test_buy_dev_card()
    test_monopoly()
    test_monopoly_nobody_has_it()
    test_ids_and_limit()
    test_serialize_does_not_leak()
    print("\nPRIVATE EVENTS TEST OK")
