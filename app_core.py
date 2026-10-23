# app_core.py - game/lobby state and HTTP-agnostic routing.
#
# This module holds all of the Catan logic, the room/lobby state and the
# request routing, WITHOUT depending on any particular HTTP server. Two thin
# adapters use it:
#   * server.py - the local / Codespaces server (http.server, threaded)
#   * wsgi.py   - the PythonAnywhere deployment (Flask + WSGI)
#
# IMPORTANT: the game state (ROOM) lives in this process's memory. Run ONE
# worker process (single process, e.g. "--threads N") so every request sees the
# same game. Restarting the process resets the room.
import json, os, sys, threading, secrets
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.game import Game
from game.resources import ResourceType, TerrainType
from game.cards import DevCardType

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# ---------------------------------------------------------------------------
# Remote access / safety
#   The game is meant to be reached over a private network (Tailscale). The
#   only "power user" switch is /monitor?debug=1, which turns the view-only
#   monitor into a full-control hot-seat screen. It must NOT be available to
#   anyone coming in over the network, so it is limited to loopback by default.
#
#   Override with CATAN_DEBUG_CIDRS="127.0.0.0/8,100.64.0.0/10" if you ever
#   want to allow it from the Tailscale range too.
# ---------------------------------------------------------------------------
def _debug_cidrs():
    raw = os.environ.get("CATAN_DEBUG_CIDRS", "127.0.0.0/8,::1/128")
    return [c.strip() for c in raw.split(",") if c.strip()]


def _ip_in_cidr(ip, cidr):
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        if "/" in cidr:
            return addr in ipaddress.ip_network(cidr, strict=False)
        return addr == ipaddress.ip_address(cidr)
    except ValueError:
        return False


def _debug_allowed(ip):
    """True only for the configured (default: local) addresses."""
    return any(_ip_in_cidr(ip, c) for c in _debug_cidrs())

# ---------------------------------------------------------------------------
# Room / lobby state
#   seats:  [{"token","name","roll": [d1,d2] or None}, ...]  (join order)
#   order:  seat indices in PLAY order (set on start); rank == player id
#   slots:  lobby draft - seat index -> chosen turn number (1..N)
#   g:      the Game once started, else None
# ---------------------------------------------------------------------------
ROOM = {
    "phase": "lobby",   # "lobby" | "playing"
    "seats": [],
    "order": [],
    "g": None,
    "slots": {},        # lobby draft: seat index -> chosen turn number (1..N)
    "color_slots": {},  # lobby draft: seat index -> chosen colour (dice order)
    "settings": {       # house rules chosen in the lobby before the game starts
        "desert": "coast_ng",   # "center" | "coast_ng" | "none"
        "numbers": "official",  # "official" | "random"
        "victory": 10,          # 10 | 7
    },
}

# Player colours. Each seat picks one in the lobby (all different); the game
# itself only stores the name, and the browser maps it to a hex value.
PLAYER_COLORS = ("red", "blue", "white", "orange")
COLOR_LABELS = {
    "red": "赤", "blue": "青", "white": "白", "orange": "オレンジ",
}


def _free_color(seats):
    """First colour not used by another seat (seat order = preference order)."""
    used = {s.get("color") for s in seats}
    for i, c in enumerate(PLAYER_COLORS):
        if c not in used:
            return c
    return PLAYER_COLORS[0]

LOCK = threading.RLock()

# ---------------------------------------------------------------------------
# Single-process guard
#   The room lives in this process's memory, so the whole app MUST run in one
#   worker process. On shared hosts (e.g. PythonAnywhere) it is easy to end up
#   with several workers by accident, which would silently split the room.
#   We record the pid that owns the state and report the pid on /env so the
#   problem is visible instead of mysterious. Run with a single worker.
# ---------------------------------------------------------------------------
OWNER_PID = os.getpid()


def reset_room():
    with LOCK:
        ROOM["phase"] = "lobby"
        ROOM["seats"] = []
        ROOM["order"] = []
        ROOM["g"] = None
        ROOM["slots"] = {}
        ROOM["color_slots"] = {}
        ROOM["settings"] = {"desert": "coast_ng", "numbers": "official", "victory": 10}


def _new_token():
    return secrets.token_hex(8)


def token_to_pid(token):
    """Map a client token to a player id (= rank in the dice order)."""
    if not token:
        return None
    order = ROOM.get("order") or []
    seats = ROOM.get("seats") or []
    for rank, seat_i in enumerate(order):
        if 0 <= seat_i < len(seats) and seats[seat_i].get("token") == token:
            return rank
    return None


