"""AI agents for Guandan.

HeuristicAgent: greedy play based on hand-quality scoring.
MonteCarloAgent: sample opponent hands, simulate rollout, pick best play.

Architecture:
  Layer 0: hand_eval.py + opponent.py  — analysis
  Layer 1: combo_finder.py             — candidate generation (existing)
  Layer 2: scorer.py                   — play evaluation
  Layer 3: agent.py                    — decision
"""

from __future__ import annotations

import math
import random
import time
from typing import List, Optional, Tuple

from ..card import Card, Rank
from ..combo import Combo, ComboType
from ..combo_finder import ComboFinder
from ..combo_compare import can_beat
from ..deck import Deck
from ..game_state import GameState
from ..rules import RulesEngine
from ..score import calculate_result
from .scorer import choose_best_play, score_play
from .opponent import CardCounter
from .logger import ai_log
from .player_view import PlayerView
from .params import AIParams, DEFAULT_PARAMS


# ==================================================================
# Base agent
# ==================================================================

class BaseAgent:
    """Abstract base for all agents."""

    def choose_play(self, view: PlayerView) -> List[Card]:
        raise NotImplementedError


def _generate_lead_candidates(finder: ComboFinder, hand: Tuple[Card, ...]) -> List[Combo]:
    """Generate a diverse set of lead candidates WITHOUT calling find_all()."""
    from ..combo_parser import ComboParser
    parser = ComboParser(finder.level)
    candidates: List[Combo] = []
    seen: set = set()

    def add(c: Combo):
        key = (c.combo_type, c.main_rank, c.length)
        if key not in seen:
            seen.add(key)
            candidates.append(c)

    # Singles: try lowest ranks
    singles = sorted(hand, key=lambda c: (c.rank.value, c.suit.value))
    for c in singles[:5]:
        parsed = parser.parse([c])
        if parsed:
            add(parsed)

    # Pairs: lowest rank pair
    by_rank: dict = {}
    for c in hand:
        by_rank.setdefault(c.rank, []).append(c)
    for rank, cards in sorted(by_rank.items(), key=lambda x: x[0].value):
        if len(cards) >= 2:
            parsed = parser.parse(list(cards[:2]))
            if parsed:
                add(parsed)
                break

    # Triples
    for rank, cards in sorted(by_rank.items(), key=lambda x: x[0].value):
        if len(cards) >= 3:
            parsed = parser.parse(list(cards[:3]))
            if parsed:
                add(parsed)
                break

    # Straights
    normals = [c for c in hand if not c.is_wild(finder.level)]
    wilds_list = [c for c in hand if c.is_wild(finder.level)]
    for length in [5, 6, 7]:
        for end in range(length + 2, 15):
            start = end - length + 1
            if start < 3:
                continue
            needed = 0
            subset = []
            for r_val in range(start, end + 1):
                matches = [c for c in normals if c.rank.value == r_val]
                if matches:
                    subset.append(matches[0])
                else:
                    needed += 1
            if needed == len(wilds_list) and len(subset) + needed == length:
                parsed = parser.parse(subset + wilds_list)
                if parsed and parsed.combo_type.name in ('STRAIGHT', 'STRAIGHT_FLUSH'):
                    add(parsed)
                    break
        break  # only try one length

    # Bombs & rocket — excluded from lead candidates
    return candidates


class HeuristicAgent(BaseAgent):
    """Picks the play with the best immediate heuristic score."""

    def __init__(self, params: AIParams = DEFAULT_PARAMS, **kw):
        self.params = params

    def choose_play(self, view: PlayerView) -> List[Card]:
        t0 = time.time()
        pid = view.player_id
        hand = view.my_hand
        table = view.table
        level = view.level
        finder = ComboFinder(hand, level)

        # Log the AI's view
        ai_log(pid, "decision_start", view=view.to_json())

        # Generate candidates — use FAST methods only
        if table.is_empty or table.last_played_player == pid:
            candidates = _generate_lead_candidates(finder, hand)
        else:
            candidates = []
            combo = finder.pick_response(table.current_combo)
            if combo:
                candidates.append(combo)
            bomb = finder._find_any_bomb()
            if bomb and bomb not in candidates:
                candidates.append(bomb)

        can_pass = (not table.is_empty and table.last_played_player != pid)

        # Score candidates
        scored = []
        for c in candidates:
            used_ids = {x.id for x in c.cards}
            hand_after = tuple(x for x in hand if x.id not in used_ids)
            s = score_play(c, hand, hand_after, table.current_combo, level, self.params)
            scored.append((c, s))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Log candidates
        ai_log(pid, "candidates", candidates=[
            {
                "type": c.combo_type.name,
                "cards": [x.display for x in c.cards],
                "length": c.length,
                "main_rank": c.main_rank.name,
                "score": round(s, 2),
            }
            for c, s in scored[:15]
        ])

        best = choose_best_play(candidates, hand, table.current_combo, level, can_pass, self.params)

        elapsed = (time.time() - t0) * 1000
        ai_log(pid, "decision_end",
               choice=("pass" if best is None else f"{best.combo_type.name} {[c.display for c in best.cards]}"),
               elapsed_ms=round(elapsed, 1))

        if best is None:
            return []
        return list(best.cards)


