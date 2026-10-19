# game/game.py
import random
from .board import Board
from .player import Player
from .resources import (ResourceType, TerrainType, TERRAIN_TO_RESOURCE,
                        ROAD_COST, SETTLEMENT_COST, CITY_COST, DEV_CARD_COST,
                        VP_SETTLEMENT, VP_CITY, VP_LARGEST_ARMY,
                        VP_LONGEST_ROAD, VICTORY_TARGET)
from .cards import (create_dev_deck, draw_dev_card, DevCardType)
from .trade import bank_trade

PHASE_SETUP = "setup"
PHASE_ROLL = "roll"
PHASE_MAIN = "main"
PHASE_END = "end"

class Game:
    COLORS = ["red", "blue", "white", "orange"]

    def __init__(self, num_players=4, seed=None, names=None):
        self.seed = seed
        self.rng = random.Random(seed)
        self.board = Board(seed=seed)
        self.players = [
            Player(i, (names[i] if names and i < len(names) and names[i] else f"プレイヤー{i+1}"), self.COLORS[i])
            for i in range(num_players)
        ]
        self.num_players = num_players
        self.dev_deck = create_dev_deck(seed=seed)
        # Bank supply: 19 cards of each resource. Production is all-or-nothing
        # per resource when the bank cannot cover the total demand.
        self.bank = {rt: 19 for rt in ResourceType if rt != ResourceType.DESERT}
        # setup phase: each player places 2 settlements + 2 roads
        self.phase = PHASE_SETUP
        self.setup_round = 0  # 0 = first settlement, 1 = second
        self.setup_index = 0  # which player is placing
        self.setup_order = list(range(num_players)) + list(range(num_players - 1, -1, -1))
        # Enforce the fixed order settlement -> road within each setup step.
        self.setup_placed_settlement = False  # has the current player placed this step's settlement?
        self.setup_last_vertex = None         # the settlement vertex placed this step
        self.current_player_idx = self.setup_order[0]
        self.turn_number = 0
        self.dice = (0, 0)
        self.winner = None
        # 7-handling state
        self.robber_pending = False      # current player must move the robber
        self.pending_discards = {}       # player_id -> cards to discard
        self.last_roll_rerolled = False  # True when a first-round 7 was re-rolled
        # player-to-player trade offer (proposal -> accept).
        # {"from": pid, "give": {ResourceType: n}, "want": {ResourceType: n},
        #  "targets": [pid, ...], "declined": [pid, ...]}
        self.trade_offer = None
        # longest road / largest army tracking
        self.longest_road_owner = None
        self.longest_road_length = 4  # minimum 5 roads to qualify (length edges)
        self.largest_army_owner = None
        self.largest_army_count = 2  # minimum 3 knights

    def current_player(self):
        return self.players[self.current_player_idx]

    # ---------- Bank supply ----------
    def _bank_take(self, rt, n):
        """Remove up to n of `rt` from the bank; return the amount taken."""
        avail = self.bank.get(rt, 0)
        take = min(avail, n)
        if take > 0:
            self.bank[rt] = avail - take
        return take

    def _bank_put(self, rt, n):
        if n > 0:
            self.bank[rt] = self.bank.get(rt, 0) + n

    def _bank_put_cost(self, cost):
        """Return a building/development cost to the bank."""
        for rt, n in cost.items():
            self._bank_put(rt, n)

    # ---------- Setup placement ----------
    def place_setup_settlement(self, vertex):
        """Place a settlement during setup. Returns bool."""
        if self.phase != PHASE_SETUP:
            return False
        # fixed order: the settlement of this step must come before its road
        if self.setup_placed_settlement:
            return False
        p = self.current_player()
        vinfo = self.board.vertices.get(vertex)
        if vinfo is None:
            return False
        if vinfo["building"] is not None:
            return False
        if not self._valid_settlement_spot(vertex, p):
            return False
        # distance rule: no adjacent settlements
        if not self._distance_rule_ok(vertex):
            return False
        vinfo["building"] = "settlement"
        vinfo["owner"] = p.id
        p.settlements_left -= 1
        p.vp += VP_SETTLEMENT
        # grant resources on second placement
        if self.setup_round == 1:
            for hq in vinfo["hexes"]:
                h = self.board.hexes[hq]
                if h.resource is not None:
                    if self._bank_take(h.resource, 1):
                        p.gain(h.resource)
        self.setup_placed_settlement = True
        self.setup_last_vertex = vertex
        return True

    def place_setup_road(self, edge):
        """Place a road adjacent to the settlement placed in this setup step."""
        if self.phase != PHASE_SETUP:
            return False
        # fixed order: the settlement of this step must be placed first
        if not self.setup_placed_settlement:
            return False
        p = self.current_player()
        einfo = self.board.edges.get(edge)
        if einfo is None:
            return False
        if einfo["road_owner"] is not None:
            return False
        # road must be adjacent to the settlement placed in THIS step
        if self.setup_last_vertex not in edge:
            return False
        einfo["road_owner"] = p.id
        p.roads_left -= 1
        # advance setup
        self.setup_placed_settlement = False
        self.setup_last_vertex = None
        self._advance_setup()
        return True

    def _advance_setup(self):
        self.setup_index += 1
        self.setup_placed_settlement = False
        self.setup_last_vertex = None
        if self.setup_index >= len(self.setup_order):
            self.phase = PHASE_ROLL
            self.current_player_idx = 0
            self.setup_index = 0
            return
        # determine round: first half = round 0, second half = round 1
        half = len(self.setup_order) // 2
        if self.setup_index < half:
            self.setup_round = 0
        else:
            self.setup_round = 1
        self.current_player_idx = self.setup_order[self.setup_index]

    # ---------- Turn flow ----------
    def roll_dice(self):
        if self.phase != PHASE_ROLL:
            return None
        if self._seven_unresolved():
            return None
        # A new turn's roll must never inherit an open player-trade offer.
        self.trade_offer = None
        self.last_roll_rerolled = False
        d1 = self.rng.randint(1, 6)
        d2 = self.rng.randint(1, 6)
        total = d1 + d2
        # First round (each player's first turn): a 7 has no effect,
        # the dice are re-rolled.
        while total == 7 and self.turn_number < self.num_players:
            self.last_roll_rerolled = True
            d1 = self.rng.randint(1, 6)
            d2 = self.rng.randint(1, 6)
            total = d1 + d2
        self.dice = (d1, d2)
        if total == 7:
            self._handle_seven()
        else:
            self._distribute_resources(total)
        self.phase = PHASE_MAIN
        return total

    def _distribute_resources(self, number):
        # Official rule: for each resource produced by this roll, either every
        # entitled player receives it, or (if the bank cannot cover the total)
        # nobody receives that resource.
        needed = {}   # ResourceType -> total cards required
        claims = {}   # player_id -> {ResourceType: amount}
        for h in self.board.hexes.values():
            if h.number != number or h.has_robber:
                continue
            rt = h.resource
            if rt is None:
                continue
            for vpt in self.board.vertices_of_hex(h.q, h.r):
                vi = self.board.vertices[vpt]
                if vi["owner"] is None or vi["building"] is None:
                    continue
                amt = 1 if vi["building"] == "settlement" else 2
                needed[rt] = needed.get(rt, 0) + amt
                claims.setdefault(vi["owner"], {}).setdefault(rt, 0)
                claims[vi["owner"]][rt] += amt
        for rt, total in needed.items():
            if self.bank.get(rt, 0) < total:
                continue  # bank short -> nobody gets this resource
            for pid, gained in claims.items():
                if rt in gained:
                    self.players[pid].gain(rt, gained[rt])
            self._bank_take(rt, total)

    def _handle_seven(self):
        # Rule order: 1) players with >7 cards discard half (rounded down)
        # of their CHOICE, 2) the active player moves the robber and steals.
        # Discards are collected via discard_cards(); the robber cannot be
        # moved until all pending discards are resolved.
        self.pending_discards = {}
        for p in self.players:
            n = p.total_resources()
            if n > 7:
                self.pending_discards[p.id] = n // 2
        self.robber_pending = True

    def discard_cards(self, resources, player_id=None):
        """A player discards the chosen cards for the pending discard.

        `resources` maps resource name -> count.  The total must equal the
        pending discard count for the given player (defaults to the current
        player).  Hot-seat: any player with a pending discard may submit.
        """
        pid = self.current_player_idx if player_id is None else int(player_id)
        need = self.pending_discards.get(pid)
        if need is None:
            return False
        total = 0
        for k, v in resources.items():
            v = int(v)
            if v < 0:
                return False
            rt = ResourceType(k)
            if self.players[pid].resources.get(rt, 0) < v:
                return False
            total += v
        if total != need:
            return False
        p = self.players[pid]
        for k, v in resources.items():
            p.resources[ResourceType(k)] -= int(v)
            self._bank_put(ResourceType(k), int(v))  # discards return to the bank
        del self.pending_discards[pid]
        return True

    def has_pending_discards(self):
        return bool(self.pending_discards)

    def possible_robber_victims(self, hex_coord):
        q, r = hex_coord
        vpts = self.board.vertices_of_hex(q, r)
        victims = set()
        for vpt in vpts:
            vi = self.board.vertices.get(vpt)
            if vi and vi["owner"] is not None and vi["owner"] != self.current_player_idx:
                victims.add(vi["owner"])
        return list(victims)

    def move_robber_and_steal(self, hex_coord, victim_id=None):
        # A Knight may be played before rolling (PHASE_ROLL) or after (PHASE_MAIN).
        if self.phase not in (PHASE_ROLL, PHASE_MAIN):
            return False
        if not self.robber_pending:
            return False
        if self.pending_discards:
            return False  # discards must be resolved first
        q, r = hex_coord
        h = self.board.hexes.get((q, r))
        if h is None:
            return False
        if (q, r) == self.board.robber_hex:
            return False  # the robber must move to a different hex
        if victim_id is not None:
            if victim_id not in self.possible_robber_victims(hex_coord):
                return False
        self.board.move_robber(q, r)
        self.robber_pending = False
        # steal one random resource from the chosen victim
        if victim_id is not None:
            victim = self.players[victim_id]
            thief = self.current_player()
            avail = [rt for rt, amt in victim.resources.items() if amt > 0]
            if avail:
                rt = self.rng.choice(avail)
                victim.resources[rt] -= 1
                thief.resources[rt] += 1
        return True

    # ---------- Building ----------
    def _seven_unresolved(self):
        """True while a rolled/played 7 is not yet fully resolved."""
        return self.robber_pending or bool(self.pending_discards)

    def build_road_at(self, edge):
        if self.phase != PHASE_MAIN:
            return False
        if self._seven_unresolved():
            return False
        p = self.current_player()
        einfo = self.board.edges.get(edge)
        if einfo is None or einfo["road_owner"] is not None:
            return False
        if not self._road_adjacent_to_player(edge, p.id):
            return False
        if p.free_roads > 0:
            if p.roads_left <= 0:
                return False
            p.roads_left -= 1
            p.free_roads -= 1
        else:
            if not p.build_road():
                return False
            self._bank_put_cost(ROAD_COST)
        einfo["road_owner"] = p.id
        self._update_longest_road()
        return True

    def _road_adjacent_to_player(self, edge, pid):
        pts = list(edge)
        for pt in pts:
            vi = self.board.vertices.get(pt)
            # connect to own settlement/city
            if vi is not None and vi["owner"] == pid and vi["building"] in ("settlement", "city"):
                return True
            # connect to own road, unless this vertex is now blocked by opponent building
            if vi is not None and vi["owner"] is not None and vi["owner"] != pid and vi["building"] in ("settlement", "city"):
                continue
        # adjacent own road sharing a non-blocked vertex
        for pt in pts:
            vi = self.board.vertices.get(pt)
            if vi is not None and vi["owner"] is not None and vi["owner"] != pid and vi["building"] in ("settlement", "city"):
                continue  # blocked vertex
            for ek, einfo in self.board.edges.items():
                if ek == edge:
                    continue
                if einfo["road_owner"] == pid and pt in ek:
                    return True
        return False

    def build_settlement_at(self, vertex):
        if self.phase != PHASE_MAIN:
            return False
        if self._seven_unresolved():
            return False
        p = self.current_player()
        vinfo = self.board.vertices.get(vertex)
        if vinfo is None or vinfo["building"] is not None:
            return False
        if not self._distance_rule_ok(vertex):
            return False
        if not self._settlement_adjacent_to_player_road(vertex, p.id):
            return False
        if not p.build_settlement():
            return False
        self._bank_put_cost(SETTLEMENT_COST)
        vinfo["building"] = "settlement"
        vinfo["owner"] = p.id
        self._check_win()
        return True

    def _settlement_adjacent_to_player_road(self, vertex, pid):
        # vertex must be endpoint of a road owned by pid (or first build? no, main phase needs road)
        for ek, einfo in self.board.edges.items():
            if vertex in ek and einfo["road_owner"] == pid:
                return True
        return False

    def build_city_at(self, vertex):
        if self.phase != PHASE_MAIN:
            return False
        if self._seven_unresolved():
            return False
        p = self.current_player()
        vinfo = self.board.vertices.get(vertex)
        if vinfo is None or vinfo["building"] != "settlement" or vinfo["owner"] != p.id:
            return False
        if not p.build_city():
            return False
        self._bank_put_cost(CITY_COST)
        vinfo["building"] = "city"
        self._check_win()
        return True

    def buy_dev_card_action(self):
        if self.phase != PHASE_MAIN:
            return None
        if self._seven_unresolved():
            return None
        p = self.current_player()
        if not p.buy_dev_card():
            return None
        card = draw_dev_card(self.dev_deck)
        if card is None:
            # refund (bank is untouched because the cost is returned only on success)
            p.resources[ResourceType.SHEEP] += 1
            p.resources[ResourceType.WHEAT] += 1
            p.resources[ResourceType.ORE] += 1
            return None
        self._bank_put_cost(DEV_CARD_COST)
        p.new_dev_cards.append(card.value)
        # VP cards count immediately
        if card == DevCardType.VICTORY_POINT:
            p.hidden_vp += 1
            self._check_win()
        return card.value

    def play_dev_card(self, card_type, **kwargs):
        if self.phase not in (PHASE_ROLL, PHASE_MAIN):
            return False
        if self._seven_unresolved():
            return False
        p = self.current_player()
        if p.played_dev_this_turn:
            return False
        # A victory point card is never "played" - it only counts towards the
        # final score (it must not end up in the used-cards list either).
        if card_type == DevCardType.VICTORY_POINT.value:
            return False
        # card must be in hand (not new this turn)
        if card_type not in p.dev_cards:
            return False
        p.dev_cards.remove(card_type)
        p.used_dev_cards.append(card_type)  # public: opponents see which cards were played
        p.played_dev_this_turn = True
        if card_type == DevCardType.KNIGHT.value:
            p.knights_played += 1
            # knight always requires moving the robber
            self.robber_pending = True
            self.trade_offer = None  # any open offer is void once the robber is in play
            hex_coord = kwargs.get("hex")
            victim_id = kwargs.get("victim")
            if hex_coord and not self.pending_discards:
                self.move_robber_and_steal(tuple(hex_coord), victim_id)
            self._update_largest_army()
            self._check_win()
        elif card_type == DevCardType.ROAD_BUILDING.value:
            p.free_roads += 2
        elif card_type == DevCardType.YEAR_OF_PLENTY.value:
            for key in ("r1", "r2"):
                r = kwargs.get(key)
                if r:
                    rt = ResourceType(r)
                    if self._bank_take(rt, 1):  # take from the bank if available
                        p.gain(rt)
        elif card_type == DevCardType.MONOPOLY.value:
            rt = kwargs.get("resource")
            if rt:
                rt_enum = ResourceType(rt)
                total = 0
                for other in self.players:
                    if other.id != p.id:
                        amt = other.resources.get(rt_enum, 0)
                        other.resources[rt_enum] = 0
                        total += amt
                p.resources[rt_enum] += total
        elif card_type == DevCardType.VICTORY_POINT.value:
            pass  # already counted
        return True

    def end_turn(self):
        if self.phase != PHASE_MAIN:
            return False
        if self._seven_unresolved():
            return False
        p = self.current_player()
        # move new dev cards to hand
        p.dev_cards.extend(p.new_dev_cards)
        p.new_dev_cards = []
        p.played_dev_this_turn = False
        p.free_roads = 0
        self.trade_offer = None  # an open offer does not survive the turn
        # next player
        self.current_player_idx = (self.current_player_idx + 1) % self.num_players
        self.phase = PHASE_ROLL
        self.turn_number += 1
        self._check_win()
        return True

    # ---------- Validation helpers ----------
    def _distance_rule_ok(self, vertex):
        # no adjacent settlement/city
        for adj in self.board.adjacent_vertices(vertex):
            vi = self.board.vertices.get(adj)
            if vi and vi["building"] is not None:
                return False
        return True

    def _valid_settlement_spot(self, vertex, player):
        return True  # additional checks done elsewhere

    # ---------- Longest road / Largest army ----------
    def _update_longest_road(self):
        for p in self.players:
            length = self._longest_road_length(p.id)
            if length > self.longest_road_length:
                # remove from previous
                if self.longest_road_owner is not None and self.longest_road_owner != p.id:
                    self.players[self.longest_road_owner].longest_road = False
                    self.players[self.longest_road_owner].vp -= VP_LONGEST_ROAD
                self.longest_road_length = length
                self.longest_road_owner = p.id
                p.longest_road = True
                p.vp += VP_LONGEST_ROAD
                self._check_win()
            elif length == self.longest_road_length and self.longest_road_owner is not None and self.longest_road_owner != p.id:
                # tie: original keeper keeps it (standard rule: must exceed)
                pass

    def _longest_road_length(self, pid):
        # DFS over roads owned by pid
        # build adjacency of edges
        # vertices connected by pid's roads
        from collections import defaultdict
        adj = defaultdict(set)  # vertex -> set of vertices
        for ek, einfo in self.board.edges.items():
            if einfo["road_owner"] == pid:
                pts = list(ek)
                adj[pts[0]].add(pts[1])
                adj[pts[1]].add(pts[0])
        # DFS, avoid revisiting edges
        best = 0
        # try starting from each vertex
        visited_edges = set()
        def dfs(v, prev, length):
            nonlocal best
            best = max(best, length)
            for nb in adj[v]:
                ek = frozenset([v, nb])
                if ek in visited_edges:
                    continue
                # also check not blocked by opponent settlement/city on intermediate vertex
                # (standard rule: road broken by opponent building)
                vi = self.board.vertices.get(v)
                if vi and vi["owner"] is not None and vi["owner"] != pid and vi["building"] in ("settlement", "city"):
                    continue
                visited_edges.add(ek)
                dfs(nb, v, length + 1)
                visited_edges.discard(ek)
        for start in list(adj.keys()):
            visited_edges.clear()
            dfs(start, None, 0)
        return best

    def _update_largest_army(self):
        for p in self.players:
            if p.knights_played > self.largest_army_count:
                if self.largest_army_owner is not None and self.largest_army_owner != p.id:
                    self.players[self.largest_army_owner].largest_army = False
                    self.players[self.largest_army_owner].vp -= VP_LARGEST_ARMY
                self.largest_army_count = p.knights_played
                self.largest_army_owner = p.id
                p.largest_army = True
                p.vp += VP_LARGEST_ARMY
                self._check_win()
            elif p.knights_played == self.largest_army_count and self.largest_army_owner is not None and self.largest_army_owner != p.id:
                pass  # tie keeps original

    def _check_win(self):
        for p in self.players:
            if p.total_vp() >= VICTORY_TARGET:
                self.winner = p.id
                self.phase = PHASE_END
                return

    def player_port_ratio(self, player, resource=None):
        """Best bank-trade ratio for `resource` given the player's ports.

        4:1 default; 3:1 with any generic port; 2:1 only with the port
        matching `resource`.
        """
        best = 4
        for v, ptype in self.board.ports.items():
            vi = self.board.vertices.get(v)
            if vi and vi["owner"] == player.id and vi["building"] is not None:
                if ptype == "generic":
                    best = min(best, 3)
                elif resource is not None and ptype == resource:
                    return 2
        return best

    def trade_bank(self, give_rt, receive_rt, ratio=None):
        p = self.current_player()
        if self._seven_unresolved():
            return False
        # No same-resource exchanges: this closes the loophole of shrinking a
        # hand (e.g. 4 wood -> 1 wood) to dodge the 7's half-discard.
        if give_rt == receive_rt:
            return False
        # always use the server-computed ratio; never trust the client
        true_ratio = self.player_port_ratio(p, give_rt)
        if ratio is not None and ratio < true_ratio:
            return False  # client claims worse than allowed? suspicious, reject
        if self.bank.get(receive_rt, 0) < 1:
            return False  # the bank is out of the requested resource
        ok = bank_trade(p, give_rt, receive_rt, true_ratio)
        if ok:
            self._bank_put(give_rt, true_ratio)
            self._bank_take(receive_rt, 1)
        return ok

    # ---------- Player-to-player trade ----------
    def _norm_res(self, d):
        """Normalise a {resource_name: amount} dict into {ResourceType: int}.

        Raises ValueError on unknown resource names; ignores non-positive
        amounts.  Returns {} for an empty/None mapping.
        """
        out = {}
        for k, v in (d or {}).items():
            v = int(v)
            if v <= 0:
                continue
            rt = ResourceType(k)
            out[rt] = out.get(rt, 0) + v
        return out

    def create_trade_offer(self, give, want, targets):
        """The active player proposes a trade to one or more opponents.

        `give`  maps resource -> amount the proposer hands over.
        `want`  maps resource -> amount the proposer wants in return.
        `targets` is the list of opponent player ids allowed to accept.
        Returns True on success; the offer is stored in self.trade_offer.
        """
        if self.phase != PHASE_MAIN:
            return False
        if self._seven_unresolved():
            return False
        if self.trade_offer is not None:
            # Safety net: an offer made by anyone other than the current player
            # is stale (it belongs to a previous turn) and must not block a new
            # proposal.
            if self.trade_offer.get("from") != self.current_player_idx:
                self.trade_offer = None
            else:
                return False  # one open offer at a time
        p = self.current_player()
        try:
            give = self._norm_res(give)
            want = self._norm_res(want)
        except ValueError:
            return False
        if not give or not want:
            return False
        if set(give) & set(want):
            return False  # cannot give and want the same resource
        for rt, amt in give.items():
            if p.resources.get(rt, 0) < amt:
                return False
        tlist = []
        for t in (targets or []):
            t = int(t)
            if t != p.id and 0 <= t < self.num_players and t not in tlist:
                tlist.append(t)
        if not tlist:
            return False
        self.trade_offer = {
            "from": p.id, "give": give, "want": want,
            "targets": tlist, "declined": [],
        }
        return True

    def cancel_trade_offer(self, player_id=None):
        """The proposer withdraws the open offer."""
        if not self.trade_offer:
            return False
        pid = self.current_player_idx if player_id is None else int(player_id)
        if self.trade_offer["from"] != pid:
            return False
        self.trade_offer = None
        return True

    def respond_trade(self, player_id, accept):
        """A targeted player accepts or declines the open offer.

        On accept the resources are exchanged atomically and the offer is
        cleared.  On decline the player is removed from the responder pool;
        when everyone has declined the offer is cleared automatically.
        """
        offer = self.trade_offer
        if not offer:
            return False
        pid = int(player_id)
        if pid == offer["from"] or pid not in offer["targets"]:
            return False
        if pid in offer["declined"]:
            return False
        if not accept:
            offer["declined"].append(pid)
            if set(offer["declined"]) >= set(offer["targets"]):
                self.trade_offer = None
            return True
        responder = self.players[pid]
        for rt, amt in offer["want"].items():
            if responder.resources.get(rt, 0) < amt:
                return False  # responder cannot afford it
        proposer = self.players[offer["from"]]
        for rt, amt in offer["give"].items():
            if proposer.resources.get(rt, 0) < amt:
                self.trade_offer = None  # proposer no longer has the goods
                return False
        for rt, amt in offer["give"].items():
            proposer.resources[rt] -= amt
            responder.resources[rt] += amt
        for rt, amt in offer["want"].items():
            responder.resources[rt] -= amt
            proposer.resources[rt] += amt
        self.trade_offer = None
        return True

    def status(self):
        return {
            "phase": self.phase,
            "current": self.current_player_idx,
            "dice": self.dice,
            "winner": self.winner,
        }