def _resolve_viewer(token, client_ip, view=None):
    """Decide what a /state caller is allowed to see.

    * a valid token  -> that player's pid (their own private view)
    * no / bad token -> SPECTATOR_VIEW (public info only)
    * a LOCAL monitor page (view=monitor from loopback) -> DEBUG_VIEW

    The debug view is only ever handed out for the monitor page on a trusted
    (default: loopback) address, so neither a remote visitor nor a token-less
    player page can read hands or hidden victory points.
    """
    pid = token_to_pid(token)
    if pid is not None:
        return pid
    if view == 'monitor' and _debug_allowed(client_ip):
        return DEBUG_VIEW
    return SPECTATOR_VIEW


def game():
    return ROOM.get("g")


def _pick_queue():
    """Dice order (largest total first, ties -> the player who joined first).

    This is only the order in which players CHOOSE their turn number; the
    actual play order is decided by the numbers they pick.
    """
    seats = ROOM.get("seats") or []
    q = [i for i, s in enumerate(seats) if s.get("roll")]
    q.sort(key=lambda i: (-sum(seats[i]["roll"]), i))
    return q


def _current_picker():
    """Seat index that still has to choose a turn number, or None if done."""
    slots = ROOM.get("slots") or {}
    for s in _pick_queue():
        if s not in slots:
            return s
    return None


def _slots_done():
    q = _pick_queue()
    slots = ROOM.get("slots") or {}
    return bool(q) and all(s in slots for s in q)


def _color_picker():
    """Seat that must choose a colour next: same dice order as the turn draft.

    Colours are drafted AFTER every turn number has been taken, so the two
    stages never interleave (much easier to follow on a phone).
    """
    if not _slots_done():
        return None
    picked = ROOM.get("color_slots") or {}
    for s in _pick_queue():
        if s not in picked:
            return s
    return None


def _draft_state():
    """None unless the room is waiting for picks; otherwise the draft state."""
    seats = ROOM.get("seats") or []
    if ROOM["phase"] != "lobby" or len(seats) < 2:
        return None
    if not all(s.get("roll") for s in seats):
        return None
    q = _pick_queue()
    slots = ROOM.get("slots") or {}
    colors = ROOM.get("color_slots") or {}
    slots_done = _slots_done()
    colors_done = slots_done and all(s in colors for s in q)
    if colors_done:
        stage = "done"
    elif slots_done:
        stage = "colors"
    else:
        stage = "slots"
    return {
        "queue": [{"seat": s, "name": seats[s].get("name") or f"プレイヤー{s+1}",
                   "total": sum(seats[s]["roll"])} for s in q],
        "slots": {str(s): slots[s] for s in q if s in slots},
        "colors": {str(s): colors[s] for s in q if s in colors},
        "current_picker": _current_picker(),
        "color_picker": _color_picker(),
        "stage": stage,
        "ready": colors_done,
    }


DESERT_MODES = ("center", "coast_ng", "none")


def _desert_mode():
    """The house rule for where the desert goes (validated, with a safe default)."""
    m = (ROOM.get("settings") or {}).get("desert", "coast_ng")
    return m if m in DESERT_MODES else "coast_ng"



def _numbers_mode():
    """House rule for number-token layout (validated, with a safe default)."""
    m = (ROOM.get("settings") or {}).get("numbers", "official")
    return m if m in ("official", "random") else "official"


def _victory_target():
    """House rule for the winning score (10 default, or 7 for a short game)."""
    v = (ROOM.get("settings") or {}).get("victory", 10)
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = 10
    return v if v in (7, 10) else 10

def _ensure_board():
    """Create the board the lobby preview shows.

    The map is generated once, as soon as it can be seen (i.e. while the room is
    still in the lobby, with 2+ players), and it is REUSED by room_start - so
    the board players choose their turn order around is exactly the board they
    play on.
    """
    if ROOM["phase"] != "lobby":
        return ROOM.get("g")
    g = ROOM.get("g")
    if g is not None:
        return g                          # keep the map that is already on screen
    if len(ROOM["seats"]) < 2:
        return None                       # nothing to decide with one player
    ROOM["g"] = Game(num_players=len(ROOM["seats"]), seed=None,
                     desert=_desert_mode(), numbers=_numbers_mode(),
                     victory_target=_victory_target())
    return ROOM["g"]


def _sync_board():
    """Make the previewed map match the room again after a seat change.

    A player joining or leaving invalidates the map that is on screen (it was
    generated for a different number of players). Rather than silently swapping
    the map while people are looking at it, the preview is dropped until the
    draft reopens (which needs a fresh roll from everyone anyway).
    """
    if ROOM["phase"] != "lobby":
        return None
    g = ROOM.get("g")
    if g is None:
        return None
    if len(g.players) != len(ROOM["seats"]):
        # The seat count changed after the map was generated: drop the preview
        # and the rolls (everyone has to roll again for the new draft anyway).
        ROOM["g"] = None
        ROOM["slots"] = {}
        ROOM["color_slots"] = {}
        for s in ROOM["seats"]:
            s["roll"] = None
        return None
    return g


