"""Score calculation and level progression for Guandan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from . import constants


@dataclass
class RoundResult:
    """Result of a single round."""
    positions: List[int]  # [头游, 二游, 三游, 末游] — player IDs in finish order
    winning_team: int     # 0 or 1
    level_change: int     # levels gained by winning team


def calculate_result(finished_positions: List[int]) -> RoundResult:
    """Calculate round result from finish order.

    finished_positions: player IDs in order of finishing [1st, 2nd, 3rd].
    The 4th player (末游) is the one not in the list.

    Level advancement:
      - 头游+二游 (same team): advance 3 levels (双上/双贡)
      - 头游+三游 (same team): advance 2 levels
      - 头游 only (partner is 末游): advance 1 level
    """
    if len(finished_positions) != 3:
        raise ValueError(f"Expected 3 finished positions, got {len(finished_positions)}")

    # Determine 末游 (last place)
    all_players = set(range(4))
    last_player = (all_players - set(finished_positions)).pop()
    all_positions = finished_positions + [last_player]

    first = finished_positions[0]
    first_team = constants.TEAMS[first]

    # Check if teammate is 2nd
    second = finished_positions[1] if len(finished_positions) > 1 else None
    third = finished_positions[2] if len(finished_positions) > 2 else None

    if second is not None and constants.TEAMS[second] == first_team:
        level_change = 3  # 双上
    elif third is not None and constants.TEAMS[third] == first_team:
        level_change = 2
    else:
        level_change = 1  # partner was last

    return RoundResult(
        positions=all_positions,
        winning_team=first_team,
        level_change=level_change,
    )


def advance_level(current_level: int, level_change: int) -> int:
    """Advance the level. Levels go 2 through A (2-14)."""
    new_level = current_level + level_change
    if new_level > constants.HIGHEST_LEVEL:
        return constants.HIGHEST_LEVEL
    return new_level


def is_game_won(team_level_after_win: int) -> bool:
    """Game is won when a team wins a round while at level A (14) or higher.

    Called BEFORE advancing the level: if the team is at level A and wins,
    they conquer the game.
    """
    return team_level_after_win >= constants.HIGHEST_LEVEL
