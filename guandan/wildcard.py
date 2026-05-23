"""Wild card identification utility."""

from .card import Card


def is_wild(card: Card, level: int) -> bool:
    """Check if a card is wild (万能牌/逢人配) at the given level.

    The heart-suit level-rank card is the wild card.
    There are exactly 2 wild cards in the entire deck (one per deck).
    """
    return card.is_wild(level)