def serialize_room(token=None):
    seats = [{
        "seat": i,
        "name": s.get("name") or f"プレイヤー{i+1}",
        "roll": s.get("roll"),
        "total": (sum(s["roll"]) if s.get("roll") else None),
        "color": s.get("color") or PLAYER_COLORS[i % len(PLAYER_COLORS)],
    } for i, s in enumerate(ROOM["seats"])]
    order = None
    if ROOM["phase"] == "playing" and ROOM["order"]:
        order = []
        for rank, seat_i in enumerate(ROOM["order"]):
            order.append({"pid": rank, "seat": seat_i,
                          "name": ROOM["seats"][seat_i].get("name") or f"プレイヤー{rank+1}"})
    draft = _draft_state()
    # Board preview: while the room is still in the lobby the map is shown (and
    # is the very map room_start will use) so players can choose their turn
    # order while looking at the board.
    preview = None
    if ROOM["phase"] == "lobby" and ROOM.get("g") is not None:
        preview = board_data(ROOM["g"].board)
    return {
        "phase": ROOM["phase"],
        "seats": seats,
        "order": order,
        "you": token_to_pid(token),
        "you_seat": _seat_of(token),
        "num_players": len(ROOM["seats"]),
        "draft": draft,
        "can_start": bool(draft and draft.get("ready")),
        "settings": dict(ROOM.get("settings") or {}),
        "board": preview,
    }


# ---------------------------------------------------------------------------
# Serialization (public / private filtering)
#   viewer is an int pid      -> that player's private view
#   viewer == 'spectator'     -> public information only (no token / bad token,
#                                or a remote monitor). Anyone can get this, so it
#                                must never leak hands or hidden victory points.
#   viewer == 'debug'         -> everything visible. Only ever produced for a
#                                LOCAL monitor (loopback), see route_get().
# ---------------------------------------------------------------------------
DEBUG_VIEW = "debug"
SPECTATOR_VIEW = "spectator"


def _viewer_sees_all(viewer):
    """True when this view is the unrestricted (hot-seat / local monitor) one."""
    return viewer is None or viewer == DEBUG_VIEW


def serialize_player(p, viewer, reveal=False):
    full = reveal or _viewer_sees_all(viewer) or (p.id == viewer)
    d = {
        "id": p.id, "name": p.name, "color": p.color,
        "hand_count": p.total_resources(),
        "dev_count": len(p.dev_cards) + len(p.new_dev_cards),
        "used_dev_cards": list(p.used_dev_cards),
        "roads_left": p.roads_left, "settlements_left": p.settlements_left,
        "cities_left": p.cities_left, "knights": p.knights_played,
        "longest_road": p.longest_road, "largest_army": p.largest_army,
        "free_roads": p.free_roads,
        "vp": p.vp,                      # visible (board) victory points
        "revealed": reveal,              # True once the game is over (cards open)
    }
    if full:
        d["resources"] = {r.value: p.resources[r] for r in ResourceType if r != ResourceType.DESERT}
        d["dev_cards"] = list(p.dev_cards)
        d["new_dev_cards"] = list(p.new_dev_cards)
        d["hidden_vp"] = p.hidden_vp  # private: VP development cards
        d["total_vp"] = p.total_vp()
    else:
        # only what is visible on the board
        d["total_vp"] = p.vp
    return d


def board_data(b):
    """Terrain / numbers / ports / geometry of one board.

    Used for the running game AND for the lobby preview (the board is generated
    as soon as the turn-order draft opens, so players can choose their turn
    while looking at the map that will actually be played on).
    """
    hexes = []
    for (q, r), h in b.hexes.items():
        hexes.append({
            "q": q, "r": r,
            "terrain": h.terrain.value,
            "number": h.number,
            "robber": h.has_robber,
            "resource": (h.resource.value if h.resource else None),
        })
    v_list = list(b.vertices.keys())
    v_index = {pt: i for i, pt in enumerate(v_list)}
    vertices = []
    for pt in v_list:
        info = b.vertices[pt]
        vertices.append({
            "i": v_index[pt],
            "x": pt[0], "y": pt[1],
            "building": info["building"],
            "owner": info["owner"],
            "port_type": (b.ports[pt].value if hasattr(b.ports.get(pt), "value") else b.ports.get(pt)) if pt in b.ports else None,
        })
    edges = []
    for ek in b.edges.keys():
        pts = list(ek)
        info = b.edges[ek]
        edges.append({
            "points": [list(p) for p in pts],
            "road_owner": info["road_owner"],
            "v": [v_index[p] for p in pts],
        })
    ports = {}
    for v, pt in b.ports.items():
        ports[str(v_index[v])] = (pt.value if hasattr(pt, "value") else pt)
    port_edges = []
    for (v1, v2), ptype in getattr(b, "port_edges", []):
        port_edges.append({
            "v": [v_index[v1], v_index[v2]],
            "x1": v1[0], "y1": v1[1], "x2": v2[0], "y2": v2[1],
            "type": (ptype.value if hasattr(ptype, "value") else ptype),
        })
    return {
        "hexes": hexes,
        "vertices": vertices,
        "edges": edges,
        "ports": ports,
        "port_edges": port_edges,
    }


