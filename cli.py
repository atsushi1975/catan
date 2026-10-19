# cli.py - Simple text-based play for testing game logic
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.board import Board
from game.game import Game
from game.resources import ResourceType

def show(g):
    p = g.current_player()
    print(f"\n=== Turn {g.turn_number} | Phase: {g.phase} | Player: {p.name} (id {p.id}) ===")
    print(f"Dice: {g.dice}  Winner: {g.winner}")
    print("Resources:", {r.value: p.resources[r] for r in ResourceType if r != ResourceType.DESERT})
    print("VP:", p.total_vp(), "Roads left:", p.roads_left, "Settlements:", p.settlements_left, "Cities:", p.cities_left)
    print("Dev cards:", p.dev_cards, "New:", p.new_dev_cards)

def main():
    seed = 42
    g = Game(num_players=4, seed=seed)
    # auto setup randomly-ish: place settlements on first valid spots
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
    print("Setup done.")
    # give current player resources for testing
    while g.winner is None:
        show(g)
        p = g.current_player()
        if g.phase == "roll":
            cmd = input("Command (roll / quit): ").strip()
            if cmd == "quit":
                break
            if cmd == "roll":
                total = g.roll_dice()
                print("Rolled:", total)
                # give some resources to current player for testing
                for r in ResourceType:
                    if r != ResourceType.DESERT:
                        p.resources[r] += 2
            continue
        cmd = input("Command (build road/settle/city, buydev, end, status, quit): ").strip()
        if cmd == "quit":
            break
        if cmd == "end":
            g.end_turn()
        elif cmd == "status":
            pass
        elif cmd == "build road":
            # find first buildable edge
            done = False
            for ek in b.edges:
                if b.edges[ek]["road_owner"] is None and g._road_adjacent_to_player(ek, p.id):
                    if g.build_road_at(ek):
                        print("Road built")
                        done = True
                        break
            if not done:
                print("No buildable road")
        elif cmd == "build settle":
            done = False
            for v in b.vertices:
                if b.vertices[v]["building"] is None and g._distance_rule_ok(v):
                    if g._settlement_adjacent_to_player_road(v, p.id):
                        if g.build_settlement_at(v):
                            print("Settlement built")
                            done = True
                            break
            if not done:
                print("No buildable settlement")
        elif cmd == "build city":
            done = False
            for v in b.vertices:
                if b.vertices[v]["building"] == "settlement" and b.vertices[v]["owner"] == p.id:
                    if g.build_city_at(v):
                        print("City built")
                        done = True
                        break
            if not done:
                print("No buildable city")
        elif cmd == "buydev":
            c = g.buy_dev_card_action()
            print("Bought:", c)
        else:
            print("Unknown command")
    print("Game over. Winner:", g.winner)

if __name__ == "__main__":
    main()
