# game/board.py
import math
from .resources import TerrainType, TERRAIN_TO_RESOURCE, ResourceType

# Axial coordinate neighbors (pointy-top)
HEX_NEIGHBORS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]

def axial_to_pixel(q, r, size=1.0):
    x = size * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
    y = size * (3 / 2 * r)
    return (x, y)

def hex_corners(cx, cy, size=1.0):
    corners = []
    for i in range(6):
        angle = math.radians(30 + 60 * i)
        corners.append((cx + size * math.cos(angle),
                        cy + size * math.sin(angle)))
    return corners

def round_pt(p, nd=6):
    return (round(p[0], nd), round(p[1], nd))

class Hex:
    def __init__(self, q, r, terrain, number=None):
        self.q = q
        self.r = r
        self.terrain = terrain
        self.number = number  # dice number 2-12 or None
        self.has_robber = False

    @property
    def resource(self):
        return TERRAIN_TO_RESOURCE[self.terrain]

    def __repr__(self):
        return f"Hex({self.q},{self.r},{self.terrain.value},num={self.number})"

    def __eq__(self, other):
        return isinstance(other, Hex) and self.q == other.q and self.r == other.r

    def __hash__(self):
        return hash((self.q, self.r))


class Board:
    """Standard Catan board: 19 hexes in 3-4-5-4-3 layout."""

    # Terrain distribution for standard board
    TERRAINS = [
        TerrainType.FOREST, TerrainType.FOREST, TerrainType.FOREST, TerrainType.FOREST,
        TerrainType.HILLS, TerrainType.HILLS, TerrainType.HILLS,
        TerrainType.PASTURE, TerrainType.PASTURE, TerrainType.PASTURE, TerrainType.PASTURE,
        TerrainType.FIELDS, TerrainType.FIELDS, TerrainType.FIELDS, TerrainType.FIELDS,
        TerrainType.MOUNTAINS, TerrainType.MOUNTAINS, TerrainType.MOUNTAINS,
        TerrainType.DESERT,
    ]

    # Number tokens are placed in the official spiral order (A..R).
    # Start at one of the island's 6 corners and proceed counterclockwise
    # toward the centre, skipping the desert hex.
    NUMBER_SEQUENCE = [5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11]

    def __init__(self, seed=None, desert="coast_ng"):
        import random
        rng = random.Random(seed)
        self.seed = seed
        self.rng = rng
        self.desert_mode = desert          # "center" | "coast_ng" | "none"
        self.hexes = {}  # (q,r) -> Hex
        self.vertices = {}  # vertex_key -> {hexes, building, owner}
        self.edges = {}  # edge_key -> {hexes, road_owner}
        self._build_layout()
        self._assign_terrains(rng)
        self._assign_numbers(rng)
        self._build_graph()
        # robber starts on desert
        for h in self.hexes.values():
            if h.terrain == TerrainType.DESERT:
                h.has_robber = True
                self.robber_hex = (h.q, h.r)
                break
        self._assign_ports()

    def _assign_ports(self, rng=None):
        """Official-style port layout.

        Each port is a dock on a coastal EDGE (between the two coastal
        vertices at its ends).  A building on either endpoint grants use
        of the port - matching the official rule that a settlement on
        either of the two coastal corners of a harbor may use it.

        The 9 ports are distributed evenly around the coast cycle (so the
        five 2:1 ports are spread out, never clustered), and the port
        types alternate 2:1 / 3:1 like the official board (4x 3:1 generic
        and 5x 2:1 specific).
        """
        import random
        rng = rng or random.Random(self.seed)
        self.ports = {}       # vertex -> port_type (both endpoints)
        self.port_edges = []  # [((v1, v2), port_type), ...] for UI docks

        coastal_edges = [ek for ek, info in self.edges.items()
                         if len(info["hexes"]) == 1]
        if not coastal_edges:
            return

        # Walk the coast as a vertex cycle
        adj = {}  # vertex -> neighbouring coastal vertices
        for ek in coastal_edges:
            a, b = tuple(ek)
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        start = min(adj)
        cycle = [start]
        prev, cur = None, start
        while True:
            nxt = next((v for v in adj[cur] if v != prev), None)
            if nxt is None or nxt == start:
                break
            cycle.append(nxt)
            prev, cur = cur, nxt
        n = len(cycle)
        if n < 12:
            return

        # coastal edges between consecutive cycle vertices
        cycle_edges = [(cycle[i], cycle[(i + 1) % n]) for i in range(n)]

        # Rotate the starting point so ports are not aligned with a corner
        offset = rng.randrange(n)

        # 9 ports evenly spaced along the 30-edge cycle
        port_edge_slots = []
        used_indices = set()
        for i in range(9):
            idx = round(i * n / 9.0)
            while idx % n in used_indices:
                idx += 1
            idx %= n
            used_indices.add(idx)
            a, b = cycle_edges[(idx + offset) % n]
            port_edge_slots.append((a, b))

        # Port types: alternate specific 2:1 and generic 3:1
        # (5 specific + 4 generic = 9 ports)
        specifics = [ResourceType.WOOD, ResourceType.BRICK, ResourceType.SHEEP,
                     ResourceType.WHEAT, ResourceType.ORE]
        rng.shuffle(specifics)
        specific_first = rng.randrange(2)
        types = []
        si = 0
        for i in range(len(port_edge_slots)):
            if (i % 2 == 0) == (specific_first == 0) and si < len(specifics):
                types.append(specifics[si])
                si += 1
            else:
                types.append("generic")

        for (v1, v2), ptype in zip(port_edge_slots, types):
            self.ports[v1] = ptype
            self.ports[v2] = ptype
            self.port_edges.append(((v1, v2), ptype))

    def _build_layout(self):
        # axial coords for 3-4-5-4-3 layout
        rows = [
            (-2, [0, 1, 2]),
            (-1, [-1, 0, 1, 2]),
            (0, [-2, -1, 0, 1, 2]),
            (1, [-2, -1, 0, 1]),
            (2, [-2, -1, 0]),
        ]
        for r, qs in rows:
            for q in qs:
                self.hexes[(q, r)] = None  # placeholder

    def _ring(self, radius):
        """Axial hexes on the ring of the given radius around the centre.

        Returned counterclockwise starting from the hex at
        `centre + radius * (-1, 1)` (the upper-left corner direction),
        matching the direction required by the official number layout.
        """
        dirs = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
        hex_ = (-radius, radius)
        result = []
        for i in range(6):
            for _ in range(radius):
                result.append(hex_)
                dq, dr = dirs[i]
                hex_ = (hex_[0] + dq, hex_[1] + dr)
        return result

    def _spiral(self, corner=0):
        """Full 19-hex spiral path (outer ring -> inner ring -> centre).

        `corner` (0-5) rotates the whole spiral by 60 degrees so it starts
        at one of the island's six corners.
        """
        outer = self._ring(2)
        inner = self._ring(1)
        o = (2 * corner) % 12
        outer = outer[o:] + outer[:o]
        i = corner % 6
        inner = inner[i:] + inner[:i]
        return outer + inner + [(0, 0)]

    def _assign_terrains(self, rng):
        # Where the desert goes is a house rule:
        #   "center"   - always the middle hex
        #   "coast_ng" - anywhere inland (inner ring or centre) so NO coastal hex
        #                is desert (the default)
        #   "none"     - anywhere on the board, coast included
        # The other 18 terrains are shuffled over the remaining hexes.
        mode = getattr(self, "desert_mode", "coast_ng")
        if mode == "center":
            desert_key = (0, 0)
        elif mode == "none":
            desert_key = rng.choice(list(self.hexes.keys()))
        else:                                   # "coast_ng" (default)
            inland = self._ring(1) + [(0, 0)]
            desert_key = rng.choice(inland)
        terrains = [t for t in self.TERRAINS if t != TerrainType.DESERT]
        rng.shuffle(terrains)
        ti = 0
        for key in self.hexes.keys():
            if key == desert_key:
                self.hexes[key] = Hex(key[0], key[1], TerrainType.DESERT)
            else:
                self.hexes[key] = Hex(key[0], key[1], terrains[ti])
                ti += 1

    def _assign_numbers(self, rng):
        # Official layout: the 18 numbers are placed in spiral order from a
        # corner of the island, counterclockwise, skipping the desert.
        spiral = self._spiral(corner=rng.randrange(6))
        seq = list(self.NUMBER_SEQUENCE)
        si = 0
        for key in spiral:
            h = self.hexes[key]
            if h.terrain == TerrainType.DESERT:
                continue
            h.number = seq[si]
            si += 1

    def _build_graph(self):
        # Build vertices and edges using rounded world coords as keys
        vertex_map = {}  # rounded point -> key
        edge_map = {}
        # vertex: point -> list of adjacent hex coords
        v_adj = {}  # point -> set of (q,r)
        e_adj = {}  # frozenset of two points -> list of adjacent hex coords

        for (q, r), h in self.hexes.items():
            cx, cy = axial_to_pixel(q, r)
            corners = hex_corners(cx, cy)
            for i in range(6):
                p1 = round_pt(corners[i])
                p2 = round_pt(corners[(i + 1) % 6])
                # vertex p1 belongs to this hex
                v_adj.setdefault(p1, set()).add((q, r))
                # edge between p1 and p2 belongs to this hex
                ek = frozenset([p1, p2])
                e_adj.setdefault(ek, set()).add((q, r))

        # Assign canonical keys (just use the rounded point tuple for vertices)
        for pt, hexes in v_adj.items():
            self.vertices[pt] = {
                "hexes": hexes,
                "building": None,  # None / "settlement" / "city"
                "owner": None,
            }
        for ek, hexes in e_adj.items():
            self.edges[ek] = {
                "hexes": hexes,
                "road_owner": None,
            }

    def get_hex(self, q, r):
        return self.hexes.get((q, r))

    def hexes_with_number(self, number):
        return [h for h in self.hexes.values() if h.number == number and not h.has_robber]

    def neighbors_hex(self, q, r):
        result = []
        for dq, dr in HEX_NEIGHBORS:
            h = self.hexes.get((q + dq, r + dr))
            if h is not None:
                result.append(h)
        return result

    def vertices_of_hex(self, q, r):
        cx, cy = axial_to_pixel(q, r)
        corners = hex_corners(cx, cy)
        return [round_pt(c) for c in corners]

    def edges_of_hex(self, q, r):
        cx, cy = axial_to_pixel(q, r)
        corners = hex_corners(cx, cy)
        pts = [round_pt(c) for c in corners]
        result = []
        for i in range(6):
            result.append(frozenset([pts[i], pts[(i + 1) % 6]]))
        return result

    def adjacent_vertices(self, vertex):
        """Vertices adjacent to this vertex (connected by an edge that exists)."""
        # find edges containing this vertex
        adj = set()
        for ek, info in self.edges.items():
            if vertex in ek:
                other = [p for p in ek if p != vertex][0]
                adj.add(other)
        return adj

    def adjacent_hexes_of_vertex(self, vertex):
        return self.vertices[vertex]["hexes"]

    def move_robber(self, q, r):
        # clear old
        for h in self.hexes.values():
            h.has_robber = False
        h = self.hexes[(q, r)]
        h.has_robber = True
        self.robber_hex = (q, r)

    def __repr__(self):
        return f"Board({len(self.hexes)} hexes, {len(self.vertices)} vertices, {len(self.edges)} edges)"
