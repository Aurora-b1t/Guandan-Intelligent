"""IS-MCTS: Information Set Monte Carlo Tree Search.

Builds on the MC framework with a search tree:
  Select → Expand → Simulate → Backpropagate

Key parameters:
  max_iterations: max tree iterations
  time_limit_ms: time budget
  ucb_c: exploration constant for UCB
"""

from __future__ import annotations

import math
import random
import time
from typing import List, Optional, Tuple

from ..card import Card
from ..combo import Combo
from ..combo_finder import ComboFinder
from ..combo_compare import can_beat
from ..game_state import GameState
from ..rules import RulesEngine
from ..score import calculate_result
from ..table import TableState
from .player_view import PlayerView
from .sampler import Sampler, create_sampler
from .logger import ai_log


class ISMCTSDecider:
    """IS-MCTS decision maker.

    Composes: sampler + inner decider + enumerator + UCB search tree.
    """

    name = "IS-MCTS"
    description = "信息集MC树搜索：UCB选择→展开→模拟→回传"

    def __init__(self, sampler: Sampler = None, inner=None, enumerator=None,
                 max_iterations: int = 500, time_limit_ms: int = 10000,
                 ucb_c: float = 1.4, config: dict = None):
        self.sampler = sampler or create_sampler("random")
        self.inner = inner
        self.enumerator = enumerator
        self.max_iterations = max_iterations
        self.time_limit_ms = time_limit_ms
        self.ucb_c = ucb_c
        self._config = config

    def choose_play(self, view: PlayerView):
        result = self.analyze(view)
        if result.choice and result.choice.combo_type != "PASS":
            card_ids = set(result.choice.card_ids)
            return [c for c in view.my_hand if c.id in card_ids]
        return []

    def analyze(self, view: PlayerView):
        t_start = time.time()
        pid = view.player_id
        hand = view.my_hand
        level = view.level
        table = view.table
        finder = ComboFinder(hand, level)

        ai_log(pid, "decision_start", agent="IS-MCTS",
               hand_size=len(hand), max_iters=self.max_iterations)

        # Generate root candidates
        is_lead = table.is_empty or table.last_played_player == pid
        table_combo = table.current_combo if not is_lead else None

        if self.enumerator:
            try:
                candidates = self.enumerator.enumerate(hand, view, is_lead, table_combo, level)
            except TypeError:
                candidates = self.enumerator.enumerate(hand, None, is_lead, table_combo, level)
        elif is_lead:
            from .agent import _generate_lead_candidates
            candidates = _generate_lead_candidates(finder, hand)
        else:
            from .agent import _enumerate_responses
            candidates = _enumerate_responses(hand, table_combo, finder, level)

        can_pass = table_combo is not None and table.last_played_player != pid

        # Build root node
        sim_state = _clone_state(view._state)
        root = _Node(sim_state, pid, view, self.ucb_c)

        # Expand root with candidates
        for c in candidates:
            child_state = _clone_state(sim_state)
            _apply_play(child_state, pid, c)
            root.add_child(c, child_state)

        if can_pass:
            # Pass action
            pass_state = _clone_state(sim_state)
            pass_state.table.record_pass(pid)
            pass_state.current_player = (pid + 1) % 4
            root.add_child(None, pass_state)  # None = pass

        # Main MCTS loop
        iterations = 0
        while iterations < self.max_iterations:
            if time.time() - t_start > self.time_limit_ms / 1000:
                break

            # Select
            node = self._select(root)

            # Expand (if node has untried actions)
            if node.untried:
                node = self._expand(node, view)

            # Simulate
            result = self._simulate(node, view)

            # Backpropagate
            self._backpropagate(node, result, pid)

            iterations += 1

        elapsed = (time.time() - t_start) * 1000
        timed_out = iterations >= self.max_iterations

        # Build results from root children
        from .models.interface import AnalyzeResult, CandidateResult
        crs = []
        best_combo = None
        best_visits = -1

        for combo, child in root.children:
            wr = child.wins / child.visits if child.visits > 0 else 0.0
            if combo is None:
                crs.append(CandidateResult(combo_type="PASS", cards=[], card_ids=[],
                                           win_rate=wr, score=wr,
                                           reasoning=f"IS-MCTS: {child.wins}/{child.visits}"))
            else:
                crs.append(CandidateResult(
                    combo_type=combo.combo_type.name,
                    cards=[x.display for x in combo.cards],
                    card_ids=[x.id for x in combo.cards],
                    win_rate=wr, score=wr,
                    reasoning=f"IS-MCTS: {child.wins}/{child.visits} visits"))
            if child.visits > best_visits:
                best_visits = child.visits
                best_combo = combo

        crs.sort(key=lambda r: r.win_rate or 0, reverse=True)

        ai_log(pid, "decision_end", agent="IS-MCTS",
               candidates_scored=[{"type": c.combo_type, "cards": c.cards,
                                   "win_rate": round(c.win_rate or 0, 3)} for c in crs],
               choice=(best_combo.combo_type.name if best_combo else "PASS"),
               choice_cards=[x.display for x in best_combo.cards] if best_combo else [],
               choice_win_rate=round(best_visits / iterations if iterations > 0 else 0, 3),
               elapsed_ms=round(elapsed, 1),
               timed_out=timed_out, iterations=iterations)

        return AnalyzeResult(
            candidates=crs,
            choice=crs[0] if crs else None,
            pass_chosen=(best_combo is None),
            metrics={"elapsed_ms": elapsed, "iterations": iterations, "timed_out": timed_out},
            model_name="IS-MCTS")

    def _select(self, node: _Node) -> _Node:
        """UCB descent to a leaf node."""
        while node.children and not node.untried:
            node = node.best_child()
        return node

    def _expand(self, node: _Node, view: PlayerView) -> _Node:
        """Expand one untried action into a child node."""
        if not node.untried:
            return node
        # Pick one untried combo (random for exploration diversity)
        combo = node.untried.pop(random.randint(0, len(node.untried) - 1))

        child_state = _clone_state(node.state)
        if combo is None:
            # Pass
            # Find current player
            current = _next_active(child_state, node.state.current_player)
            child_state.table.record_pass(current)
            child_state.current_player = (current + 1) % 4
        else:
            current = _next_active(child_state, node.state.current_player)
            _apply_play(child_state, current, combo)

        child = node.add_child(combo, child_state)
        return child

    def _simulate(self, node: _Node, view: PlayerView) -> bool:
        """Rollout from this node to terminal, return True if my team wins."""
        pid = view.player_id
        my_team = {0: 0, 1: 1, 2: 0, 3: 1}[pid]
        sim_state = _clone_state(node.state)

        # Deal unseen cards
        sampled = self.sampler.sample(view)
        for p in range(4):
            if p == pid: continue
            sim_state.hands = tuple(
                sampled.get(p, tuple()) if i == p else h
                for i, h in enumerate(sim_state.hands))

        # Simulate to end
        for _ in range(200):
            if len(sim_state.finished_positions) >= 3:
                result = calculate_result(sim_state.finished_positions)
                return result.winning_team == my_team

            table = sim_state.table
            if table.last_played_player >= 0:
                other = [p for p in sim_state.active_players if p != table.last_played_player]
                if table.pass_count >= len(other):
                    sim_state.current_player = table.last_played_player
                    _start_new_trick(sim_state)
                    continue

            current = _next_active(sim_state, sim_state.current_player)
            hand = sim_state.hands[current]

            # Use inner decider
            sim_view = PlayerView(sim_state, current)
            if self.inner:
                play_cards = self.inner.choose_play(sim_view)
            else:
                from .agent import BlindAgent
                play_cards = BlindAgent().choose_play(sim_view)

            rules = RulesEngine(sim_state.level)
            result = rules.validate_play(
                cards=play_cards, hand=hand, table_state=sim_state.table,
                player_id=current, finished_positions=sim_state.finished_positions)
            if result.is_legal and play_cards:
                _apply_play(sim_state, current, result.resolved_combo)
            else:
                sim_state.table.record_pass(current)
                sim_state.current_player = (current + 1) % 4

        return _did_team_win(sim_state, my_team)

    def _backpropagate(self, node: _Node, won: bool, root_pid: int):
        """Propagate result up the tree."""
        my_team = {0: 0, 1: 1, 2: 0, 3: 1}[root_pid]
        while node is not None:
            node.visits += 1
            # Win counts from the perspective of the player who acted at this node
            current = _next_active(node.state, node.state.current_player)
            current_team = {0: 0, 1: 1, 2: 0, 3: 1}[current]
            if (won and current_team == my_team) or (not won and current_team != my_team):
                node.wins += 1
            node = node.parent