# ==================================================================
# Fast simulation agent (used inside Monte Carlo rollouts)
# ==================================================================

class _FastSimAgent(BaseAgent):
    """Fast agent for Monte Carlo rollouts — uses params but skips estimate_rounds()."""

    def __init__(self, params: AIParams = DEFAULT_PARAMS):
        self.params = params

    def choose_play(self, view: PlayerView) -> List[Card]:
        hand = view.my_hand
        table = view.table
        pid = view.player_id
        level = view.level
        p = self.params
        finder = ComboFinder(hand, level)

        if table.is_empty or table.last_played_player == pid:
            candidates = _generate_lead_candidates(finder, hand)
            table_combo = None
        else:
            candidates = []
            combo = finder.pick_response(table.current_combo)
            if combo: candidates.append(combo)
            bomb = finder._find_any_bomb()
            if bomb and bomb not in candidates:
                candidates.append(bomb)
            table_combo = table.current_combo

        can_pass = (table_combo is not None and table.last_played_player != pid)

        best = None
        best_score = float('-inf')
        total = len(hand)

        for c in candidates:
            eff = (c.length / total) * p.efficiency_weight if total > 0 else 0
            bomb_pen = 0.0
            if c.is_bomb:
                if table_combo is None:
                    bomb_pen = p.bomb_lead_penalty
                elif not table_combo.is_bomb:
                    bomb_pen = p.bomb_overuse_penalty
                else:
                    bomb_pen = p.bomb_vs_bomb_bonus
            usage = c.length * p.card_usage_weight
            pos = p.lead_bonus if table_combo is None else (p.follow_bonus if not c.is_bomb else 0)
            s = eff + bomb_pen + usage + pos
            if s > best_score:
                best_score = s
                best = c

        if best is not None and best_score >= p.pass_threshold:
            return list(best.cards)
        if can_pass and random.random() > p.sim_pass_prob:
            return []
        if best is not None:
            return list(best.cards)
        if hand:
            return [hand[0]]
        return []


# ==================================================================
# MonteCarloAgent — sample + simulate
# ==================================================================

