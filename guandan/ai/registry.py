"""AI agent registry and configuration.

Supports multiple agent models and per-player configuration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..card import Card
from .agent import BaseAgent, HeuristicAgent, MonteCarloAgent, RandomAgent
from .params import AIParams, DEFAULT_PARAMS as DEFAULT_AI_PARAMS
from .player_view import PlayerView

# Registered models
_MODELS: Dict[str, type] = {
    "heuristic": HeuristicAgent,
    "monte_carlo": MonteCarloAgent,
    "random": RandomAgent,
}

# Default parameters per model (constructor args + AIParams weights)
_DEFAULT_PARAMS: Dict[str, dict] = {
    "heuristic": dict(DEFAULT_AI_PARAMS.to_dict()),
    "monte_carlo": {
        "num_samples": 128,
        "time_limit_ms": 10000,
        **DEFAULT_AI_PARAMS.to_dict(),
    },
    "random": {},
}

# Default config
DEFAULT_CONFIG = {
    "global_model": "monte_carlo",
    "global_params": dict(_DEFAULT_PARAMS),
    "players": {
        0: {"model": None, "params": None},
        1: {"model": None, "params": None},
        2: {"model": None, "params": None},
        3: {"model": None, "params": None},
    },
}


def list_models() -> List[str]:
    return list(_MODELS.keys())


def get_model_defaults(model: str) -> dict:
    return dict(_DEFAULT_PARAMS.get(model, {}))


def create_agent(model: str, params: Optional[Dict[str, Any]] = None) -> BaseAgent:
    """Create an agent instance from model name and optional params.

    Params dict can contain both constructor args (num_samples, etc.)
    and AIParams weights (efficiency_weight, etc.).
    """
    cls = _MODELS.get(model)
    if cls is None:
        cls = HeuristicAgent
    if params is None:
        params = _DEFAULT_PARAMS.get(model, {})

    # Separate constructor args from AIParams weights
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
    return cls(**constructor_args)


def create_agent_for_player(config: dict, player_id: int) -> BaseAgent:
    """Create the appropriate agent for a player based on config."""
    player_cfg = config.get("players", {}).get(player_id, {})
    model = player_cfg.get("model") or config.get("global_model", "heuristic")
    params = player_cfg.get("params") or config.get("global_params", {}).get(model, {})
    return create_agent(model, params)


def choose_play_for_player(config: dict, view: PlayerView) -> List[Card]:
    """Create an agent and have it choose a play."""
    agent = create_agent_for_player(config, view.player_id)
    return agent.choose_play(view)
