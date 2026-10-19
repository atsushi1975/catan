# game/trade.py
from .resources import ResourceType, BANK_TRADE_RATIO, PORT_GENERIC_RATIO, PORT_SPECIFIC_RATIO

ALL_RESOURCES = [ResourceType.WOOD, ResourceType.BRICK, ResourceType.SHEEP,
                 ResourceType.WHEAT, ResourceType.ORE]

def bank_trade(player, give_rt, receive_rt, ratio=BANK_TRADE_RATIO):
    """Bank trade: give ratio of one resource for 1 of another."""
    if give_rt == receive_rt:
        return False
    if player.resources.get(give_rt, 0) < ratio:
        return False
    player.resources[give_rt] -= ratio
    player.resources[receive_rt] += 1
    return True

def port_trade_ratio(player, port_type):
    """Determine trade ratio for a player at a port."""
    # port_type: None (no port), "generic", or a ResourceType for 2:1
    if port_type is None:
        return BANK_TRADE_RATIO
    if port_type == "generic":
        return PORT_GENERIC_RATIO
    return PORT_SPECIFIC_RATIO

def player_trade(offer_player, receive_player, offer, request):
    """offer: dict resource->amount from offer_player; request: dict from receive_player."""
    for rt, amt in offer.items():
        if offer_player.resources.get(rt, 0) < amt:
            return False
    for rt, amt in request.items():
        if receive_player.resources.get(rt, 0) < amt:
            return False
    for rt, amt in offer.items():
        offer_player.resources[rt] -= amt
        receive_player.resources[rt] += amt
    for rt, amt in request.items():
        receive_player.resources[rt] -= amt
        offer_player.resources[rt] += amt
    return True
