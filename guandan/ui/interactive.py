"""Interactive game driver for human vs AI play.

Wraps the game engine to support step-driven (request/response) play
instead of the continuous game loop. Each step processes one human
move and auto-plays AI turns until it's the human's turn again.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from ..card import Card
from ..combo import Combo
from ..combo_finder import ComboFinder
from ..combo_compare import can_beat
from ..deck import Deck
from ..game_state import GameState
from ..rules import RulesEngine, PlayLegality
from ..score import calculate_result, advance_level, is_game_won
from ..table import TableState


class InteractiveGame:
    """Manages one Guandan game session with step-by-step human interaction.

    Human is always player 0. AI players are 1, 2, 3.
    """

    HUMAN_ID = 0

    def __init__(self, level: int = 2):
        self.level = level
        self.team_levels = [level, level]
        self.round_number = 0
        self.state: Optional[GameState] = None
        self.rules: Optional[RulesEngine] = None
        self._round_results: list = []
        self._game_over = False
        self._winning_team: Optional[int] = None
        self._message = ""
        self._ai_running = False
        # AI config
        from ..ai.registry import DEFAULT_CONFIG
        self.config = dict(DEFAULT_CONFIG)
        self.config["global_params"] = dict(DEFAULT_CONFIG["global_params"])
        self.config["players"] = {
            p: dict(cfg) for p, cfg in DEFAULT_CONFIG["players"].items()
        }
        self._auto_play = False  # full auto mode (all AI)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_new_round(self) -> dict:
        """Deal a new round and return the initial state for the frontend."""
        if self._game_over:
            return self._build_state()
        return self._start_round()

    def play_cards(self, card_ids: List[int]) -> dict:
        """Human plays the given cards. Returns updated state.

        Applies the play synchronously, then spawns a background thread
        for AI processing. Returns immediately with my_turn=False.
        The frontend polls until my_turn becomes True.
        """
        if self._game_over:
            return self._build_state()
        if self._ai_running:
            return self._build_state(error="AI思考中，请等待")
        if not self._is_human_turn():
            return self._build_state(error="现在不是你出牌")

        hand = self.state.hands[self.HUMAN_ID]
        cards = [c for c in hand if c.id in card_ids]

        if not cards:
            return self._build_state(error="未选中有效的牌")

        return self._process_human_play(cards)

    def pass_turn(self) -> dict:
        """Human passes. Returns updated state. Async AI processing."""
        if self._game_over:
            return self._build_state()
        if self._ai_running:
            return self._build_state(error="AI思考中，请等待")
        if not self._is_human_turn():
            return self._build_state(error="现在不是你出牌")
        if not self.rules.can_pass(self.state.table, self.HUMAN_ID):
            return self._build_state(error="你是首家，不能过")

        return self._process_human_pass()

    def get_state(self) -> dict:
        """Return current game state. If AI is running, process one AI turn."""
        if self._ai_running and self.state is not None:
            self._step_one_ai()
        return self._build_state()

    def _is_human_turn(self) -> bool:
        """Check if it's currently the human's turn."""
        if self.state is None:
            return False
        if len(self.state.finished_positions) >= 3:
            return False
        if self._ai_running:
            return False
        next_player = self._next_active_player(self.state.current_player)
        return next_player == self.HUMAN_ID

    # ------------------------------------------------------------------
    # Round management
    # ------------------------------------------------------------------

    def _start_round(self) -> dict:
        self.round_number += 1
        round_level = self.team_levels[0]  # level for card play is shared
        self.rules = RulesEngine(round_level)

        deck = Deck.shuffle(Deck.create())
        hands = Deck.deal(deck)

        if self.round_number == 1:
            starter = random.randint(0, 3)
        else:
            starter = self._round_results[-1].positions[0] if self._round_results else 0

        self.state = GameState(
            level=round_level,
            round_number=self.round_number,
            hands=hands,
            current_player=starter,
            trick_number=0,
        )

        # If human is not the starter, auto-play until human's turn
        if starter != self.HUMAN_ID:
            self._ai_running = True

        self._message = "请出牌（你是首家）" if (starter == self.HUMAN_ID) else ""
        return self._build_state()

    # ------------------------------------------------------------------
    # Step processing
    # ------------------------------------------------------------------

    def _process_human_play(self, cards: List[Card]) -> dict:
        """Process human's play. AI turns will run step-by-step via get_state()."""
        result = self.rules.validate_play(
            cards=cards,
            hand=self.state.hands[self.HUMAN_ID],
            table_state=self.state.table,
            player_id=self.HUMAN_ID,
            finished_positions=self.state.finished_positions,
        )

        if not result.is_legal:
            return self._build_state(error=f"不合法的出牌: {result.reason.name}")

        self._apply_play(self.HUMAN_ID, cards, result.resolved_combo)

        if self._check_round_end():
            return self._finish_round()

        self._ai_running = True
        return self._build_state(message="AI思考中...")

    def _process_human_pass(self) -> dict:
        """Process human pass. AI turns will run step-by-step via get_state()."""
        self.state.table.record_pass(self.HUMAN_ID)
        self.state.current_player = (self.HUMAN_ID + 1) % 4

        if self._check_round_end():
            return self._finish_round()

        self._ai_running = True
        return self._build_state(message="AI思考中...")

    def _step_one_ai(self):
        """Process exactly one AI turn. Called from get_state() while _ai_running."""
        if not self._ai_running:
            return
        if self.state is None:
            self._ai_running = False
            return
        if len(self.state.finished_positions) >= 3:
            self._ai_running = False
            return

        table = self.state.table

        # Check if trick ended
        if table.last_played_player >= 0:
            other_active = [p for p in self.state.active_players
                            if p != table.last_played_player]
            if table.pass_count >= len(other_active):
                self.state.current_player = table.last_played_player
                self._start_new_trick()
                if self.state.current_player == self.HUMAN_ID:
                    if self._auto_play:
                        pass  # continue to AI processing below
                    else:
                        self._ai_running = False
                        return

        # Get next player to act
        current = self._next_active_player(self.state.current_player)

        if current == self.HUMAN_ID:
            if self._auto_play:
                # Human slot is AI-controlled — keep running
                self._ai_play(self.HUMAN_ID)
                if len(self.state.finished_positions) >= 3:
                    self._ai_running = False
                return
            else:
                self.state.current_player = current
                self._ai_running = False
                return

        # Process this AI's turn
        self._ai_play(current)

        if len(self.state.finished_positions) >= 3:
            self._ai_running = False
            return

        # After AI plays, check if the next player is human
        # (will be checked on the NEXT get_state call)

    # ------------------------------------------------------------------
    # Auto-play AI turns
    # ------------------------------------------------------------------

    def _ai_play(self, player_id: int):
        """Have an AI player make a move (with restricted view)."""
        from ..ai.player_view import PlayerView
        from ..ai.registry import create_agent_for_player
        hand = self.state.hands[player_id]

        agent = create_agent_for_player(self.config, player_id)
        view = PlayerView(self.state, player_id)
        play_cards = agent.choose_play(view)

        result = self.rules.validate_play(
            cards=play_cards,
            hand=hand,
            table_state=self.state.table,
            player_id=player_id,
            finished_positions=self.state.finished_positions,
        )

        if not result.is_legal:
            # AI error — force pass
            self.state.table.record_pass(player_id)
            self.state.current_player = (player_id + 1) % 4
            return

        if play_cards:
            self._apply_play(player_id, play_cards, result.resolved_combo)
        else:
            self.state.table.record_pass(player_id)
            self.state.current_player = (player_id + 1) % 4

    def _apply_play(self, player_id: int, cards: List[Card], combo: Combo):
        """Apply a play: update table and remove cards from hand."""
        hand = self.state.hands[player_id]
        played_ids = {c.id for c in cards}
        new_hand = tuple(c for c in hand if c.id not in played_ids)
        self.state.hands = tuple(
            new_hand if i == player_id else h
            for i, h in enumerate(self.state.hands)
        )
        self.state.played_cards.extend(cards)
        self.state.table.record_play(player_id, combo)
        self.state.current_player = (player_id + 1) % 4

        if not new_hand:
            self.state.finished_positions.append(player_id)

    def _start_new_trick(self):
        """Start a new trick with the appropriate leader."""
        leader = self._next_active_player(self.state.current_player)
        self.state.table.reset_for_new_trick(leader)
        self.state.trick_number += 1
        self.state.current_player = leader

    def _next_active_player(self, from_player: int) -> int:
        """Find the next active player clockwise from from_player."""
        for _ in range(4):
            if from_player not in self.state.finished_positions:
                return from_player
            from_player = (from_player + 1) % 4
        return from_player

    def _mask_state_for_player(self, player_id: int) -> GameState:
        """Return a copy of the state with opponent hands masked (empty tuples).

        AI agents must not see other players' specific cards — only hand sizes.
        """
        masked_hands = []
        for p in range(4):
            if p == player_id:
                masked_hands.append(self.state.hands[p])
            else:
                # Replace with empty tuple — AI only knows hand size via other means
                masked_hands.append(tuple())
        # Create a shallow copy with masked hands
        from ..game_state import GameState as GS
        from ..table import TableState
        return GS(
            level=self.state.level,
            round_number=self.state.round_number,
            hands=tuple(masked_hands),
            played_cards=list(self.state.played_cards),
            finished_positions=list(self.state.finished_positions),
            current_player=self.state.current_player,
            table=self.state.table,
            trick_number=self.state.trick_number,
        )

    def _check_round_end(self) -> bool:
        return self.state is not None and len(self.state.finished_positions) >= 3

    def _finish_round(self) -> dict:
        """Calculate round result and check for game over."""
        result = calculate_result(self.state.finished_positions)
        self._round_results.append(result)

        winning_team = result.winning_team

        if is_game_won(self.team_levels[winning_team]):
            self._game_over = True
            self._winning_team = winning_team
            self._message = f"游戏结束！{'你' if winning_team == 0 else 'AI'} 的队伍获胜！"
            return self._build_state()

        self.team_levels[winning_team] = advance_level(
            self.team_levels[winning_team], result.level_change
        )

        self._message = f"第{self.round_number}局结束，{'你' if winning_team == 0 else 'AI'}方升级"
        return self._build_state()

    # ------------------------------------------------------------------
    # State serialization
    # ------------------------------------------------------------------

    def _build_state(self, error: str = "", message: str = "") -> dict:
        if self.state is None:
            return {
                "my_hand": [],
                "table_combo": None,
                "players": [],
                "my_turn": False,
                "can_pass": False,
                "level": self.level,
                "round": 0,
                "trick": 0,
                "finished_positions": [],
                "message": error or message or "开始新游戏",
                "error": bool(error),
                "round_over": False,
                "game_over": self._game_over,
                "winner": self._winning_team,
                "team_level_0": self.team_levels[0],
                "team_level_1": self.team_levels[1],
                "round_results": [],
                "trick_history": [],
            }

        # Human hand (sorted by rank then suit)
        hand = sorted(
            self.state.hands[self.HUMAN_ID],
            key=lambda c: (c.rank.value, c.suit.value)
        )

        # Players info
        player_names = ["你", "AI-右", "AI-对", "AI-左"]
        players = []
        for p in range(4):
            is_finished = p in self.state.finished_positions
            players.append({
                "id": p,
                "name": player_names[p],
                "hand_size": 0 if is_finished else len(self.state.hands[p]),
                "finished": is_finished,
                "is_human": p == self.HUMAN_ID,
            })

        # Table combo
        table_combo = None
        if self.state.table.current_combo is not None:
            tc = self.state.table.current_combo
            table_combo = {
                "type": tc.combo_type.name,
                "type_cn": _COMBO_TYPE_CN.get(tc.combo_type, tc.combo_type.name),
                "cards": [self._card_json(c) for c in tc.cards],
                "main_rank": tc.main_rank.name if tc.main_rank else "",
                "length": tc.length,
                "last_player": self.state.table.last_played_player,
            }

        # Check if human can pass
        can_pass = self.rules.can_pass(self.state.table, self.HUMAN_ID) if self.rules else False

        # Check if it's human's turn (AI must not be running)
        my_turn = not self._ai_running and self._is_human_turn()

        # Finished positions (player IDs in order)
        finished_positions = [
            {"id": pid, "name": player_names[pid]}
            for pid in self.state.finished_positions
        ]

        # Determine message
        if error:
            msg = error
        elif message:
            msg = message
        elif self._ai_running:
            msg = "AI思考中..."
        elif self._message:
            msg = self._message
            self._message = ""
        elif my_turn:
            if can_pass:
                msg = "请出牌或点「过」"
            else:
                msg = "你是首家，请出牌"
        else:
            msg = "等待AI出牌..."

        # Trick history (all plays/passes in the current trick)
        trick_history = []
        for pid, combo in self.state.table.trick_history:
            if combo is None:
                trick_history.append({"player": pid, "pass": True})
            else:
                trick_history.append({
                    "player": pid,
                    "pass": False,
                    "combo": {
                        "type": combo.combo_type.name,
                        "type_cn": _COMBO_TYPE_CN.get(combo.combo_type, combo.combo_type.name),
                        "cards": [self._card_json(c) for c in combo.cards],
                        "length": combo.length,
                    }
                })

        # Round results history
        round_results = []
        for rr in self._round_results:
            round_results.append({
                "positions": [{"id": pid, "name": player_names[pid]} for pid in rr.positions],
                "winning_team": rr.winning_team,
                "level_change": rr.level_change,
            })

        return {
            "my_hand": [self._card_json(c) for c in hand],
            "table_combo": table_combo,
            "players": players,
            "my_turn": my_turn,
            "can_pass": can_pass,
            "level": self.team_levels[0] if self.team_levels else self.level,
            "round": self.round_number,
            "trick": self.state.trick_number,
            "finished_positions": finished_positions,
            "message": msg,
            "error": bool(error),
            "round_over": len(self.state.finished_positions) >= 3,
            "game_over": self._game_over,
            "winner": self._winning_team,
            "team_level_0": self.team_levels[0],
            "team_level_1": self.team_levels[1],
            "round_results": round_results,
            "trick_history": trick_history,
            "ai_running": self._ai_running,
            "ai_thinking_player": self.state.current_player if self._ai_running else -1,
            "auto_play": self._auto_play,
        }

    def _card_json(self, card: Card) -> dict:
        suit_names = {0: "C", 1: "D", 2: "H", 3: "S", 4: ""}
        rank_names = {2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
                      9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A",
                      15: "SJ", 16: "BJ"}
        return {
            "id": card.id,
            "rank": card.rank.value,
            "rank_name": rank_names.get(card.rank.value, "?"),
            "suit": card.suit.value,
            "suit_name": suit_names.get(card.suit.value, ""),
            "display": card.display,
            "is_wild": card.is_wild(self.state.level if self.state else 2),
            "is_joker": card.is_joker,
        }


_COMBO_TYPE_CN = {
    1: "单张", 2: "对子", 3: "三条", 4: "三带一", 5: "三带二",
    6: "顺子", 7: "连对", 8: "钢板", 9: "炸弹", 10: "同花顺", 11: "天王炸",
}