# ==================================================================
# Tree node
# ==================================================================

class _Node:
    def __init__(self, state: GameState, player_id: int, view: PlayerView, ucb_c: float):
        self.state = state
        self.player_id = player_id
        self.parent: Optional[_Node] = None
        self.children: List[Tuple[Combo | None, _Node]] = []
        self.untried: List[Combo | None] = []  # candidates not yet expanded
        self.visits = 0
        self.wins = 0
        self._ucb_c = ucb_c

    def add_child(self, combo: Combo | None, state: GameState) -> _Node:
        child = _Node(state, self.player_id, None, self._ucb_c)
        child.parent = self
        self.children.append((combo, child))
        return child

    def best_child(self) -> _Node:
        """Select child with highest UCB."""
        best = None
        best_ucb = -float('inf')
        log_visits = math.log(max(1, self.visits))
        for combo, child in self.children:
            if child.visits == 0:
                ucb = float('inf')  # visit unexplored children first
            else:
                exploit = child.wins / child.visits
                explore = self._ucb_c * math.sqrt(log_visits / child.visits)
                ucb = exploit + explore
            if ucb > best_ucb:
                best_ucb = ucb
                best = child
        return best


# ==================================================================
# Helpers (duplicated from agent.py for independence)
# ==================================================================

def _clone_state(state: GameState) -> GameState:
    t = TableState(
        current_combo=state.table.current_combo,
        last_played_player=state.table.last_played_player,
        pass_count=state.table.pass_count,
        trick_leader=state.table.trick_leader,
        trick_history=list(state.table.trick_history))
    return GameState(
        level=state.level, round_number=state.round_number,
        hands=state.hands, played_cards=list(state.played_cards),
        finished_positions=list(state.finished_positions),
        current_player=state.current_player, table=t, trick_number=state.trick_number)


def _apply_play(state: GameState, pid: int, combo: Combo):
    hand = state.hands[pid]
    ids = {c.id for c in combo.cards}
    new = tuple(c for c in hand if c.id not in ids)
    state.hands = tuple(new if i == pid else h for i, h in enumerate(state.hands))
    state.played_cards.extend(combo.cards)
    state.table.record_play(pid, combo)
    state.current_player = (pid + 1) % 4
    if not new:
        state.finished_positions.append(pid)


def _start_new_trick(state: GameState):
    leader = _next_active(state, state.current_player)
    state.table.reset_for_new_trick(leader)
    state.trick_number += 1
    state.current_player = leader


def _next_active(state: GameState, start: int) -> int:
    for _ in range(4):
        if start not in state.finished_positions:
            return start
        start = (start + 1) % 4
    return start


def _did_team_win(state: GameState, my_team: int) -> bool:
    if len(state.finished_positions) >= 3:
        result = calculate_result(state.finished_positions)
        return result.winning_team == my_team
    if state.finished_positions:
        return {0: 0, 1: 1, 2: 0, 3: 1}[state.finished_positions[0]] == my_team
    return False
