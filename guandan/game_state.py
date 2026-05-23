"""Full game state snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .card import Card
from .combo import Combo
from .table import TableState


@dataclass
class GameState:
    """Complete state of a Guandan game at a point in time.

    Provides full information for perfect-information simulation.
    For real play, agents receive a filtered view (own hand + public info only).
    """

    level: int
    round_number: int
    hands: Tuple[Tuple[Card, ...], Tuple[Card, ...], Tuple[Card, ...], Tuple[Card, ...]]
    played_cards: List[Card] = field(default_factory=list)
    finished_positions: List[int] = field(default_factory=list)
    current_player: int = 0
    table: TableState = field(default_factory=TableState)
    trick_number: int = 0
    round_over: bool = False

    @property
    def active_players(self) -> List[int]:
        """Return list of player IDs who still have cards."""
        return [
            p for p in range(4)
            if p not in self.finished_positions
        ]

    def is_player_finished(self, player_id: int) -> bool:
        return player_id in self.finished_positions

    def get_hand(self, player_id: int) -> Tuple[Card, ...]:
        return self.hands[player_id]