def serialize(g, viewer=None):
    b = g.board
    bd = board_data(b)
    v_list = list(b.vertices.keys())
    e_list = list(b.edges.keys())

    players = [serialize_player(p, viewer, reveal=g.winner is not None) for p in g.players]

    cur = g.current_player()
    valid_roads = []
    valid_settlements = []
    valid_cities = []
    if g.phase in ("setup", "main"):
        for ei, ek in enumerate(e_list):
            if b.edges[ek]["road_owner"] is not None:
                continue
            if g.phase == "main":
                if g._road_adjacent_to_player(ek, cur.id):
                    valid_roads.append(ei)
            else:
                # setup: only the road of the settlement placed in THIS step
                if getattr(g, "setup_last_vertex", None) is not None and g.setup_last_vertex in ek:
                    valid_roads.append(ei)
        for vi_i, pt in enumerate(v_list):
            info = b.vertices[pt]
            if info["building"] is not None:
                continue
            if not g._distance_rule_ok(pt):
                continue
            if g.phase == "setup":
                # settlement of this step must be placed before its road
                if not getattr(g, "setup_placed_settlement", False):
                    valid_settlements.append(vi_i)
            else:
                if g._settlement_adjacent_to_player_road(pt, cur.id):
                    valid_settlements.append(vi_i)
        for vi_i, pt in enumerate(v_list):
            info = b.vertices[pt]
            if info["building"] == "settlement" and info["owner"] == cur.id:
                valid_cities.append(vi_i)

    robber_victims = {}
    for (q, r) in b.hexes.keys():
        vids = g.possible_robber_victims((q, r))
        if vids:
            robber_victims[f"{q},{r}"] = vids

    trade_ratios = {}
    for rt in ResourceType:
        if rt == ResourceType.DESERT:
            continue
        trade_ratios[rt.value] = g.player_port_ratio(cur, rt)

    trade_offer = None
    if getattr(g, "trade_offer", None):
        to = g.trade_offer
        trade_offer = {
            "from": to["from"],
            "give": {rt.value: amt for rt, amt in to["give"].items()},
            "want": {rt.value: amt for rt, amt in to["want"].items()},
            "targets": list(to["targets"]),
            "declined": list(to.get("declined", [])),
        }

    return {
        "phase": g.phase,
        "bank": {rt.value: n for rt, n in g.bank.items()},
        "current": g.current_player_idx,
        # `you` is the viewer's player id, or null for spectators / the monitor.
        # `role` says which of the three views this is ('player'|'spectator'|'debug').
        "you": viewer if isinstance(viewer, int) else None,
        "role": ("player" if isinstance(viewer, int)
                 else (viewer if isinstance(viewer, str) else DEBUG_VIEW)),
        "turn_number": g.turn_number,
        "dice": list(g.dice),
        "winner": g.winner,
        "setup_round": getattr(g, "setup_round", 0),
        # True while the current player still must place this step's settlement
        # (i.e. settlement -> road is enforced). False = road is next.
        "setup_settlement_required": (g.phase == "setup" and not getattr(g, "setup_placed_settlement", False)),
        "robber_pending": getattr(g, "robber_pending", False),
        "pending_discards": {str(k): v for k, v in getattr(g, "pending_discards", {}).items()},
        "rerolled": getattr(g, "last_roll_rerolled", False),
        "players": players,
        "board": bd,
        "robber_victims": robber_victims,
        "trade_ratios": trade_ratios,
        "trade_offer": trade_offer,
        # Public event log (dev cards played, the robber, longest road / largest
        # army, the win, ...). Same text for every viewer: it never contains
        # hidden information. Clients diff by `id` to toast / append to the log.
        "events": list(getattr(g, "events", [])),
        "valid": {
            "roads": valid_roads,
            "settlements": valid_settlements,
            "cities": valid_cities,
        },
    }


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
# Actions only the current player may perform.
CURRENT_ONLY = {
    "roll", "end_turn", "build_road", "build_settlement", "build_city",
    "buy_dev", "play_dev", "move_robber", "trade_bank", "trade_offer",
}