class MonteCarloAgent(BaseAgent):
    """Monte Carlo agent with opponent hand sampling and rollout simulation.

    Algorithm:
      1. Generate candidate plays from my hand
      2. For each candidate:
         a. Sample opponent hands from unseen cards (N times)
         b. For each sample: simulate game to completion
         c. Record whether "my team" won
      3. Pick the candidate with highest win rate
    """

    def __init__(self, num_samples: int = 50, time_limit_ms: float = 3000,
                 params: AIParams = DEFAULT_PARAMS):
        self.num_samples = num_samples
        self.time_limit_ms = time_limit_ms
        self.params = params

    def choose_play(self, view: PlayerView) -> List[Card]:
        t_start = time.time()
        pid = view.player_id
        hand = view.my_hand
        table = view.table
        level = view.level
        ai_log(pid, "decision_start",
               agent="MonteCarlo",
               hand_size=len(hand),
               num_samples=self.num_samples,
               time_limit_ms=self.time_limit_ms)
        finder = ComboFinder(hand, level)

        # Generate candidates
        if table.is_empty or table.last_played_player == pid:
            candidates = _generate_lead_candidates(finder, hand)
        else:
            candidates = []
            combo = finder.pick_response(table.current_combo)
            if combo:
                candidates.append(combo)
            bomb = finder._find_any_bomb()
            if bomb and bomb not in candidates:
                candidates.append(bomb)

        can_pass = (not table.is_empty and table.last_played_player != pid)

        if not candidates and not can_pass:
            return []
        if not candidates:
            return []

        # Add "pass" as a candidate
        all_candidates = list(candidates)
        if can_pass:
            all_candidates.append(None)  # None = pass

        # Build card counter from current view
        counter = CardCounter(hand)
        for p in range(4):
            if p != pid:
                counter.set_opponent_hand_sizes({
                    p: view.opponent_hand_size(p) for p in range(4) if p != pid
                })
        for c in view.played_cards:
            counter._seen.add(c.id)

        # Score each candidate
        results = []
        for candidate in all_candidates:
            if candidate is None:
                # Pass candidate
                results.append((None, 0.0))
                continue

            # Check time
            if time.time() - t_start > self.time_limit_ms / 1000:
                break

            wins = 0
            simulations = 0

            # Run simulations
            for _ in range(self.num_samples):
                if time.time() - t_start > self.time_limit_ms / 1000:
                    break

                sim_result = self._run_simulation(
                    view, candidate, counter
                )
                if sim_result:
                    wins += 1
                simulations += 1

            win_rate = wins / simulations if simulations > 0 else 0.0
            results.append((candidate, win_rate))

        # Pick best
        if not results:
            return []

        best = max(results, key=lambda r: r[1])
        elapsed = (time.time() - t_start) * 1000
        ai_log(pid, "decision_end",
               agent="MonteCarlo",
               candidates_scored=[{
                   "type": (c.combo_type.name if c else "PASS"),
                   "cards": [x.display for x in c.cards] if c else [],
                   "win_rate": round(wr, 3),
               } for c, wr in results],
               choice=(f"{best[0].combo_type.name}" if best[0] else "PASS"),
               elapsed_ms=round(elapsed, 1))
        if best[0] is None:
            return []
        return list(best[0].cards)

    def _run_simulation(
        self,
        view: PlayerView,
        my_play: Combo,
        counter: CardCounter,
    ) -> bool:
        """Run one simulation from the current state.

        Returns True if my team wins.
        """
        my_id = view.player_id
        # Clone from the underlying state (need full state for simulation)
        sim_state = _clone_full_state_from_view(view)

        # Apply my play
        _apply_play_to_state(sim_state, my_id, my_play)

        if len(sim_state.finished_positions) >= 3:
            return self._did_i_win(sim_state, my_id)

        # Collect all cards not in my hand and not already played
        my_card_ids = {c.id for c in view.my_hand}
        played_ids = {c.id for c in view.played_cards}
        pool = [Card.from_id(i) for i in range(108)
                if i not in my_card_ids and i not in played_ids]
        random.shuffle(pool)
        idx = 0
        for pid in range(4):
            if pid == my_id:
                continue
            size = view.opponent_hand_size(pid)
            sim_state.hands = tuple(
                tuple(pool[idx:idx + size]) if i == pid else h
                for i, h in enumerate(sim_state.hands)
            )
            idx += size

        my_team = {0: 0, 1: 1, 2: 0, 3: 1}[my_id]

        # Simulate remainder using fast-but-smart agents
        agents = [_FastSimAgent() for _ in range(4)]

        for _ in range(200):  # safety limit
            if len(sim_state.finished_positions) >= 3:
                return self._did_i_win(sim_state, my_id)

            table = sim_state.table
            if table.last_played_player >= 0:
                other_active = [p for p in sim_state.active_players
                                if p != table.last_played_player]
                if table.pass_count >= len(other_active):
                    sim_state.current_player = table.last_played_player
                    _start_new_trick(sim_state)
                    continue

            current = _next_active_player(sim_state, sim_state.current_player)
            agent = agents[current]
            # Create a PlayerView for the simulation agent
            sim_view = PlayerView(sim_state, current)
            sim_hand = sim_state.hands[current]
            play_cards = agent.choose_play(sim_view)

            # Validate
            rules = RulesEngine(sim_state.level)
            result = rules.validate_play(
                cards=play_cards, hand=sim_hand,
                table_state=sim_state.table,
                player_id=current,
                finished_positions=sim_state.finished_positions,
            )

            if not result.is_legal:
                play_cards = []

            if play_cards:
                _apply_play_to_state(sim_state, current, result.resolved_combo)
            else:
                sim_state.table.record_pass(current)
                sim_state.current_player = (current + 1) % 4

        # Fallback: check result
        return self._did_i_win(sim_state, my_id)

    def _did_i_win(self, state: GameState, my_id: int) -> bool:
        """Check if my team won given the finish order."""
        my_team = {0: 0, 1: 1, 2: 0, 3: 1}[my_id]
        if len(state.finished_positions) >= 3:
            result = calculate_result(state.finished_positions)
            return result.winning_team == my_team
        # Not enough finishers — guess from who's ahead
        if state.finished_positions:
            first = state.finished_positions[0]
            first_team = {0: 0, 1: 1, 2: 0, 3: 1}[first]
            return first_team == my_team
        return False


# ==================================================================
# Simulation helpers
# ==================================================================

def _clone_full_state_from_view(view: PlayerView) -> GameState:
    """Reconstruct a full GameState from a PlayerView for simulation.

    Since PlayerView hides opponent hands, we need the FULL state.
    This is accessed via view._state which holds the original reference.
    """
    return _clone_state(view._state)


