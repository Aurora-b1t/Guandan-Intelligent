"""Combo comparison: determine if one combo beats another.

Comparison hierarchy:
1. Rocket (王炸) beats everything; nothing beats a rocket.
2. Any bomb beats any non-bomb.
3. Bomb vs bomb: larger bomb (more cards) wins; same size → compare rank.
4. Non-bomb vs non-bomb: must be same type and same length;
   then compare main_rank. The existing combo holds tie advantage (defender
   needs strictly HIGHER).
"""

from __future__ import annotations

from .card import effective_rank
from .combo import Combo, ComboType


def can_beat(new: Combo, existing: Combo) -> bool:
    """Return True if `new` can legally beat `existing`."""
    # Nothing beats a rocket
    if existing.combo_type == ComboType.ROCKET:
        return False

    # Rocket beats everything
    if new.combo_type == ComboType.ROCKET:
        return True

    # Both are bombs → use bomb comparison
    if new.is_bomb and existing.is_bomb:
        return _compare_bombs(new, existing) > 0

    # Bomb vs non-bomb → bomb always wins
    if new.is_bomb and not existing.is_bomb:
        return True
    if not new.is_bomb and existing.is_bomb:
        return False

    # Both non-bombs → must be exact same type
    if new.combo_type != existing.combo_type:
        return False

    # For sequences (straight, consecutive pairs/triples), lengths must match
    if new.combo_type in (ComboType.STRAIGHT, ComboType.CONSECUTIVE_PAIRS, ComboType.CONSECUTIVE_TRIPLES):
        if new.length != existing.length:
            return False

    new_eff = effective_rank(new.main_rank, new.level)
    exist_eff = effective_rank(existing.main_rank, existing.level)
    return new_eff > exist_eff


def _compare_bombs(a: Combo, b: Combo) -> int:
    """Compare two bombs. Returns >0 if a beats b, <0 if b beats a, 0 if equal."""
    # Different sizes: more cards = bigger bomb
    if a.length != b.length:
        return a.length - b.length
    # Same size: compare effective rank (level-aware)
    a_eff = effective_rank(a.main_rank, a.level)
    b_eff = effective_rank(b.main_rank, b.level)
    return a_eff - b_eff