def handle_lobby(action, payload, local=True):
    token = payload.get("token") or ""
    if action == "join":
        with LOCK:
            name = (payload.get("name") or "").strip()[:24]
            # rejoin: an existing token keeps its seat
            for s in ROOM["seats"]:
                if s.get("token") == token:
                    if name:
                        s["name"] = name
                    return {"ok": True, "token": token,
                            "pid": token_to_pid(token), "seat": ROOM["seats"].index(s)}
            if ROOM["phase"] != "lobby":
                return {"ok": False, "error": "game already started"}
            if len(ROOM["seats"]) >= 4:
                return {"ok": False, "error": "room is full"}
            tok = _new_token()
            ROOM["seats"].append({"token": tok,
                                  "name": name or f"プレイヤー{len(ROOM['seats'])+1}",
                                  "color": _free_color(ROOM["seats"]),
                                  "roll": None})
            _sync_board()      # drop a preview whose player count is now wrong
            if ROOM["g"] is None and len(ROOM["seats"]) >= 2:
                _ensure_board()   # 2人そろったら盤面プレビューを出す
            return {"ok": True, "token": tok, "pid": None, "seat": len(ROOM["seats"]) - 1}
    if action == "room_roll":
        with LOCK:
            seat = _seat_of(token)
            if seat is None:
                return {"ok": False, "error": "not joined"}
            if ROOM["phase"] != "lobby":
                return {"ok": False}
            import random
            d = [random.randint(1, 6), random.randint(1, 6)]
            ROOM["seats"][seat]["roll"] = d
            if all(s.get("roll") for s in ROOM["seats"]):
                _ensure_board()      # draft is about to open -> show the map
            return {"ok": True, "dice": d, "total": sum(d)}
    if action == "leave":
        # Leave the table: the seat is removed entirely. Only possible in the
        # lobby - once the game is running the turn order / player ids would
        # have to be rebuilt, so the monitor's "初期化" is the way back.
        with LOCK:
            seat = _seat_of(token)
            if seat is None:
                return {"ok": False, "error": "not joined"}
            if ROOM["phase"] != "lobby":
                return {"ok": False, "error": "ゲーム進行中は退出できません（監視画面の初期化でロビーに戻してください）"}
            seats = ROOM["seats"]
            seats.pop(seat)
            # seats shift down: re-index the draft choices and drop the roll of
            # the player who left (they are gone), keeping the others' rolls.
            slots = ROOM.get("slots") or {}
            ROOM["slots"] = {k - 1 if k > seat else k: v
                             for k, v in slots.items() if k != seat}
            colors = ROOM.get("color_slots") or {}
            ROOM["color_slots"] = {k - 1 if k > seat else k: v
                                   for k, v in colors.items() if k != seat}
            # A different player count invalidates the previewed map.
            _sync_board()
            if ROOM["g"] is None and len(seats) >= 2:
                _ensure_board()
            return {"ok": True}
    if action == "room_reset":
        # Dev/monitor reset of the whole room. Refused for remote callers: a
        # forwarded link must never be able to wipe a running game.
        if not local:
            return {"ok": False, "error": "この操作は外部からは行えません"}
        reset_room()
        return {"ok": True}
    if action == "room_pick":
        # Lobby draft: the player whose turn it is in the dice order picks a
        # free turn number (1..N). Once picked, a player may re-pick any free
        # number until the game actually starts.
        with LOCK:
            seat = _seat_of(token)
            if seat is None:
                return {"ok": False, "error": "not joined"}
            if ROOM["phase"] != "lobby":
                return {"ok": False, "error": "already started"}
            seats = ROOM["seats"]
            if not all(s.get("roll") for s in seats):
                return {"ok": False, "error": "サイコロが未振りの人がいます"}
            try:
                n = int(payload.get("slot"))
            except (TypeError, ValueError):
                return {"ok": False, "error": "invalid slot"}
            if not (1 <= n <= len(seats)):
                return {"ok": False, "error": "invalid slot"}
            slots = ROOM.setdefault("slots", {})
            if any(v == n and k != seat for k, v in slots.items()):
                return {"ok": False, "error": "その番号は既に選ばれています"}
            if seat not in _pick_queue():
                return {"ok": False, "error": "not your turn to pick"}
            if seat != _current_picker() and seat not in slots:
                return {"ok": False, "error": "順番がまだ来ていません"}
            slots[seat] = n
            return {"ok": True, "seat": seat, "slot": n}
    if action == "room_color":
        # Colour draft, stage 2 of the lobby draft: same dice order as the turn
        # number draft. Two seats may never share a colour.
        with LOCK:
            seat = _seat_of(token)
            if seat is None:
                return {"ok": False, "error": "not joined"}
            if ROOM["phase"] != "lobby":
                return {"ok": False, "error": "ゲーム中は変更できません"}
            color = payload.get("color")
            if color not in PLAYER_COLORS:
                return {"ok": False, "error": "不正な色です"}
            if not _slots_done():
                return {"ok": False, "error": "先に順番を決めてください"}
            picked = ROOM.setdefault("color_slots", {})
            if any(v == color and k != seat for k, v in picked.items()):
                return {"ok": False, "error": "その色は既に選ばれています"}
            # Only the player whose turn it is may pick; someone who already
            # picked may still switch to another free colour until the start.
            if seat != _color_picker() and seat not in picked:
                return {"ok": False, "error": "色を選ぶ順番ではありません"}
            picked[seat] = color
            ROOM["seats"][seat]["color"] = color   # mirror for the seat list
            return {"ok": True, "color": color, "seat": seat}
    if action == "room_setting":
        with LOCK:
            if ROOM["phase"] != "lobby":
                return {"ok": False, "error": "ゲーム中は変更できません"}
            # Only seated players may change the house rules (an empty room is
            # allowed so the tests / a fresh server can be configured).
            if ROOM["seats"] and _seat_of(token) is None:
                return {"ok": False, "error": "席に着いている人だけが変更できます"}
            s = ROOM.setdefault("settings", {})
            key = payload.get("key")
            val = payload.get("value")
            if key in ("desert", "numbers", "victory"):
                if key == "desert" and val not in DESERT_MODES:
                    return {"ok": False, "error": "不正な設定値です"}
                if key == "numbers" and val not in ("official", "random"):
                    return {"ok": False, "error": "不正な設定値です"}
                if key == "victory":
                    try:
                        val = int(val)
                    except (TypeError, ValueError):
                        return {"ok": False, "error": "不正な設定値です"}
                    if val not in (7, 10):
                        return {"ok": False, "error": "不正な設定値です"}
                s[key] = val
                # The desert placement changes the map, so a map that is already
                # on screen is no longer valid - drop it and regenerate it right
                # away with the new rule (players are looking at the board).
                ROOM["g"] = None
                ROOM["slots"] = {}
                ROOM["color_slots"] = {}
                for seat in ROOM["seats"]:
                    seat["roll"] = None
                _ensure_board()
                return {"ok": True, "settings": s}
            return {"ok": False, "error": "不明な設定です"}
    if action == "room_start":
        with LOCK:
            if ROOM["phase"] != "lobby":
                return {"ok": False, "error": "already started"}
            # A passer-by must not be able to start someone else's game.
            if ROOM["seats"] and _seat_of(token) is None:
                return {"ok": False, "error": "席に着いている人だけが開始できます"}
            seats = ROOM["seats"]
            if len(seats) < 2:
                return {"ok": False, "error": "need at least 2 players"}
            if not all(s.get("roll") for s in seats):
                return {"ok": False, "error": "everyone must roll first"}
            q = _pick_queue()
            slots = ROOM.get("slots") or {}
            if any(s not in slots for s in q):
                return {"ok": False, "error": "順番が未確定です（全員が番号を選んでください）"}
            picked = ROOM.get("color_slots") or {}
            if any(s not in picked for s in q):
                return {"ok": False, "error": "色が未確定です（全員が色を選んでください）"}
            # Play order follows the numbers the players chose, not the dice.
            order = sorted(q, key=lambda i: slots[i])
            ROOM["order"] = order
            names = [seats[i].get("name") or f"プレイヤー{i+1}" for i in order]
            colors = [picked[i] for i in order]
            # Reuse the board the players were looking at during the draft.
            g = _ensure_board()
            if g is None:
                g = ROOM["g"] = Game(num_players=len(seats), seed=None, names=names,
                                     colors=colors, desert=_desert_mode(),
                                     numbers=_numbers_mode(),
                                     victory_target=_victory_target())
            for i, p in enumerate(g.players):
                p.name = names[i]
                p.color = colors[i]
            ROOM["phase"] = "playing"
            return {"ok": True, "order": order}
    return None


