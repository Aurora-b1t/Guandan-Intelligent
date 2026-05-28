"""Shared state-manipulation helpers for simulation and game orchestration.

These were previously duplicated across agent.py, ismcts.py, mc_decider.py,
endgame_solver.py, interactive.py, and arena_api.py.
"""

from typing import List, Tuple

from .card import Card
from .combo import Combo
from .game_state import GameState
from .score import calculate_result
from .table import TableState

_TEAMS = {0: 0, 1: 1, 2: 0, 3: 1}


def clone_state(state: GameState) -> GameState:
    """Deep-copy a GameState for simulation.

    Card objects are frozen dataclasses, so shallow-copying the hand tuples
    and played_cards list is safe — no need for deepcopy.
    """
    new_table = TableState(
        current_combo=state.table.current_combo,
        last_played_player=state.table.last_played_player,
        pass_count=state.table.pass_count,
        trick_leader=state.table.trick_leader,
        trick_history=list(state.table.trick_history),
    )
    return GameState(
        level=state.level,
        round_number=state.round_number,
        hands=state.hands,
        played_cards=list(state.played_cards),
        finished_positions=list(state.finished_positions),
        current_player=state.current_player,
        table=new_table,
        trick_number=state.trick_number,
    )


def apply_play(state: GameState, player_id: int, combo: Combo):
    """Apply a play (mutates state in-place)."""
    hand = state.hands[player_id]
    played_ids = {c.id for c in combo.cards}
    new_hand = tuple(c for c in hand if c.id not in played_ids)
    state.hands = tuple(
        new_hand if i == player_id else h for i, h in enumerate(state.hands)
    )
    state.played_cards.extend(combo.cards)
    state.table.record_play(player_id, combo)
    state.current_player = (player_id + 1) % 4
    if not new_hand:
        state.finished_positions.append(player_id)


def start_new_trick(state: GameState):
    """Begin a new trick, resetting the table and finding the next leader."""
    leader = next_active_player(state, state.current_player)
    state.table.reset_for_new_trick(leader)
    state.trick_number += 1
    state.current_player = leader


def next_active_player(state: GameState, from_player: int) -> int:
    """Find the next non-finished player clockwise from ``from_player``."""
    for _ in range(4):
        if from_player not in state.finished_positions:
            return from_player
        from_player = (from_player + 1) % 4
    return from_player


def did_team_win(state: GameState, my_team: int) -> bool:
    """Check whether *my_team* won based on finish order so far."""
    if len(state.finished_positions) >= 3:
        result = calculate_result(state.finished_positions)
        return result.winning_team == my_team
    if state.finished_positions:
        return _TEAMS[state.finished_positions[0]] == my_team
    return False
