# tests/test_trade_events.py
# Player-to-player trade notifications. Each notification is private (only the
# player it concerns sees it) and maps to a toast kind on the client:
# trade_offer / trade_ok / trade_fail.
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_core
from app_core import serialize
from game.game import Game, PHASE_MAIN
from game.resources import ResourceType as R

def check(cond, msg):
    if not cond:
        print("FAIL:", msg); sys.exit(1)
    print("ok:", msg)

def new_game():
    g = Game(num_players=4, seed=7, names=["A", "B", "C", "D"])
    g.phase = PHASE_MAIN
    g.current_player_idx = 0
    for p in g.players:
        p.resources = {r: 0 for r in R if r != R.DESERT}
    g.players[0].resources[R.WOOD] = 5
    for pid in (1, 2, 3):
        g.players[pid].resources[R.ORE] = 5
    return g

def offer(g, targets):
    return g.create_trade_offer({R.WOOD.value: 1}, {R.ORE.value: 1}, targets)

def texts(g, pid):
    return [e["text"] for e in g.private_events if e["to"] == pid]

def kinds(g, pid):
    return [e["kind"] for e in g.private_events if e["to"] == pid]

def counts(g):
    return {pid: len(texts(g, pid)) for pid in range(4)}

# ---------- 1. an offer reaches only its targets (not the proposer) ----------
def test_offer_notifies_targets_only():
    g = new_game()
    pub_before = len(g.events)
    check(offer(g, [1, 2]) is True, "A opens an offer to B and C")
    check(texts(g, 1) == ["Aから交易の依頼が届きました"], "B is told about the offer")
    check(texts(g, 2) == ["Aから交易の依頼が届きました"], "C is told about the offer")
    check(kinds(g, 1) == ["trade_offer"] and kinds(g, 2) == ["trade_offer"],
          "the offer notifications use kind=trade_offer")
    check(texts(g, 0) == [], "the proposer A is not notified")
    check(texts(g, 3) == [], "D (not a target) is not notified")
    check(len(g.events) == pub_before, "the offer adds nothing to the public log")

# ---------- 2. accepting notifies both sides; a single decline is silent ----------
def test_accept_notifications():
    g = new_game()
    check(offer(g, [1, 2, 3]) is True, "A opens an offer to B, C and D")
    before = counts(g)
    check(g.respond_trade(3, False) is True, "D declines")
    check(counts(g) == before, "a single decline produces no notification")
    check(g.respond_trade(1, True) is True, "B accepts")
    check(texts(g, 0)[-1] == "Bと交易が成立しました", "A is told who accepted: %r" % texts(g, 0))
    check(kinds(g, 0)[-1] == "trade_ok", "A's success toast is kind=trade_ok")
    check(texts(g, 1) == ["Aから交易の依頼が届きました", "Aと交易が成立しました"],
          "B sees the offer and the success: %r" % texts(g, 1))
    check(kinds(g, 1)[-1] == "trade_ok", "B's success toast is kind=trade_ok")
    check(texts(g, 2) == ["Aから交易の依頼が届きました", "交易は不成立（別の人と成立）"],
          "C (still open) is told it went to someone else: %r" % texts(g, 2))
    check(kinds(g, 2)[-1] == "trade_fail", "C's toast is kind=trade_fail")
    check(texts(g, 3) == ["Aから交易の依頼が届きました"],
          "D, who had already declined, gets no failure notice: %r" % texts(g, 3))
    check(g.trade_offer is None, "the offer is cleared after a successful trade")
    check(g.players[0].resources[R.WOOD] == 4 and g.players[0].resources[R.ORE] == 1
          and g.players[1].resources[R.WOOD] == 1 and g.players[1].resources[R.ORE] == 4,
          "resources were exchanged")