def _seat_of(token):
    if not token:
        return None
    for i, s in enumerate(ROOM["seats"]):
        if s.get("token") == token:
            return i
    return None


def handle_action(action, payload, actor, local=True):
    """Returns the response dict, or None if the action is unknown.

    `local` is True only for requests from a trusted (default: local) address.
    The monitor-only power actions (init/new/auto_setup/give_resources) are
    refused for remote clients so a forwarded URL alone cannot take over a game.
    """
    if not local and action in ("room_init", "monitor_new", "auto_setup", "give_resources"):
        return {"ok": False, "error": "この操作は外部からは行えません"}
    if action == "room_init":
        # Monitor-only: finish/abort the current game and return everyone to the
        # lobby. Seats (names + tokens) are kept so players only need to re-roll;
        # the game itself and all dice are cleared.
        if actor is not None:
            return {"ok": False, "error": "monitor only"}
        with LOCK:
            for s in ROOM["seats"]:
                s["roll"] = None
            ROOM["order"] = []
            ROOM["slots"] = {}
            ROOM["color_slots"] = {}
            ROOM["g"] = None
            ROOM["phase"] = "lobby"
        return {"ok": True}
    if action == "monitor_new":
        # monitor / solo: start a fresh full-visibility hot-seat game
        if actor is not None:
            return {"ok": False, "error": "monitor only"}
        with LOCK:
            reset_room()
            ROOM["g"] = Game(num_players=4, seed=None, desert=_desert_mode(), numbers=_numbers_mode(), victory_target=_victory_target())
            ROOM["phase"] = "playing"
        return {"ok": True}
    if ROOM["phase"] != "playing":
        # The lobby preview creates a (phase="setup") game so the map can be
        # shown, but no game action may touch it until room_start.
        return {"ok": False, "error": "ゲームが開始されていません"}
    g = game()
    if g is None:
        return {"ok": False, "error": "game not started"}
    b = g.board
    v_list = list(b.vertices.keys())
    e_list = list(b.edges.keys())

    # authorization
    #   * A request with no valid token (actor is None) is only allowed to act
    #     when it comes from a trusted/local address (the hot-seat monitor used
    #     for local play and the automated tests). A remote tokenless request
    #     must not be able to drive the game at all.
    #   * A real client (actor is a pid) may only act on its own turn / its own
    #     discard / its own trade response.
    if actor is None and not local:
        return {"ok": False, "error": "この操作は外部からは行えません"}
    if actor is not None and action in CURRENT_ONLY and actor != g.current_player_idx:
        return {"ok": False, "error": "not your turn"}
    if actor is not None and action == "discard" and actor != payload.get("player"):
        return {"ok": False, "error": "not your discard"}
    if actor is not None and action in ("trade_respond", "trade_cancel") and actor != payload.get("player"):
        return {"ok": False, "error": "not your action"}

    if action == "roll":
        total = g.roll_dice()
        return {"ok": total is not None, "total": total}
    if action == "end_turn":
        return {"ok": g.end_turn()}
    if action == "build_road":
        ei = payload["edge"]
        ek = e_list[ei]
        ok = g.build_road_at(ek) if g.phase == "main" else g.place_setup_road(ek)
        return {"ok": ok}
    if action == "build_settlement":
        vi = payload["vertex"]
        pt = v_list[vi]
        ok = g.place_setup_settlement(pt) if g.phase == "setup" else g.build_settlement_at(pt)
        return {"ok": ok}
    if action == "build_city":
        pt = v_list[payload["vertex"]]
        return {"ok": g.build_city_at(pt)}
    if action == "buy_dev":
        c = g.buy_dev_card_action()
        return {"ok": c is not None, "card": c}
    if action == "play_dev":
        if g.play_dev_card(payload["card"], hex=payload.get("hex"), victim=payload.get("victim"),
                           r1=payload.get("r1"), r2=payload.get("r2"),
                           resource=payload.get("resource")):
            return {"ok": True}
        return {"ok": False,
                "error": "そのカードは使えません（今ターンはすでに1枚使うか、カードがまだ手札に移っていません）。"}
    if action == "move_robber":
        return {"ok": g.move_robber_and_steal(tuple(payload["hex"]), payload.get("victim"))}
    if action == "discard":
        return {"ok": g.discard_cards(payload.get("resources", {}), payload.get("player"))}
    if action == "trade_bank":
        give = ResourceType(payload["give"])
        recv = ResourceType(payload["receive"])
        return {"ok": g.trade_bank(give, recv, payload.get("ratio"))}
    if action == "trade_offer":
        if getattr(g, "trade_offer", None):
            # only one negotiation at a time (the current offer must be accepted,
            # declined or withdrawn first)
            return {"ok": False,
                    "error": "既に提案が開いています。相手の応答を待つか、提案を取り消してください。"}
        if g.create_trade_offer(payload.get("give", {}), payload.get("want", {}),
                                payload.get("targets", [])):
            return {"ok": True}
        return {"ok": False,
                "error": "提案できませんでした（手番・資源の量・相手の選択を確認してください）。"}
    if action == "trade_respond":
        return {"ok": g.respond_trade(payload.get("player"), payload.get("accept", False))}
    if action == "trade_cancel":
        return {"ok": g.cancel_trade_offer(payload.get("player"))}
    if action == "give_resources":
        # debug helper: monitor only
        if actor is not None:
            return {"ok": False, "error": "monitor only"}
        amt = payload.get("amount", 5)
        cur = g.current_player()
        for r in ResourceType:
            if r != ResourceType.DESERT:
                cur.resources[r] += amt
        return {"ok": True}
    if action == "auto_setup":
        if actor is not None:
            return {"ok": False, "error": "monitor only"}
        verts = list(b.vertices.keys())
        placed = 0
        while g.phase == "setup":
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
            if candidate is None:
                break
            g.place_setup_settlement(candidate)
            road_edge = None
            for ek in b.edges:
                if candidate in ek and b.edges[ek]["road_owner"] is None:
                    road_edge = ek
                    break
            g.place_setup_road(road_edge)
            placed += 1
        return {"ok": True, "placed": placed}
    return None


