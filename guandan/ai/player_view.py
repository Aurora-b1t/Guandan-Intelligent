"""Restricted game view for AI agents.

AI agents must NOT see other players' hands — only public information.
PlayerView masks opponent hands, exposing only hand sizes.
"""

from __future__ import annotations

from typing import List, Tuple

from ..card import Card
from ..combo import Combo
from ..game_state import GameState
from ..table import TableState
from .action_log import ActionLog, CardTracker


class PlayerView:
    """A filtered view of the game state for a specific player.

    Exposes:
      - Own hand (full cards)
      - Table state (public)
      - Action log + CardTracker (memory)
      - Other players' hand sizes (public)
      - Level, trick number, finished positions (public)

    Hidden:
      - Other players' specific cards
    """

    def __init__(self, state: GameState, player_id: int, action_log: ActionLog = None):
        self._state = state
        self.player_id = player_id
        self.level = state.level
        self.round_number = state.round_number
        self.trick_number = state.trick_number
        self.table = state.table
        self.current_player = state.current_player
        self.finished_positions = list(state.finished_positions)
        self.played_cards = list(state.played_cards)

        # Own hand
        self.my_hand: Tuple[Card, ...] = state.hands[player_id]

        # Opponent sizes
        self._opponent_sizes: dict[int, int] = {}
        for p in range(4):
            if p != player_id:
                self._opponent_sizes[p] = len(state.hands[p])

        # Memory module
        self.action_log = action_log
        self.tracker = CardTracker(self.my_hand, action_log) if action_log else None
        if self.tracker:
            self.tracker.set_opponent_sizes(
                {p: self._opponent_sizes[p] for p in range(4) if p != player_id}
            )

    @property
    def active_players(self) -> List[int]:
        return [p for p in range(4) if p not in self.finished_positions]

    @property
    def hands(self) -> tuple:
        """Returns a tuple mimicking state.hands but with opponent hands masked.
        AI should use self.my_hand and self.get_hand(player_id).
        """
        result = []
        for p in range(4):
            if p == self.player_id:
                result.append(self.my_hand)
            else:
                result.append(tuple())
        return tuple(result)

    def get_hand(self, player_id: int) -> Tuple[Card, ...]:
        if player_id == self.player_id:
            return self.my_hand
        return tuple()

    def opponent_hand_size(self, player_id: int) -> int:
        return self._opponent_sizes.get(player_id, 0)

    def is_player_finished(self, player_id: int) -> bool:
        return player_id in self.finished_positions

    def to_json(self) -> dict:
        """Serialize for the debug panel."""
        player_names = ['你', 'AI-右家', 'AI-对家', 'AI-左家']
        return {
            "player_id": self.player_id,
            "player_name": player_names[self.player_id],
            "my_hand_size": len(self.my_hand),
            "my_hand": [c.display for c in self.my_hand],
            "opponents": [
                {"id": p, "name": player_names[p], "hand_size": self._opponent_sizes[p]}
                for p in range(4) if p != self.player_id
            ],
            "table": str(self.table.current_combo) if self.table.current_combo else "空",
            "can_pass": not self.table.is_empty and self.table.last_played_player != self.player_id,
            "level": self.level,
            "finished": self.finished_positions,
            "played_count": len(self.played_cards),
        }
