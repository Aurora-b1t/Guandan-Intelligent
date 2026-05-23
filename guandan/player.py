"""Player model for Guandan."""

from __future__ import annotations

from . import constants


class Player:
    """Represents a player at the table."""

    def __init__(self, player_id: int):
        if not 0 <= player_id < constants.NUM_PLAYERS:
            raise ValueError(f"Player id must be 0-3, got {player_id}")
        self.player_id = player_id
        self.team_id = constants.TEAMS[player_id]

    def is_partner(self, other: Player) -> bool:
        return self.team_id == other.team_id

    @property
    def partner_id(self) -> int:
        return (self.player_id + 2) % 4