# ---------------------------------------------------------------------------
# HTTP-agnostic routing
#   Adapters (server.py / wsgi.py) turn these into real responses.
# ---------------------------------------------------------------------------
import mimetypes


def _content_type_for(path):
    if path.endswith('.html'):
        return 'text/html; charset=utf-8'
    if path.endswith('.css'):
        return 'text/css; charset=utf-8'
    if path.endswith('.js'):
        return 'application/javascript; charset=utf-8'
    if path.endswith('.json'):
        return 'application/json; charset=utf-8'
    if path.endswith('.png'):
        return 'image/png'
    if path.endswith('.svg'):
        return 'image/svg+xml'
    if path.endswith('.ico'):
        return 'image/x-icon'
    return 'application/octet-stream'


def route_get(path, query, client_ip):
    """Handle a GET. Returns (status, content_type, body_bytes).

    `query` is a dict of str -> list[str] (like parse_qs). `client_ip` is the
    caller's address (used only for the /env debug gate).
    """
    token = (query.get('token') or [None])[0]

    if path in ('/', '/client', '/client.html'):
        return _file_response('client.html')
    if path in ('/monitor', '/monitor.html', '/index.html'):
        return _file_response('index.html')
    if path == '/style.css':
        return _file_response('style.css')
    if path == '/game.js':
        return _file_response('game.js')
    if path.startswith('/assets/'):
        return _file_response(path.lstrip('/'))

    if path == '/room':
        body = json.dumps(serialize_room(token)).encode()
        return (200, 'application/json; charset=utf-8', body)
    if path == '/env':
        body = json.dumps({'debug_allowed': _debug_allowed(client_ip),
                           'pid': os.getpid(),
                           'owner_pid': OWNER_PID}).encode()
        return (200, 'application/json; charset=utf-8', body)
    if path == '/state':
        with LOCK:
            g = game()
            if g is None or ROOM['phase'] != 'playing':
                body = json.dumps({'phase': 'lobby', 'started': False}).encode()
                return (200, 'application/json; charset=utf-8', body)
            viewer = _resolve_viewer(token, client_ip, (query.get('view') or [None])[0])
            body = json.dumps(serialize(g, viewer)).encode()
            return (200, 'application/json; charset=utf-8', body)

    return (404, 'text/plain; charset=utf-8', b'Not Found')


