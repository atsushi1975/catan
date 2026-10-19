# game/cards.py
from enum import Enum
import random

class DevCardType(Enum):
    KNIGHT = "knight"
    VICTORY_POINT = "victory_point"
    ROAD_BUILDING = "road_building"
    YEAR_OF_PLENTY = "year_of_plenty"
    MONOPOLY = "monopoly"

# Deck composition (standard Catan)
DEV_CARD_DECK = (
    [DevCardType.KNIGHT] * 14 +
    [DevCardType.VICTORY_POINT] * 5 +
    [DevCardType.ROAD_BUILDING] * 2 +
    [DevCardType.YEAR_OF_PLENTY] * 2 +
    [DevCardType.MONOPOLY] * 2
)

def create_dev_deck(seed=None):
    deck = list(DEV_CARD_DECK)
    rng = random.Random(seed)
    rng.shuffle(deck)
    return deck

def draw_dev_card(deck):
    if not deck:
        return None
    return deck.pop()
