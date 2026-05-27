"""Informed scorer — exploits known four-hand info, weighted scoring."""

from __future__ import annotations

import time
from typing import List

from ...card import Card
from ...combo import Combo
from ...combo_finder import ComboFinder
from ...combo_compare import can_beat
from ..player_view import PlayerView
from .interface import TestableModel, AnalyzeResult, CandidateResult


class InformedScorer(TestableModel):
    """Scores plays using known four-hand information + tunable weights."""

    name = "InformedScorer"
    description = "全局感知评分器：已知四家手牌，权重可调"
    default_config = {
        "round_weight": 5.0,          # 自己轮次节约权重
        "no_counter_bonus": 8.0,      # 无人能压奖励
        "teammate_cover_bonus": 2.0,  # 队友可接奖励
        "opponent_counter_penalty": 3.0,  # 对手能压惩罚
        "bomb_lead_penalty": 5.0,     # 首家出炸弹罚
        "bomb_overuse_penalty": 4.0,  # 有更优方案却出炸弹罚
        "pass_teammate_bonus": 3.0,   # 过牌时队友可接奖励
        "pass_control_bonus": 2.0,    # 过牌时本队有控权奖励
        "pass_neutral": 0.0,          # 过牌基线
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
            s, detail = self._score(c, hand, hand_after, state, pid, my_team)

            results.append(CandidateResult(
                combo_type=c.combo_type.name,
                cards=[x.display for x in c.cards],
                card_ids=[x.id for x in c.cards],
                score=s,
                reasoning=self._explain(c, state, pid, my_team),
                detail=detail,
            ))

        results.sort(key=lambda r: r.score or 0, reverse=True)

        if can_pass:
            ps = self._score_pass(state, pid, my_team)
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

    def _score(self, combo, hand_before, hand_after, state, pid, my_team):
        rounds_before = len(hand_before) // 2
        rounds_after = len(hand_after) // 2
        round_delta = rounds_before - rounds_after

        who = self._first_who_can_beat(state, pid, combo)
        round_score = round_delta * self.c["round_weight"]
        counter_score = 0.0
        counter_label = ""
        if who is None:
            counter_score = self.c["no_counter_bonus"]
            counter_label = "无人能压"
        elif {0:0,1:1,2:0,3:1}[who] == my_team:
            counter_score = self.c["teammate_cover_bonus"]
            counter_label = f"队友P{who}可接"
        else:
            counter_score = -self.c["opponent_counter_penalty"]
            counter_label = f"对手P{who}能压"

        bomb_penalty = 0.0
        bomb_label = ""
        if combo.is_bomb:
            if state.table.current_combo is None:
                bomb_penalty = -self.c["bomb_lead_penalty"]
                bomb_label = "首家出炸弹"
            elif not state.table.current_combo.is_bomb:
                finder = ComboFinder(hand_before, state.level)
                resp = finder.pick_response(state.table.current_combo)
                if resp and not resp.is_bomb:
                    bomb_penalty = -self.c["bomb_overuse_penalty"]
                    bomb_label = "有更优方案却出炸弹"

        total = round_score + counter_score + bomb_penalty
        return total, {
            "rounds_before": rounds_before, "rounds_after": rounds_after,
            "round_delta": round_delta, "round_weight": self.c["round_weight"],
            "round_score": round(round_score, 1),
            "counter_who": who, "counter_label": counter_label,
            "counter_score": round(counter_score, 1),
            "bomb_penalty": round(bomb_penalty, 1), "bomb_label": bomb_label,
            "total_score": round(total, 1),
        }

    def _score_pass(self, state, pid, my_team):
        table_combo = state.table.current_combo
        if table_combo is None:
            return self.c["pass_neutral"]
        partner = (pid + 2) % 4
        if partner not in state.finished_positions:
            if self._player_can_beat(state, partner, table_combo):
                return self.c["pass_teammate_bonus"]
        if {0:0,1:1,2:0,3:1}.get(state.table.last_played_player) == my_team:
            return self.c["pass_control_bonus"]
        return self.c["pass_neutral"]

    def _player_can_beat(self, state, pid, combo):
        finder = ComboFinder(state.hands[pid], state.level)
        resp = finder.pick_response(combo)
        if resp and can_beat(resp, combo): return True
        bomb = finder._find_any_bomb()
        return bomb is not None and can_beat(bomb, combo)

    def _first_who_can_beat(self, state, my_pid, combo):
        for p in [my_pid+1, my_pid+2, my_pid+3]:
            p = p % 4
            if p == my_pid or p in state.finished_positions: continue
            if self._player_can_beat(state, p, combo): return p
        return None

    def _explain(self, combo, state, pid, my_team):
        parts = [f"出{combo.combo_type.name}"]
        who = self._first_who_can_beat(state, pid, combo)
        if who is None: parts.append("| 无人能压")
        elif {0:0,1:1,2:0,3:1}[who] == my_team: parts.append(f"| 队友P{who}可接")
        else: parts.append(f"| 对手P{who}能压")
        return " ".join(parts)


# Alias for backward compatibility
GreedyPerfectSolver = InformedScorer
