"""Pluggable AI models for the test arena.

Two dimensions:
  - Info scope: Blind (own hand) vs Informed (full four-hand)
  - Weights:   Weighted (tunable params) vs Unweighted (pure computation)

Model list:
  BlindScorer    — Blind + Weighted (12 AIParams)
  InformedScorer — Informed + Weighted (9 control weights)
  RoundScorer    — Informed + Weighted (7 round weights)
  ExactSolver    — Informed + Unweighted (minimax search)
  MCWrapper      — Sampling (inner model configurable)
"""

from .interface import TestableModel, AnalyzeResult, CandidateResult
from .blind_scorer import BlindScorer
from .informed_scorer import InformedScorer
from .round_scorer import RoundScorer
from .endgame_solver import EndgameExactSolver
