"""Unified AI parameters — all tunable weights in one place.

These control the scoring and decision logic. Adjustable per-model
and per-player via the web UI config panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AIParams:
    """Tunable parameters for AI decision-making."""

    # Efficiency — how much to value using many cards at once
    efficiency_weight: float = 20.0

    # Round reduction — reward for reducing rounds-to-empty (scorer.py uses this)
    round_weight: float = 8.0

    # Bomb penalties
    bomb_lead_penalty: float = -12.0    # leading with a bomb
    bomb_overuse_penalty: float = -10.0  # using bomb vs non-bomb
    bomb_vs_bomb_bonus: float = 2.0     # bomb vs bomb

    # Positional
    lead_bonus: float = 1.0
    follow_bonus: float = 1.0
    joker_lead_penalty: float = -18.0      # per joker card led (eff>=16)
    rank_card_lead_penalty: float = -10.0   # per rank/level card led (eff==15)
    high_rank_lead_penalty: float = -0.5    # leading with K/A (eff>=13)

    # Card usage
    card_usage_weight: float = 0.3

    # Threshold: score below this → pass instead of play
    pass_threshold: float = 0.0

    # Simulation agent: probability of passing when could play
    sim_pass_prob: float = 0.15

    def to_dict(self) -> dict:
        return {
            "efficiency_weight": self.efficiency_weight,
            "round_weight": self.round_weight,
            "bomb_lead_penalty": self.bomb_lead_penalty,
            "bomb_overuse_penalty": self.bomb_overuse_penalty,
            "bomb_vs_bomb_bonus": self.bomb_vs_bomb_bonus,
            "lead_bonus": self.lead_bonus,
            "follow_bonus": self.follow_bonus,
            "joker_lead_penalty": self.joker_lead_penalty,
            "rank_card_lead_penalty": self.rank_card_lead_penalty,
            "high_rank_lead_penalty": self.high_rank_lead_penalty,
            "card_usage_weight": self.card_usage_weight,
            "pass_threshold": self.pass_threshold,
            "sim_pass_prob": self.sim_pass_prob,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AIParams:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# Default instance
DEFAULT_PARAMS = AIParams()