def _file_response(rel_name):
    """Read a file from web/ and return (status, content_type, bytes)."""
    # guard against path traversal
    safe = os.path.normpath(rel_name).lstrip('/')
    if safe.startswith('..'):
        return (404, 'text/plain; charset=utf-8', b'Not Found')
    full = os.path.join(WEB_DIR, safe)
    if not full.startswith(os.path.abspath(WEB_DIR)):
        return (404, 'text/plain; charset=utf-8', b'Not Found')
    try:
        with open(full, 'rb') as f:
            data = f.read()
    except (FileNotFoundError, IsADirectoryError):
        return (404, 'text/plain; charset=utf-8', b'Not Found')
    return (200, _content_type_for(safe), data)


def route_post(payload, query, client_ip):
    """Handle a POST. `payload` is the parsed JSON body (dict). Returns a dict."""
    token = payload.get('token') or (query.get('token') or [None])[0]
    action = payload.get('action')
    local = _debug_allowed(client_ip)
    try:
        with LOCK:
            lobby_res = handle_lobby(action, payload, local=local)
            if lobby_res is not None:
                return lobby_res
            actor = token_to_pid(token)
            action_res = handle_action(action, payload, actor, local=local)
            if action_res is not None:
                return action_res
            return {'ok': False, 'error': 'unknown action'}
    except Exception as e:           # never leak a stack trace to the client
        return {'ok': False, 'error': str(e)}


def ensure_started():
    """Reset the room once at import/startup time."""
    reset_room()
