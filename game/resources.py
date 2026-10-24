# game/resources.py

from enum import Enum
from collections import Counter

class ResourceType(Enum):
    WOOD = "wood"
    BRICK = "brick"
    SHEEP = "sheep"
    WHEAT = "wheat"
    ORE = "ore"
    DESERT = "desert"  # not a real resource, used for terrain

class TerrainType(Enum):
    FOREST = "forest"      # produces WOOD
    HILLS = "hills"        # produces BRICK
    PASTURE = "pasture"    # produces SHEEP
    FIELDS = "fields"      # produces WHEAT
    MOUNTAINS = "mountains"  # produces ORE
    DESERT = "desert"      # produces nothing

TERRAIN_TO_RESOURCE = {
    TerrainType.FOREST: ResourceType.WOOD,
    TerrainType.HILLS: ResourceType.BRICK,
    TerrainType.PASTURE: ResourceType.SHEEP,
    TerrainType.FIELDS: ResourceType.WHEAT,
    TerrainType.MOUNTAINS: ResourceType.ORE,
    TerrainType.DESERT: None,
}

# Building costs
ROAD_COST = {ResourceType.WOOD: 1, ResourceType.BRICK: 1}
SETTLEMENT_COST = {ResourceType.WOOD: 1, ResourceType.BRICK: 1,
                   ResourceType.SHEEP: 1, ResourceType.WHEAT: 1}
CITY_COST = {ResourceType.WHEAT: 2, ResourceType.ORE: 3}
DEV_CARD_COST = {ResourceType.SHEEP: 1, ResourceType.WHEAT: 1, ResourceType.ORE: 1}

# Victory points
VP_SETTLEMENT = 1
VP_CITY = 2
VP_LARGEST_ARMY = 2
VP_LONGEST_ROAD = 2
LONGEST_ROAD_MIN = 5     # roads in a row needed for the title
LARGEST_ARMY_MIN = 3     # knights played needed for the title
VICTORY_TARGET = 10

# Player limits
MAX_ROADS = 15
MAX_SETTLEMENTS = 5
MAX_CITIES = 4

# Bank trade ratio
BANK_TRADE_RATIO = 4
PORT_GENERIC_RATIO = 3
PORT_SPECIFIC_RATIO = 2
