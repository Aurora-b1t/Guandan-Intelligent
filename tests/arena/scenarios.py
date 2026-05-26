"""Test scenario library for the AI arena.

Card IDs are chosen to form the intended combos correctly.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from guandan.card import Card


def _ids(rank_val: int, count: int = 1) -> List[int]:
    """Find card IDs for given rank."""
    result = []
    for i in range(108):
        c = Card.from_id(i)
        if c.rank.value == rank_val and not c.is_wild(2):
            result.append(i)
            if len(result) >= count:
                break
    return result


def _extra(rank_vals: List[int], count: int) -> List[int]:
    """Find extra cards of given ranks."""
    result = []
    for i in range(108):
        c = Card.from_id(i)
        if c.rank.value in rank_vals and not c.is_wild(2):
            if i not in result:
                result.append(i)
                if len(result) >= count:
                    break
    return result


@dataclass
class Scenario:
    id: str
    name: str
    category: str
    description: str
    hand: List[int]
    table: Optional[List[int]] = None
    table_player: int = 1           # who played the table combo
    level: int = 2
    opponents: Dict[int, List[int]] = field(default_factory=dict)
    played_cards: List[int] = field(default_factory=list)  # all cards already played
    expected_play: Optional[List[int]] = None
    expected_pass: bool = False
    reasoning: str = ""


# ==================================================================
# Category 1: Full-information deduction
# ==================================================================

DEDUCTION_SCENARIOS = [
    Scenario(
        id="deduce_pair_teammate",
        name="队友可接盘一对",
        category="deduction",
        description="牌桌对5(右家出)，手牌对8对3。对家有对10可接。应出对8",
        hand=_ids(8, 2) + _ids(3, 2) + _extra([6, 7], 2),
        table=_ids(5, 2),
        table_player=1,
        played_cards=_extra([9, 10, 11, 12, 13, 14], 8),
        opponents={2: _ids(10, 2) + _extra([11, 12, 13, 14], 4)},
        expected_play=_ids(8, 2),
        expected_pass=False,
        reasoning="出对8让对家用对10接盘"
    ),
    Scenario(
        id="deduce_no_bomb_lead_bomb",
        name="三家无炸弹可首出炸弹",
        category="deduction",
        description="手牌有4张8炸弹。三家无炸弹。首家可出炸弹",
        hand=_ids(8, 4) + _extra([3, 4], 2),
        table=None,
        opponents={
            1: _extra([10, 11, 12], 6),
            2: _extra([5, 6, 7], 6),
            3: _extra([9, 13, 14], 6),
        },
        expected_play=_ids(8, 4),
        table_player=1,
        expected_pass=False,
        reasoning="三家无炸弹，出炸弹抢控制"
    ),
    Scenario(
        id="deduce_pass_teammate_cover",
        name="队友可接盘应对",
        category="deduction",
        description="牌桌对K，手牌对A。队友有对2。应过牌让队友接",
        hand=_ids(14, 2),
        table=_ids(13, 2),
        opponents={2: _ids(2, 2) + _extra([3, 4], 4)},
        expected_pass=True,
        reasoning="对A打对K浪费，队友对2更合适"
    ),
]

# ==================================================================
# Category 2: Probabilistic sampling
# ==================================================================

SAMPLING_SCENARIOS = [
    Scenario(
        id="sample_one_unseen_king",
        name="一张未见的K",
        category="sampling",
        description="手牌对Q，牌桌对J。只剩少量K未出。评估安全",
        hand=_ids(12, 2),
        table=_ids(11, 2),
        expected_play=_ids(12, 2),
        expected_pass=False,
        reasoning="剩下K不多，出对Q大概率安全"
    ),
    Scenario(
        id="sample_bomb_probability",
        name="炸弹概率评估",
        category="sampling",
        description="手牌2张。牌桌炸弹。应过",
        hand=_extra([3, 4], 2),
        table=_ids(8, 4),
        expected_pass=True,
        reasoning="手牌弱无法压炸弹，只能过"
    ),
]

# ==================================================================
# Category 3: Endgame exact solve
# ==================================================================

ENDGAME_SCENARIOS = [
    Scenario(
        id="endgame_pair_vs_pair",
        name="残局：对子抉择",
        category="endgame",
        description="手牌对8对3。牌桌对4。出对8",
        hand=_ids(8, 2) + _ids(3, 2),
        table=_ids(4, 2),
        expected_play=_ids(8, 2),
        expected_pass=False,
        reasoning="对4小，对8可压，留对3"
    ),
    Scenario(
        id="endgame_single_ace_vs_king",
        name="残局：单A vs 单K",
        category="endgame",
        description="手牌A+3。牌桌K。出A赢下",
        hand=_ids(14, 1) + _ids(3, 1),
        table=_ids(13, 1),
        expected_play=_ids(14, 1),
        expected_pass=False,
        reasoning="出A赢下本轮保持先手"
    ),
    Scenario(
        id="endgame_bomb_vs_pass",
        name="残局：炸弹要不要用",
        category="endgame",
        description="手牌4张8炸弹+单3。牌桌单K。应过",
        hand=_ids(8, 4) + _ids(3, 1),
        table=_ids(13, 1),
        expected_pass=True,
        reasoning="4张炸弹压1张牌不值，且剩单牌不一定能走"
    ),
    Scenario(
        id="endgame_exact_4cards",
        name="残局精确：4张牌",
        category="endgame",
        description="手牌对A对3。首家。出对3",
        hand=_ids(14, 2) + _ids(3, 2),
        table=None,
        expected_play=_ids(3, 2),
        expected_pass=False,
        reasoning="出对3，留对A做大牌"
    ),
]

# ==================================================================
# Category 4: Opening evaluation
# ==================================================================

OPENING_SCENARIOS = [
    Scenario(
        id="opening_scattered",
        name="开局：散牌评估",
        category="opening",
        description="散牌为主。首家应出最低单牌",
        hand=_extra([3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 2], 13)
             + _extra([3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 2], 14),
        table=None,
        expected_pass=False,
        reasoning="首家出最低单牌是标准开局"
    ),
]

ALL_SCENARIOS = DEDUCTION_SCENARIOS + SAMPLING_SCENARIOS + ENDGAME_SCENARIOS + OPENING_SCENARIOS


def get_scenario_by_id(scenario_id: str) -> Optional[Scenario]:
    for s in ALL_SCENARIOS:
        if s.id == scenario_id:
            return s
    return None


def get_scenarios_by_category(category: str) -> List[Scenario]:
    return [s for s in ALL_SCENARIOS if s.category == category]


def list_categories() -> List[str]:
    return ["deduction", "sampling", "endgame", "opening"]