def _clone_state(state: GameState) -> GameState:
    """Deep-copy a game state for simulation."""
    # Card objects are frozen and immutable — shallow copy of tuples is safe
    from ..table import TableState
    new_table = TableState(
        current_combo=state.table.current_combo,
        last_played_player=state.table.last_played_player,
        pass_count=state.table.pass_count,
        trick_leader=state.table.trick_leader,
        trick_history=list(state.table.trick_history),
    )
    new_state = GameState(
        level=state.level,
        round_number=state.round_number,
        hands=state.hands,
        played_cards=list(state.played_cards),
        finished_positions=list(state.finished_positions),
        current_player=state.current_player,
        table=new_table,
        trick_number=state.trick_number,
    )
    return new_state


def _apply_play_to_state(state: GameState, player_id: int, combo: Combo):
    """Apply a play (mutates state)."""
    hand = state.hands[player_id]
    played_ids = {c.id for c in combo.cards}
    new_hand = tuple(c for c in hand if c.id not in played_ids)
    state.hands = tuple(
        new_hand if i == player_id else h
        for i, h in enumerate(state.hands)
    )
    state.played_cards.extend(combo.cards)
    state.table.record_play(player_id, combo)
    state.current_player = (player_id + 1) % 4

    if not new_hand:
        state.finished_positions.append(player_id)


def _start_new_trick(state: GameState):
    """Begin a new trick."""
    leader = _next_active_player(state, state.current_player)
    state.table.reset_for_new_trick(leader)
    state.trick_number += 1
    state.current_player = leader


def _next_active_player(state: GameState, from_player: int) -> int:
    for _ in range(4):
        if from_player not in state.finished_positions:
            return from_player
        from_player = (from_player + 1) % 4
    return from_player


def _deal_subset(unseen: List[Card], start: int, count: int, counter: CardCounter) -> Tuple[Card, ...]:
    """Deal a subset of unseen cards, keeping known cards in place."""
    # This is simplified — in reality we'd need to preserve already-known cards
    # For now, deal from the unseen pool
    end = min(start + count, len(unseen))
    return tuple(unseen[start:end])


def _select_diverse_candidates(candidates: List[Combo], limit: int) -> List[Combo]:
    """Select a diverse subset: include different combo types and sizes."""
    by_type: dict = {}
    for c in candidates:
        t = c.combo_type
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(c)

    result = []
    # Take up to 3 from each type, prioritizing different main_ranks
    for t, combos in by_type.items():
        combos.sort(key=lambda c: c.main_rank)
        seen_ranks = set()
        for c in combos:
            if len(result) >= limit:
                return result
            if c.main_rank not in seen_ranks or len(by_type[t]) <= 3:
                result.append(c)
                seen_ranks.add(c.main_rank)
    return result[:limit]


# ==================================================================
# Legacy agents (kept for compatibility)
# ==================================================================

class RandomAgent(BaseAgent):
    """Random legal play — for testing."""

    def __init__(self, params: AIParams = DEFAULT_PARAMS, **kw):
        pass

    def choose_play(self, view: PlayerView) -> List[Card]:
        hand = view.my_hand
        table = view.table
        pid = view.player_id
        finder = ComboFinder(hand, view.level)

        if table.is_empty or table.last_played_player == pid:
            combo = finder.pick_lead()
        else:
            combo = finder.pick_response(table.current_combo)
            if combo is None:
                return []
            if random.random() < 0.3:
                return []
        if combo:
            return list(combo.cards)
        return []


class FirstPlayAgent(BaseAgent):
    """Always plays first found legal combo — for testing."""

    def __init__(self, params: AIParams = DEFAULT_PARAMS, **kw):
        pass

    def choose_play(self, view: PlayerView) -> List[Card]:
        hand = view.my_hand
        table = view.table
        pid = view.player_id
        finder = ComboFinder(hand, view.level)

        if table.is_empty or table.last_played_player == pid:
            combo = finder.pick_lead()
        else:
            combo = finder.pick_response(table.current_combo)
        if combo:
            return list(combo.cards)
        return []


class GreedyAgent(BaseAgent):
    """Plays the combo that uses the most cards."""

    def __init__(self, params: AIParams = DEFAULT_PARAMS, **kw):
        pass

    def choose_play(self, view: PlayerView) -> List[Card]:
        hand = view.my_hand
        table = view.table
        pid = view.player_id
        finder = ComboFinder(hand, view.level)

        if table.is_empty or table.last_played_player == pid:
            combos = _generate_lead_candidates(finder, hand)
            if combos:
                best = max(combos, key=lambda c: (c.length, c.main_rank))
                return list(best.cards)
            return []
        combo = finder.pick_response(table.current_combo)
        if combo:
            return list(combo.cards)
        return []
