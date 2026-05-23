"""Opponent modeling: track seen cards and estimate remaining distribution.

Maintains a card counter for all 108 cards. Used to:
  - Estimate the probability that a given card is in a specific player's hand
  - Detect how many of each rank are still unseen
  - Estimate opponent bomb probability
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

from ..card import Card, Rank


class CardCounter:
    """Tracks which cards have been seen and where unseen cards might be."""

    def __init__(self, own_hand: Tuple[Card, ...]):
        """Initialize with own hand (these cards are known to us)."""
        self._seen: Set[int] = set()          # card IDs seen
        self._in_my_hand: Set[int] = {c.id for c in own_hand}
        self._opponent_hand_sizes: Dict[int, int] = {1: 27, 2: 27, 3: 27}
        self._played_cards: List[Card] = []
        # Track rank counts in unseen cards
        self._total_by_rank: Counter = Counter()
        for i in range(108):
            self._total_by_rank[Card.from_id(i).rank] += 1

    def update_play(self, player_id: int, cards: List[Card]):
        """Record that player_id played these cards."""
        for c in cards:
            self._seen.add(c.id)
        self._played_cards.extend(cards)
        if player_id != 0:  # not myself
            self._opponent_hand_sizes[player_id] -= len(cards)

    def update_pass(self, player_id: int):
        """Record a pass (no card info revealed)."""
        pass

    def set_opponent_hand_sizes(self, sizes: Dict[int, int]):
        """Update the known hand sizes of opponents."""
        self._opponent_hand_sizes.update(sizes)

    def unseen_cards(self) -> List[Card]:
        """Return all cards that have not been seen."""
        result = []
        for i in range(108):
            if i not in self._seen and i not in self._in_my_hand:
                result.append(Card.from_id(i))
        return result

    def unseen_count(self) -> int:
        """Total number of unseen cards."""
        return 108 - len(self._seen) - len(self._in_my_hand)

    def unseen_by_rank(self, rank: Rank) -> int:
        """How many cards of this rank are still unseen."""
        seen_of_rank = sum(1 for cid in self._seen
                          if Card.from_id(cid).rank == rank)
        my_of_rank = sum(1 for cid in self._in_my_hand
                        if Card.from_id(cid).rank == rank)
        total = self._total_by_rank.get(rank, 0)
        return total - seen_of_rank - my_of_rank

    def prob_player_has_rank(self, player_id: int, rank: Rank, min_count: int = 1) -> float:
        """Naive probability that opponent has at least min_count cards of rank.

        Uses simple hypergeometric-like approximation:
        P = 1 - Π (1 - unseen_of_rank / remaining_pool)
        """
        unseen_of_rank = self.unseen_by_rank(rank)
        remaining_total = self.unseen_count()
        hand_size = self._opponent_hand_sizes.get(player_id, 0)

        if unseen_of_rank == 0 or hand_size == 0 or remaining_total == 0:
            return 0.0

        # Simple approximation: each card draw is independent
        p_single = unseen_of_rank / remaining_total
        # Probability of at least min_count in hand_size draws
        prob = 0.0
        from math import comb
        for k in range(min_count, min(hand_size, unseen_of_rank) + 1):
            if k > hand_size:
                break
            # Hypergeometric: C(unseen, k) * C(total-unseen, hand_size-k) / C(total, hand_size)
            if remaining_total - unseen_of_rank >= hand_size - k:
                prob += (comb(unseen_of_rank, k) *
                        comb(remaining_total - unseen_of_rank, hand_size - k) /
                        comb(remaining_total, hand_size))
        return min(prob, 1.0)

    def estimate_opponent_bomb_prob(self, player_id: int) -> float:
        """Estimate probability that opponent has a bomb."""
        # A bomb requires 4+ of the same rank
        total_prob = 0.0
        for rank in Rank:
            if rank.value <= 14:  # only normal ranks (not jokers)
                unseen = self.unseen_by_rank(rank)
                if unseen >= 4:
                    p = self.prob_player_has_rank(player_id, rank, 4)
                    total_prob = 1 - (1 - total_prob) * (1 - p)
        return total_prob

    def estimate_remaining_distribution(self) -> Dict[int, List[Card]]:
        """Sample a random distribution of unseen cards to opponents.

        Returns {player_id: [Card, ...]} for players 1, 2, 3.
        """
        import random
        unseen = self.unseen_cards()
        shuffled = random.sample(unseen, len(unseen))

        result: Dict[int, List[Card]] = {1: [], 2: [], 3: []}
        idx = 0
        for pid in [1, 2, 3]:
            size = self._opponent_hand_sizes.get(pid, 0)
            result[pid] = shuffled[idx:idx + size]
            idx += size
        return result
