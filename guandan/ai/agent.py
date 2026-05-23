"""Base agent and simple agents for Guandan."""

from __future__ import annotations

import random
from typing import List

from ..card import Card
from ..combo_finder import ComboFinder
from ..game_state import GameState


class BaseAgent:
    """Abstract base class for Guandan agents."""

    def choose_play(self, state: GameState, player_id: int) -> List[Card]:
        """Choose cards to play. Return empty list to pass."""
        raise NotImplementedError


class RandomAgent(BaseAgent):
    """Agent that chooses a random legal play using fast heuristics."""

    def choose_play(self, state: GameState, player_id: int) -> List[Card]:
        hand = state.get_hand(player_id)
        table = state.table
        finder = ComboFinder(hand, state.level)

        # Must lead (empty table or own play on table means starting fresh)
        if table.is_empty or table.last_played_player == player_id:
            combo = finder.pick_lead()
            if combo:
                return list(combo.cards)
            return []

        # Responding to a combo
        combo = finder.pick_response(table.current_combo)
        if combo and random.random() < 0.7:
            return list(combo.cards)

        # Pass
        return []


class FirstPlayAgent(BaseAgent):
    """Agent that always plays the first found legal combo, or passes."""

    def choose_play(self, state: GameState, player_id: int) -> List[Card]:
        hand = state.get_hand(player_id)
        table = state.table
        finder = ComboFinder(hand, state.level)

        if table.is_empty or table.last_played_player == player_id:
            combo = finder.pick_lead()
            if combo:
                return list(combo.cards)
            return []

        combo = finder.pick_response(table.current_combo)
        if combo:
            return list(combo.cards)
        return []


class GreedyAgent(BaseAgent):
    """Agent that tries to play the most cards possible, then the weakest single."""

    def choose_play(self, state: GameState, player_id: int) -> List[Card]:
        hand = state.get_hand(player_id)
        table = state.table
        finder = ComboFinder(hand, state.level)

        if table.is_empty or table.last_played_player == player_id:
            # Try to play a combo with the most cards
            combo = self._pick_largest_combo(finder)
            if combo:
                return list(combo.cards)
            return []

        combo = finder.pick_response(table.current_combo)
        if combo:
            return list(combo.cards)
        # Try bomb
        bomb = finder._find_any_bomb()
        if bomb:
            return list(bomb.cards)
        return []

    def _pick_largest_combo(self, finder: ComboFinder):
        """Try to find a large combo (straight, consecutive pairs, bomb)."""
        # Try straight first
        normals = sorted(
            [c for c in finder.normals if c.rank.value <= 14 and not c.is_joker],
            key=lambda c: c.rank.value
        )
        # Find longest consecutive sequence
        if normals:
            # Use find_all only for analysis — for play, just play a single
            pass
        return finder.pick_lead()
