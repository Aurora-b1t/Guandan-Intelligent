"""Trick-level state tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .combo import Combo


@dataclass
class TableState:
    """State of the current trick (round of play).

    Tracks the current combo on the table, who played it, how many
    consecutive passes have occurred, and the full history of this trick.
    """

    current_combo: Optional[Combo] = None
    last_played_player: int = -1
    pass_count: int = 0
    trick_leader: int = 0
    trick_history: List[Tuple[int, Optional[Combo]]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True if no combo is currently on the table (leader about to play)."""
        return self.current_combo is None

    def record_play(self, player_id: int, combo: Combo):
        """Record that a player played a combo."""
        self.current_combo = combo
        self.last_played_player = player_id
        self.pass_count = 0
        self.trick_history.append((player_id, combo))

    def record_pass(self, player_id: int):
        """Record that a player passed."""
        self.pass_count += 1
        self.trick_history.append((player_id, None))

    def reset_for_new_trick(self, leader: int):
        """Reset state for a new trick."""
        self.current_combo = None
        self.last_played_player = -1
        self.pass_count = 0
        self.trick_leader = leader
        self.trick_history.clear()
