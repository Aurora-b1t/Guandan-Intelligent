"""Memory-aware candidate enumerator.

Uses pass history to guide candidate generation:
  - If opponents passed on type X, prefer candidates of type X
  - Track opponent weaknesses discovered through passes
"""

from __future__ import annotations

from typing import List, Tuple

from ..card import Card
from ..combo import Combo, ComboType
from ..combo_finder import ComboFinder
from .candidate_enum import CandidateEnumerator
from .player_view import PlayerView


class MemoryAwareEnumerator(CandidateEnumerator):
    """Enumerate candidates using pass-history to prefer certain types."""

    name = "MemoryAwareEnumerator"
    description = "记忆感知枚举：根据过牌历史调整候选偏好"

    def enumerate(self, hand: Tuple[Card, ...], view: PlayerView,
                  is_lead: bool, table_combo: Combo | None,
                  level: int) -> List[Combo]:
        finder = ComboFinder(hand, level)

        # Base candidates
        if is_lead:
            from .agent import _generate_lead_candidates
            candidates = _generate_lead_candidates(finder, hand)
        else:
            from .agent import _enumerate_responses
            candidates = _enumerate_responses(hand, table_combo, finder, level)

        # If we have tracker data, reorder candidates based on opponent weaknesses
        tracker = view.tracker
        if tracker is None or len(tracker._pass_history) == 0:
            return candidates

        # Analyze opponent weaknesses: which combo types did they pass on?
        weakness_types: set = set()
        for player, passed_on in tracker._pass_history:
            ct = passed_on.combo_type
            if ct != ComboType.ROCKET:  # everyone passes on rockets
                weakness_types.add(ct)

        # Reorder: candidates matching opponent weakness types go first
        def priority(c: Combo) -> int:
            if c.is_bomb:
                return 0  # bombs at end
            if c.combo_type in weakness_types:
                return 2  # type opponent is weak in — prefer
            return 1  # normal

        candidates.sort(key=priority, reverse=True)
        return candidates
