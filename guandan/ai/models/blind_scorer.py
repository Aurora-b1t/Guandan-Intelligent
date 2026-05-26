"""Blind scorer — only sees own hand, uses AIParams weights."""

from __future__ import annotations

import time
from typing import List

from ...combo_finder import ComboFinder
from ..agent import HeuristicAgent, _generate_lead_candidates, _enumerate_responses
from ..player_view import PlayerView
from ..scorer import score_play
from ..params import AIParams
from .interface import TestableModel, AnalyzeResult, CandidateResult


class BlindScorer(TestableModel):
    """Scores plays using only own hand info + AIParams weights."""

    name = "BlindScorer"
    description = "盲评器：只看自己手牌，12个AIParams权重可调"
    default_config = AIParams().to_dict()

    def __init__(self, **config):
        super().__init__(**config)
        params_dict = {k: v for k, v in self.config.items()
                      if k in AIParams.__dataclass_fields__}
        self._params = AIParams.from_dict(params_dict)
        self._agent = HeuristicAgent(params=self._params)

    def analyze(self, view: PlayerView) -> AnalyzeResult:
        t0 = time.time()
        pid = view.player_id
        hand = view.my_hand
        level = view.level
        table = view.table
        finder = ComboFinder(hand, level)

        if table.is_empty or table.last_played_player == pid:
            candidates = _generate_lead_candidates(finder, hand)
            table_combo = None
        else:
            candidates = _enumerate_responses(hand, table.current_combo, finder, level)
            table_combo = table.current_combo

        can_pass = table_combo is not None and table.last_played_player != pid

        results = []
        for c in candidates:
            used_ids = {x.id for x in c.cards}
            hand_after = tuple(x for x in hand if x.id not in used_ids)
            s = score_play(c, hand, hand_after, table_combo, level, self._params)
            results.append(CandidateResult(
                combo_type=c.combo_type.name,
                cards=[x.display for x in c.cards],
                card_ids=[x.id for x in c.cards],
                score=s,
                reasoning=f"效率+结构+位置={s:.1f}",
            ))

        results.sort(key=lambda r: r.score or 0, reverse=True)

        if can_pass:
            results.append(CandidateResult(
                combo_type="PASS", cards=[], card_ids=[],
                score=self._params.pass_threshold,
                reasoning=f"过牌阈值={self._params.pass_threshold:.1f}",
            ))

        best = results[0] if results else None
        return AnalyzeResult(
            candidates=results, choice=best,
            pass_chosen=(best.combo_type == "PASS" if best else False),
            metrics={"elapsed_ms": (time.time() - t0) * 1000},
            model_name=self.name,
        )


# Alias
HeuristicWrapper = BlindScorer
