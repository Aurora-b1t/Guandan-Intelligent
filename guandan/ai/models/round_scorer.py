"""Round-based scorer — estimate_rounds on known hands, weighted."""

from __future__ import annotations

import time
from typing import List

from ...combo_finder import ComboFinder
from ...combo_compare import can_beat
from ..hand_eval import estimate_rounds
from ..player_view import PlayerView
from .interface import TestableModel, AnalyzeResult, CandidateResult


class RoundScorer(TestableModel):
    """Scores plays by round impact on known four-hand state."""

    name = "RoundScorer"
    description = "轮次评分器：基于 estimate_rounds，权重可调"
    default_config = {
        "round_delta_weight": 8.0,         # 队轮次改善
        "gap_improve_weight": 3.0,         # 队际差距改善
        "no_counter_bonus": 6.0,           # 无人能压
        "teammate_cover_bonus": 2.0,       # 队友可接
        "opponent_counter_penalty": 2.0,   # 对手能压
        "pass_teammate_bonus": 4.0,        # 过牌时队友可接
        "pass_default": 1.0,               # 过牌基线
    }

    def __init__(self, **config):
        super().__init__(**config)
        self.c = self.config

    def analyze(self, view: PlayerView) -> AnalyzeResult:
        t0 = time.time()
        pid = view.player_id
        state = view._state
        hand = view.my_hand
        level = view.level
        table = view.table
        finder = ComboFinder(hand, level)

        my_team = {0: 0, 1: 1, 2: 0, 3: 1}[pid]

        teams = {0: 0, 1: 1, 2: 0, 3: 1}
        team_before = sum(estimate_rounds(state.hands[p], level)
                          for p in range(4) if p not in state.finished_positions and teams[p] == my_team)
        opp_before = sum(estimate_rounds(state.hands[p], level)
                         for p in range(4) if p not in state.finished_positions and teams[p] != my_team)

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
        for c in candidates:
            used_ids = {x.id for x in c.cards}
            hand_after = tuple(x for x in hand if x.id not in used_ids)
            sim_hands = list(state.hands)
            sim_hands[pid] = hand_after

            team_after = sum(estimate_rounds(sim_hands[p], level)
                             for p in range(4) if p not in state.finished_positions and teams[p] == my_team)
            opp_after = sum(estimate_rounds(sim_hands[p], level)
                            for p in range(4) if p not in state.finished_positions and teams[p] != my_team)

            team_delta = team_before - team_after
            gap_before = opp_before - team_before
            gap_after = opp_after - team_after

            score = team_delta * self.c["round_delta_weight"] + (gap_after - gap_before) * self.c["gap_improve_weight"]

            who = self._first_who_can_beat(state, pid, c)
            if who is None:
                score += self.c["no_counter_bonus"]
            elif teams[who] == my_team:
                score += self.c["teammate_cover_bonus"]
            else:
                score -= self.c["opponent_counter_penalty"]

            results.append(CandidateResult(
                combo_type=c.combo_type.name,
                cards=[x.display for x in c.cards],
                card_ids=[x.id for x in c.cards],
                score=score,
                reasoning=f"队轮{team_before}→{team_after} 对手{opp_before}→{opp_after}",
            ))

        results.sort(key=lambda r: r.score or 0, reverse=True)

        if can_pass:
            ps = self._score_pass(state, pid, my_team, level)
            results.append(CandidateResult(
                combo_type="PASS", cards=[], card_ids=[], score=ps, reasoning="过牌",
            ))

        best = results[0] if results else None
        return AnalyzeResult(
            candidates=results, choice=best,
            pass_chosen=(best.combo_type == "PASS" if best else False),
            metrics={"elapsed_ms": (time.time() - t0) * 1000},
            model_name=self.name,
        )

    def _score_pass(self, state, pid, my_team, level):
        table_combo = state.table.current_combo
        if table_combo is None: return self.c["pass_default"]
        partner = (pid + 2) % 4
        if partner not in state.finished_positions:
            finder = ComboFinder(state.hands[partner], level)
            resp = finder.pick_response(table_combo)
            if resp and can_beat(resp, table_combo):
                return self.c["pass_teammate_bonus"]
        return self.c["pass_default"]

    def _first_who_can_beat(self, state, my_pid, combo):
        for p in [my_pid+1, my_pid+2, my_pid+3]:
            p = p % 4
            if p == my_pid or p in state.finished_positions: continue
            finder = ComboFinder(state.hands[p], state.level)
            resp = finder.pick_response(combo)
            if resp and can_beat(resp, combo): return p
            bomb = finder._find_any_bomb()
            if bomb and can_beat(bomb, combo): return p
        return None


# Alias
RoundBasedEngine = RoundScorer
