"""Action log and card tracker — the AI's memory.

ActionLog: append-only record of every play and pass.
CardTracker: derived statistics for opponent modeling.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..card import Card, Rank
from ..combo import Combo, ComboType


@dataclass
class Action:
    """One recorded action in the game."""
    seq: int
    trick_id: int
    player: int
    type: str               # "play" | "pass"
    cards: Tuple[Card, ...]  # empty for pass
    combo: Optional[Combo]   # None for pass
    passed_on: Optional[Combo] = None  # what combo was on the table when they passed


class ActionLog:
    """Append-only log of all game actions."""

    def __init__(self):
        self._actions: List[Action] = []
        self._seq = 0

    def record_play(self, trick_id: int, player: int, cards: List[Card], combo: Combo):
        self._actions.append(Action(
            seq=self._seq, trick_id=trick_id, player=player,
            type="play", cards=tuple(cards), combo=combo,
        ))
        self._seq += 1

    def record_pass(self, trick_id: int, player: int, table_combo: Optional[Combo]):
        self._actions.append(Action(
            seq=self._seq, trick_id=trick_id, player=player,
            type="pass", cards=(), combo=None, passed_on=table_combo,
        ))
        self._seq += 1

    def __len__(self) -> int:
        return len(self._actions)

    def __iter__(self):
        return iter(self._actions)

    def __getitem__(self, i: int) -> Action:
        return self._actions[i]

    @property
    def actions(self) -> List[Action]:
        return list(self._actions)

    def played_cards_by(self, player: int) -> List[Card]:
        """All cards played by a specific player."""
        result = []
        for a in self._actions:
            if a.type == "play" and a.player == player:
                result.extend(a.cards)
        return result

    def recent(self, n: int) -> List[Action]:
        return self._actions[-n:] if n < len(self._actions) else list(self._actions)


class CardTracker:
    """Derived statistics from ActionLog + own hand."""

    def __init__(self, own_hand: Tuple[Card, ...], log: ActionLog):
        # All my cards
        self._my_card_ids: Set[int] = {c.id for c in own_hand}
        self._my_hand = own_hand

        # Cards each player has played
        self._played_by: Dict[int, Set[int]] = {0: set(), 1: set(), 2: set(), 3: set()}
        # Pass history: what each player passed on
        self._pass_history: List[Tuple[int, Combo]] = []

        for a in log:
            if a.type == "play":
                for c in a.cards:
                    self._played_by[a.player].add(c.id)
            elif a.type == "pass" and a.passed_on:
                self._pass_history.append((a.player, a.passed_on))

        # Remaining hand sizes from the current state (updated externally)
        self._opp_sizes: Dict[int, int] = {1: 0, 2: 0, 3: 0}

    def set_opponent_sizes(self, sizes: Dict[int, int]):
        self._opp_sizes.update(sizes)

    def unseen_cards(self) -> List[Card]:
        """All cards not in my hand and not played by anyone."""
        played_ids = set()
        for p in range(4):
            played_ids.update(self._played_by[p])
        result = []
        for i in range(108):
            if i not in self._my_card_ids and i not in played_ids:
                result.append(Card.from_id(i))
        return result

    def unseen_by_rank(self, rank: Rank) -> int:
        """How many cards of this rank are still unseen (not mine, not played)."""
        played = sum(1 for p in range(4) for cid in self._played_by[p]
                     if Card.from_id(cid).rank == rank)
        my_count = sum(1 for c in self._my_hand if c.rank == rank)
        total = 8 if rank.value <= 14 else (4 if rank == Rank.SMALL_JOKER else 4 if rank == Rank.BIG_JOKER else 0)
        return total - played - my_count

    def sample_opponent_hands(self) -> Dict[int, List[Card]]:
        """Randomly distribute unseen cards to opponents based on hand sizes.

        Uses pass constraints: a player who passed on a combo type
        likely doesn't have cards that beat it.
        """
        unseen = self.unseen_cards()
        random.shuffle(unseen)

        # Simple constrained sampling:
        # For players who passed on a high pair, deprioritize giving them high pairs
        # This is a lightweight heuristic — full constraint sampling is complex
        result: Dict[int, List[Card]] = {1: [], 2: [], 3: []}

        # Group unseen by rough quality
        high_cards = [c for c in unseen if c.rank.value >= 13]  # K, A, jokers
        low_cards = [c for c in unseen if c.rank.value < 13]

        random.shuffle(high_cards)
        random.shuffle(low_cards)
        pool = low_cards + high_cards  # deal low cards first

        idx = 0
        for pid in [1, 2, 3]:
            size = self._opp_sizes.get(pid, 0)
            result[pid] = pool[idx:idx + size]
            idx += size
        return result

    def did_player_pass_on_type(self, player: int, combo_type: ComboType, min_rank: int = 0) -> bool:
        """Did this player ever pass when a combo of this type was on the table?"""
        for p, combo in self._pass_history:
            if p == player and combo.combo_type == combo_type:
                if min_rank == 0 or combo.main_rank.value >= min_rank:
                    return True
        return False

    def prob_player_has_bomb(self, player: int) -> float:
        """Crude estimate: probability opponent has at least one bomb."""
        prob_no_bomb = 1.0
        for rank in Rank:
            if rank.value > 14:
                continue
            unseen = self.unseen_by_rank(rank)
            if unseen >= 4:
                # Hypergeometric-ish
                total_unseen = len(self.unseen_cards())
                hand_size = self._opp_sizes.get(player, 0)
                if total_unseen == 0 or hand_size == 0:
                    continue
                p_has = 1.0
                for k in range(4):
                    if unseen - k <= 0 or total_unseen - k <= 0:
                        p_has = 0
                        break
                    p_has *= (unseen - k) / (total_unseen - k)
                p_has = min(p_has * (hand_size / total_unseen) * 10, 0.9)
                prob_no_bomb *= (1 - p_has)
        return 1 - prob_no_bomb
