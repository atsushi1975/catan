# game/player.py
from .resources import (ResourceType, ROAD_COST, SETTLEMENT_COST, CITY_COST,
                        DEV_CARD_COST, MAX_ROADS, MAX_SETTLEMENTS, MAX_CITIES,
                        VP_SETTLEMENT, VP_CITY)

class Player:
    def __init__(self, pid, name, color):
        self.id = pid
        self.name = name
        self.color = color
        self.resources = {rt: 0 for rt in ResourceType if rt != ResourceType.DESERT}
        self.dev_cards = []          # list of card type strings
        self.new_dev_cards = []      # cards bought this turn (can't play same turn)
        self.used_dev_cards = []     # public log of development cards played
        self.knights_played = 0
        self.roads_left = MAX_ROADS
        self.settlements_left = MAX_SETTLEMENTS
        self.cities_left = MAX_CITIES
        self.vp = 0                  # visible VP (settlements, cities, special)
        self.hidden_vp = 0           # VP dev cards
        self.longest_road = False
        self.largest_army = False
        self.played_dev_this_turn = False
        self.free_roads = 0

    def resource_count(self, rt):
        return self.resources.get(rt, 0)

    def total_resources(self):
        return sum(self.resources.values())

    def can_afford(self, cost):
        for rt, amt in cost.items():
            if self.resources.get(rt, 0) < amt:
                return False
        return True

    def pay(self, cost):
        for rt, amt in cost.items():
            self.resources[rt] -= amt

    def gain(self, rt, amount=1):
        if rt in self.resources:
            self.resources[rt] += amount

    def gain_resources(self, res_dict):
        for rt, amt in res_dict.items():
            self.gain(rt, amt)

    def build_road(self):
        if self.roads_left <= 0:
            return False
        if not self.can_afford(ROAD_COST):
            return False
        self.pay(ROAD_COST)
        self.roads_left -= 1
        return True

    def build_settlement(self):
        if self.settlements_left <= 0:
            return False
        if not self.can_afford(SETTLEMENT_COST):
            return False
        self.pay(SETTLEMENT_COST)
        self.settlements_left -= 1
        self.vp += VP_SETTLEMENT
        return True

    def build_city(self):
        if self.cities_left <= 0:
            return False
        if not self.can_afford(CITY_COST):
            return False
        self.pay(CITY_COST)
        self.cities_left -= 1
        self.settlements_left += 1  # city replaces settlement
        self.vp += (VP_CITY - VP_SETTLEMENT)  # net +1
        return True

    def buy_dev_card(self):
        if not self.can_afford(DEV_CARD_COST):
            return False
        self.pay(DEV_CARD_COST)
        return True

    def total_vp(self):
        return self.vp + self.hidden_vp

    def __repr__(self):
        return f"Player({self.id},{self.name},vp={self.total_vp()})"