# ---------- 3. cancelling: proposer + still-open targets, not prior decliners ----------
def test_cancel_notifications():
    g = new_game()
    check(offer(g, [1, 2, 3]) is True, "A opens an offer to B, C and D")
    check(g.respond_trade(3, False) is True, "D declines first")
    check(g.cancel_trade_offer(0) is True, "A withdraws the offer")
    check(texts(g, 0)[-1] == "交易は不成立（自分がキャンセル）",
          "A is told about their own cancellation: %r" % texts(g, 0))
    check(kinds(g, 0)[-1] == "trade_fail", "A's toast is kind=trade_fail")
    check(texts(g, 1)[-1] == "交易は不成立（相手がキャンセル）",
          "B (still open) is told the proposer cancelled: %r" % texts(g, 1))
    check(texts(g, 2)[-1] == "交易は不成立（相手がキャンセル）",
          "C (still open) is told the proposer cancelled: %r" % texts(g, 2))
    check(kinds(g, 1)[-1] == "trade_fail" and kinds(g, 2)[-1] == "trade_fail",
          "cancel toasts are kind=trade_fail")
    check(texts(g, 3) == ["Aから交易の依頼が届きました"],
          "D, who had declined, gets no cancel notice: %r" % texts(g, 3))
    check(g.trade_offer is None, "the offer is cleared after a cancellation")

# ---------- 4. everyone declined: only the proposer is told ----------
def test_all_declined_notification():
    g = new_game()
    check(offer(g, [1, 2, 3]) is True, "A opens an offer to B, C and D")
    check(g.respond_trade(1, False) is True, "B declines")
    check(g.respond_trade(2, False) is True, "C declines")
    check(texts(g, 0) == [], "no notification while someone could still accept")
    check(g.respond_trade(3, False) is True, "D declines (the last one)")
    check(texts(g, 0) == ["交易は不成立（全員が断った）"],
          "A is told everyone declined: %r" % texts(g, 0))
    check(kinds(g, 0) == ["trade_fail"], "the toast is kind=trade_fail")
    check(g.trade_offer is None, "the offer is cleared when everyone declined")

# ---------- 5. failed responses add no notification ----------
def test_failed_response_notifies_nobody():
    g = new_game()
    g.players[1].resources[R.ORE] = 0  # B cannot pay what A wants
    check(offer(g, [1]) is True, "A opens an offer to B")
    before = counts(g)
    check(g.respond_trade(1, True) is False, "B cannot afford it -> respond fails")
    check(counts(g) == before, "a failed accept adds no notification")
    check(g.trade_offer is not None, "the offer stays open after a failed accept")

    g2 = new_game()
    check(offer(g2, [1]) is True, "A opens an offer to B")
    g2.players[0].resources[R.WOOD] = 0  # A no longer has the goods
    before2 = counts(g2)
    check(g2.respond_trade(1, True) is False, "A no longer has the goods -> respond fails")
    check(counts(g2) == before2, "the internal cancellation adds no notification")
    check(g2.trade_offer is None, "the offer is cleared internally")

# ---------- 6. the offer notification is private ----------
def test_offer_notification_is_private():
    g = new_game()
    check(offer(g, [1]) is True, "A opens an offer to B only")
    msg = "Aから交易の依頼が届きました"
    for viewer in (0, 2, 3):
        blob = json.dumps(serialize(g, viewer), ensure_ascii=False)
        check(msg not in blob, "viewer %d cannot see B's offer notification" % viewer)
    blob_b = json.dumps(serialize(g, 1), ensure_ascii=False)
    check(msg in blob_b, "B sees the offer notification")
    check(serialize(g, 1)["private_events"] == [e for e in g.private_events if e["to"] == 1],
          "B's payload holds exactly B's private events")

if __name__ == "__main__":
    test_offer_notifies_targets_only()
    test_accept_notifications()
    test_cancel_notifications()
    test_all_declined_notification()
    test_failed_response_notifies_nobody()
    test_offer_notification_is_private()
    print("\nTRADE EVENTS TEST OK")
