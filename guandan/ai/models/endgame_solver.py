"""Endgame exact solver using minimax search.

For hands with ≤6 cards per player, enumerate all possible play sequences
to find the theoretical optimal play.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from ...card import Card
from ...combo import Combo
from ...combo_finder import ComboFinder
from ...combo_compare import can_beat
from ...game_state import GameState
from ..player_view import PlayerView
from .interface import TestableModel, AnalyzeResult, CandidateResult


class EndgameExactSolver(TestableModel):
    """Exact minimax solver — unweighted, pure computation."""
    """Minimax search for endgame positions (≤6 cards per player)."""

    name = "endgame_exact"
    description = "终局精确求解器：≤6张手牌时极小化极大搜索全分支"
    default_config = {"max_depth": 20, "max_cards": 6}
    MAX_CARDS = 6

    def analyze(self, view: PlayerView) -> AnalyzeResult:
        t0 = time.time()
        pid = view.player_id
        state = view._state
        hand = view.my_hand
        level = view.level
        table = view.table
        finder = ComboFinder(hand, level)

        # Check hand size
        total_cards = sum(len(state.hands[p]) for p in range(4))
        if total_cards > 24:  # 6 per player × 4
            return AnalyzeResult(
                candidates=[],
                metrics={"error": f"Too many cards ({total_cards}) for exact solve, max {self.MAX_CARDS * 4}"},
                model_name=self.name,
            )

        # Generate candidates
        if table.is_empty or table.last_played_player == pid:
            from ..agent import _generate_lead_candidates
            candidates = _generate_lead_candidates(finder, hand)
            table_combo = None
        else:
            from ..agent import _enumerate_responses
            candidates = _enumerate_responses(hand, table.current_combo, finder, level)
            table_combo = table.current_combo

        can_pass = table_combo is not None and table.last_played_player != pid

        results = []
        teams = {0: 0, 1: 1, 2: 0, 3: 1}
        my_team = teams[pid]

        for c in candidates:
            # Apply play
            sim_state = self._clone_state(state)
            self._apply_play(sim_state, pid, c)

            # Evaluate outcome
            outcome = self._evaluate(sim_state, (pid + 1) % 4, my_team, 0)
            # Normalize to 0-1 scale
            score = outcome / 10.0 if outcome else 0.0

            results.append(CandidateResult(
                combo_type=c.combo_type.name,
                cards=[x.display for x in c.cards],
                card_ids=[x.id for x in c.cards],
                score=score,
                win_rate=score,
                reasoning=f"精确推演值: {outcome}",
            ))

        results.sort(key=lambda r: r.score or 0, reverse=True)

        if can_pass:
            sim_state = self._clone_state(state)
            sim_state.table.record_pass(pid)
            sim_state.current_player = (pid + 1) % 4
            outcome = self._evaluate(sim_state, (pid + 1) % 4, my_team, 0)
            score = outcome / 10.0 if outcome else 0.0

            results.append(CandidateResult(
                combo_type="PASS", cards=[], card_ids=[],
                score=score, win_rate=score,
                reasoning=f"过牌推演值: {outcome}",
            ))

        best = results[0] if results else None
        return AnalyzeResult(
            candidates=results,
            choice=best,
            pass_chosen=(best.combo_type == "PASS" if best else False),
            metrics={"elapsed_ms": (time.time() - t0) * 1000, "nodes": len(results)},
            model_name=self.name,
        )

    def _evaluate(self, state: GameState, current_pid: int, my_team: int, depth: int) -> int:
        """Recursive evaluation. Returns a heuristic score (higher = better for my_team)."""
        if depth > 20:
            return 0
        if len(state.finished_positions) >= 3:
            from ...score import calculate_result
            result = calculate_result(state.finished_positions)
            teams = {0: 0, 1: 1, 2: 0, 3: 1}
            if result.winning_team == my_team:
                return 10 - depth
            return -10 + depth

        # Find next active player
        for _ in range(4):
            if current_pid not in state.finished_positions:
                break
            current_pid = (current_pid + 1) % 4

        table = state.table
        hand = state.hands[current_pid]
        finder = ComboFinder(hand, state.level)

        # Check trick end
        if table.last_played_player >= 0:
            other_active = [p for p in state.active_players if p != table.last_played_player]
            if table.pass_count >= len(other_active):
                state.current_player = table.last_played_player
                from ...game import Game
                # Start new trick manually
                leader = table.last_played_player
                state.table.reset_for_new_trick(leader)
                state.trick_number += 1
                state.current_player = leader
                current_pid = leader
                hand = state.hands[current_pid]
                finder = ComboFinder(hand, state.level)

        # Generate candidates
        if table.is_empty or table.last_played_player == current_pid:
            from ..agent import _generate_lead_candidates
            candidates = _generate_lead_candidates(finder, hand)
        else:
            from ..agent import _enumerate_responses
            candidates = _enumerate_responses(hand, table.current_combo, finder, state.level)

        can_pass = not table.is_empty and table.last_played_player != current_pid

        best = -999
        teams = {0: 0, 1: 1, 2: 0, 3: 1}
        is_my_team = teams[current_pid] == my_team

        for c in candidates:
            sim = self._clone_state(state)
            self._apply_play(sim, current_pid, c)
            val = self._evaluate(sim, (current_pid + 1) % 4, my_team, depth + 1)
            if is_my_team:
                best = max(best, val)
            else:
                best = max(best, -val)  # opponent's best is our worst

        if can_pass:
            sim = self._clone_state(state)
            sim.table.record_pass(current_pid)
            sim.current_player = (current_pid + 1) % 4
            val = self._evaluate(sim, (current_pid + 1) % 4, my_team, depth + 1)
            if is_my_team:
                best = max(best, val)
            else:
                best = max(best, -val)

        return best if best > -999 else 0

    def _clone_state(self, state: GameState) -> GameState:
        from ...table import TableState
        t = TableState(
            current_combo=state.table.current_combo,
            last_played_player=state.table.last_played_player,
            pass_count=state.table.pass_count,
            trick_leader=state.table.trick_leader,
            trick_history=list(state.table.trick_history),
        )
        return GameState(
            level=state.level, round_number=state.round_number,
            hands=state.hands, played_cards=list(state.played_cards),
            finished_positions=list(state.finished_positions),
            current_player=state.current_player, table=t,
            trick_number=state.trick_number,
        )

    def _apply_play(self, state: GameState, pid: int, combo: Combo):
        hand = state.hands[pid]
        ids = {c.id for c in combo.cards}
        new_hand = tuple(c for c in hand if c.id not in ids)
        state.hands = tuple(new_hand if i == pid else h for i, h in enumerate(state.hands))
        state.played_cards.extend(combo.cards)
        state.table.record_play(pid, combo)
        state.current_player = (pid + 1) % 4
        if not new_hand:
            state.finished_positions.append(pid)
