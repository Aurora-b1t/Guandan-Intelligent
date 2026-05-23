"""Play scoring: evaluate individual candidate plays.

Core concept: "rounds to empty" (轮次).
  - Bombs cost 0 rounds (playable over anything, anytime).
  - All other combos cost 1 round each.
  - Goal: minimise rounds to empty your hand.
"""

from __future__ import annotations

from typing import Tuple

from ..card import Card
from ..combo import Combo
from .hand_eval import estimate_rounds


PASS_SCORE = 0.0


def score_play(
    candidate: Combo,
    hand_before: Tuple[Card, ...],
    hand_after: Tuple[Card, ...],
    table_combo: Combo | None,
    level: int,
) -> float:
    """Score a candidate play. Higher = better. Negative = pass is preferred.

    Factors (ordered by importance):
      1. round_delta — did we reduce our rounds-to-empty?
      2. bomb_save   — are we wasting a bomb against a non-bomb?
      3. card_usage  — small bonus for using more cards
      4. positional  — leading/following context
    """
    rounds_before = estimate_rounds(hand_before, level)
    rounds_after = estimate_rounds(hand_after, level)
    round_delta = rounds_before - rounds_after  # positive = good

    # 1. Round efficiency (dominant factor)
    round_score = round_delta * 8.0

    # 2. Bomb preservation
    bomb_score = 0.0
    if candidate.is_bomb:
        if table_combo is not None and not table_combo.is_bomb:
            # Using bomb to beat non-bomb — heavy penalty
            # But only if we had other options (approximate: if rounds_after hasn't increased)
            if round_delta >= 0:
                # We're not in a desperate situation
                bomb_score = -10.0
            else:
                # Desperate — bomb is our only way out
                bomb_score = 0.0
        elif table_combo is None:
            # Leading with a bomb — almost always bad
            bomb_score = -12.0
        else:
            # Bomb vs bomb — that's fine
            bomb_score = 2.0

    # 3. Card usage (small bonus, already captured by round_delta mostly)
    usage_score = len(candidate.cards) * 0.3

    # 4. Positional
    positional = 0.0
    if table_combo is None:
        positional += 1.0  # leading bonus
        # Prefer leading with lower-rank combos
        rank_val = candidate.main_rank.value
        if rank_val >= 15:
            positional -= 1.0  # don't lead with jokers
        elif rank_val >= 13:
            positional -= 0.3
    else:
        if not candidate.is_bomb:
            positional += 1.0  # following with same type is good

    return round_score + bomb_score + usage_score + positional


def choose_best_play(
    candidates: list[Combo],
    hand: Tuple[Card, ...],
    table_combo: Combo | None,
    level: int,
    can_pass: bool = False,
) -> Combo | None:
    """Pick the best play from candidates, or None if passing is better."""
    if not candidates:
        return None

    best = None
    best_score = float('-inf')

    for combo in candidates:
        used_ids = {c.id for c in combo.cards}
        hand_after = tuple(c for c in hand if c.id not in used_ids)
        s = score_play(combo, hand, hand_after, table_combo, level)
        if s > best_score:
            best_score = s
            best = combo

    if can_pass and best_score < PASS_SCORE:
        return None
    return best
