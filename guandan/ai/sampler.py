"""Sampler — handles unknown information by generating possible opponent hands."""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from ..card import Card
from .player_view import PlayerView


class Sampler:
    """Base class for opponent hand sampling."""

    name: str = "base"
    description: str = ""

    def sample(self, view: PlayerView) -> Dict[int, Tuple[Card, ...]]:
        """Return {player_id: hand_cards} for opponents.

        The caller provides the sampled hands to the Decider.
        """
        raise NotImplementedError


class RandomSampler(Sampler):
    """Pure random shuffle of unseen pool, dealt by opponent hand size."""

    name = "RandomSampler"
    description = "纯随机：洗牌 unseen pool，按手牌数分配"

    def sample(self, view: PlayerView) -> Dict[int, Tuple[Card, ...]]:
        unseen = self._unseen(view)
        random.shuffle(unseen)
        result: Dict[int, Tuple[Card, ...]] = {}
        idx = 0
        for p in range(4):
            if p == view.player_id:
                continue
            size = view.opponent_hand_size(p)
            result[p] = tuple(unseen[idx:idx + size])
            idx += size
        return result

    def _unseen(self, view: PlayerView) -> List[Card]:
        my_ids = {c.id for c in view.my_hand}
        played_ids = {c.id for c in view.played_cards}
        return [Card.from_id(i) for i in range(108)
                if i not in my_ids and i not in played_ids]


from .constrained_sampler import ConstrainedSampler

# Registry
_SAMPLERS: Dict[str, type] = {
    "random": RandomSampler,
    "constrained": ConstrainedSampler,
}

DEFAULT_SAMPLER = "random"


def list_samplers() -> List[str]:
    return list(_SAMPLERS.keys())


def get_sampler_info(sid: str) -> dict:
    cls = _SAMPLERS.get(sid, RandomSampler)
    return {"id": sid, "name": cls.name, "description": cls.description,
            "params": {}}


def create_sampler(sid: str) -> Sampler:
    cls = _SAMPLERS.get(sid, RandomSampler)
    if issubclass(cls, Sampler):
        return cls()
    return cls()  # ConstrainedSampler doesn't inherit Sampler but has sample()

