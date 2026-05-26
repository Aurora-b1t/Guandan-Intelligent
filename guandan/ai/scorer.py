"""Play scoring with tunable parameters.

Core concept: "rounds to empty" (轮次).
  - Bombs cost 0 rounds (playable over anything, anytime).
  - All other combos cost 1 round each.
  - Goal: minimise rounds to empty your hand.
"""

from __future__ import annotations

from typing import Tuple

from ..card import Card, effective_rank
from ..combo import Combo
from .hand_eval import estimate_rounds
from .params import AIParams, DEFAULT_PARAMS


def score_play(
    candidate: Combo,
    hand_before: Tuple[Card, ...],
    hand_after: Tuple[Card, ...],
    table_combo: Combo | None,
    level: int,
    params: AIParams = DEFAULT_PARAMS,
) -> float:
    """Score a candidate play. Higher = better. Negative = pass is preferred."""
    rounds_before = estimate_rounds(hand_before, level)
    rounds_after = estimate_rounds(hand_after, level)
    round_delta = rounds_before - rounds_after

    round_score = round_delta * params.round_weight

    bomb_score = 0.0
    if candidate.is_bomb:
        if table_combo is not None and not table_combo.is_bomb:
            if round_delta >= 0:
                bomb_score = params.bomb_overuse_penalty
            else:
                bomb_score = 0.0
        elif table_combo is None:
            bomb_score = params.bomb_lead_penalty
        else:
            bomb_score = params.bomb_vs_bomb_bonus

    usage_score = candidate.length * params.card_usage_weight

    positional = 0.0
    if table_combo is None:
        positional += params.lead_bonus
        rv = effective_rank(candidate.main_rank, level)
        if rv >= 15:
            positional += params.joker_lead_penalty
        elif rv >= 13:
            positional += params.high_rank_lead_penalty
    else:
        if not candidate.is_bomb:
            positional += params.follow_bonus

    return round_score + bomb_score + usage_score + positional


def choose_best_play(
    candidates: list[Combo],
    hand: Tuple[Card, ...],
    table_combo: Combo | None,
    level: int,
    can_pass: bool = False,
    params: AIParams = DEFAULT_PARAMS,
) -> Combo | None:
    """Pick the best play from candidates, or None if passing is better."""
    if not candidates:
        return None

    best = None
    best_score = float('-inf')

    for combo in candidates:
        used_ids = {c.id for c in combo.cards}
        hand_after = tuple(c for c in hand if c.id not in used_ids)
        s = score_play(combo, hand, hand_after, table_combo, level, params)
        if s > best_score:
            best_score = s
            best = combo

    if can_pass and best_score < params.pass_threshold:
        return None
    return best
