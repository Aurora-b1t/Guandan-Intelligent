"""AI agent registry and configuration.

Two-layer architecture:
  Outer (decision)  — what each player uses: monte_carlo / heuristic / random
  Inner (simulation) — what MC uses inside rollouts: perfect_info / heuristic
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..card import Card
from .agent import (BaseAgent, HeuristicAgent, MonteCarloAgent,
                    RandomAgent, InformedAgent, BlindAgent)
from .params import AIParams, DEFAULT_PARAMS as DEFAULT_AI_PARAMS
from .player_view import PlayerView

# Outer decision models (不完全信息 → each player picks one)
_OUTER_MODELS: Dict[str, type] = {
    "heuristic": HeuristicAgent,
    "monte_carlo": MonteCarloAgent,
    "random": RandomAgent,
}

# Inner simulation models (MC uses this for rollouts)
_SIM_MODELS: Dict[str, type] = {
    "informed": InformedAgent,
    "blind": BlindAgent,
}

# Default params per model
_DEFAULT_PARAMS: Dict[str, dict] = {
    "heuristic": dict(DEFAULT_AI_PARAMS.to_dict()),
    "monte_carlo": {
        "num_samples": 128,
        "time_limit_ms": 10000,
    },
    "random": {},
    "informed": {},
    "blind": dict(DEFAULT_AI_PARAMS.to_dict()),
}

DEFAULT_CONFIG = {
    "global_model": "monte_carlo",
    "simulation_model": "informed",
    "global_params": dict(_DEFAULT_PARAMS),
    "players": {
        0: {"model": None, "params": None},
        1: {"model": None, "params": None},
        2: {"model": None, "params": None},
        3: {"model": None, "params": None},
    },
}


def list_models() -> List[str]:
    return list(_OUTER_MODELS.keys())


def list_sim_models() -> List[str]:
    return list(_SIM_MODELS.keys())


def get_model_defaults(model: str) -> dict:
    return dict(_DEFAULT_PARAMS.get(model, {}))


def create_agent(model: str, params: Optional[Dict[str, Any]] = None,
                 config: dict = None) -> BaseAgent:
    """Create an outer decision agent."""
    cls = _OUTER_MODELS.get(model)
    if cls is None:
        cls = HeuristicAgent
    if params is None:
        params = _DEFAULT_PARAMS.get(model, {})

    ai_params_dict = {}
    constructor_args = {}
    ai_fields = set(AIParams.__dataclass_fields__.keys())
    for k, v in params.items():
        if k in ai_fields:
            ai_params_dict[k] = v
        else:
            constructor_args[k] = v

    ai_params = AIParams.from_dict(ai_params_dict) if ai_params_dict else DEFAULT_AI_PARAMS
    constructor_args["params"] = ai_params
    if config is not None:
        constructor_args["config"] = config
    return cls(**constructor_args)


def create_simulation_agent(config: dict, player_id: int = None):
    """Create the inner simulation agent for MC rollouts.

    Checks per-player config first, then global.
    """
    sim_model = config.get("simulation_model", "informed")
    if player_id is not None:
        player_sim = (config.get("players", {}).get(player_id, {})
                      .get("params", {}) or {}).get("simulation_model")
        if player_sim:
            sim_model = player_sim
    params = config.get("global_params", {}).get(sim_model, {})

    cls = _SIM_MODELS.get(sim_model, InformedAgent)
    if sim_model == "informed":
        return cls()
    else:
        ai_params_dict = {}
        ai_fields = set(AIParams.__dataclass_fields__.keys())
        for k, v in params.items():
            if k in ai_fields:
                ai_params_dict[k] = v
        ai_params = AIParams.from_dict(ai_params_dict) if ai_params_dict else DEFAULT_AI_PARAMS
        return cls(params=ai_params)


def create_agent_for_player(config: dict, player_id: int) -> BaseAgent:
    """Create the outer decision agent for a player."""
    player_cfg = config.get("players", {}).get(player_id, {})
    model = player_cfg.get("model") or config.get("global_model", "heuristic")
    params = player_cfg.get("params") or config.get("global_params", {}).get(model, {})
    return create_agent(model, params, config)
