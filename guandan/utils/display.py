"""Pretty-printing utilities for cards and combos."""

from __future__ import annotations

from typing import List, Tuple

from ..card import Card, Rank, Suit
from ..combo import Combo, ComboType


def card_to_str(card: Card) -> str:
    return card.display


def cards_to_str(cards: List[Card] | Tuple[Card, ...]) -> str:
    if not cards:
        return "[]"
    return " ".join(c.display for c in cards)


def combo_to_str(combo: Combo) -> str:
    type_names = {
        ComboType.SINGLE: "单张",
        ComboType.PAIR: "对子",
        ComboType.TRIPLE: "三条",
        ComboType.TRIPLE_SINGLE: "三带一",
        ComboType.TRIPLE_PAIR: "三带二",
        ComboType.STRAIGHT: "顺子",
        ComboType.CONSECUTIVE_PAIRS: "连对",
        ComboType.CONSECUTIVE_TRIPLES: "钢板",
        ComboType.NORMAL_BOMB: "炸弹",
        ComboType.STRAIGHT_FLUSH: "同花顺",
        ComboType.ROCKET: "天王炸",
    }
    cn = type_names.get(combo.combo_type, combo.combo_type.name)
    cards = cards_to_str(combo.cards)
    return f"[{cn}] {cards} (主牌:{combo.main_rank.name})"


def hand_summary(cards: Tuple[Card, ...]) -> str:
    """Brief summary of a hand."""
    if not cards:
        return "空手"
    return f"{len(cards)}张: {cards_to_str(sorted(cards, key=lambda c: (c.rank, c.suit)))}"
