"""Flask web server for Guandan.

Routes:
  /           Main menu
  /game       4-player game (human vs 3 AI)
  /arena      AI test arena (endgame scenarios)
  /api/*      Game API
  /api/arena  Arena API

Run: python -m guandan.ui.web.app
"""

import json
import os
import uuid
from flask import Flask, jsonify, render_template, request, session

from ..interactive import InteractiveGame
from .arena_api import arena_bp

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.register_blueprint(arena_bp)

_games: dict = {}


def _get_game() -> InteractiveGame:
    sid = session.get("game_id")
    if sid and sid in _games:
        return _games[sid]
    sid = uuid.uuid4().hex
    session["game_id"] = sid
    game = InteractiveGame(level=2)
    _games[sid] = game
    return game


# ==================================================================
# Pages
# ==================================================================

@app.route("/")
def menu():
    return render_template("menu.html")


@app.route("/game")
def game_page():
    game = _get_game()
    if game.state is None:
        game.start_new_round()
    initial_state = json.dumps(game.get_state())
    return render_template("game.html", initial_state=initial_state)


@app.route("/arena")
def arena_page():
    return render_template("arena.html")


# ==================================================================
# Game API (existing)
# ==================================================================

@app.route("/api/state")
def api_state():
    game = _get_game()
    if game.state is None:
        game.start_new_round()
    return jsonify(game.get_state())


@app.route("/api/play", methods=["POST"])
def api_play():
    game = _get_game()
    data = request.get_json()
    card_ids = data.get("card_ids", [])
    if not card_ids:
        return jsonify(game.get_state())
    result = game.play_cards(card_ids)
    return jsonify(result)


@app.route("/api/pass", methods=["POST"])
def api_pass():
    game = _get_game()
    result = game.pass_turn()
    return jsonify(result)


@app.route("/api/start_game", methods=["POST"])
def api_start_game():
    game = _get_game()
    result = game.start_game()
    return jsonify(result)


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    sid = uuid.uuid4().hex
    session["game_id"] = sid
    game = InteractiveGame(level=2)
    _games[sid] = game
    game.start_new_round()
    return jsonify(game.get_state())


@app.route("/api/hint")
def api_hint():
    game = _get_game()
    if game.state is None:
        return jsonify({"card_ids": []})
    if not game._is_human_turn():
        return jsonify({"card_ids": []})

    from ...combo_finder import ComboFinder
    from ...combo_compare import can_beat
    hand = game.state.hands[game.HUMAN_ID]
    finder = ComboFinder(hand, game.state.level)

    if game.state.table.is_empty or game.state.table.last_played_player == game.HUMAN_ID:
        combo = finder.pick_lead()
        if combo:
            return jsonify({"card_ids": [c.id for c in combo.cards]})
    else:
        combo = finder.pick_response(game.state.table.current_combo)
        if combo and can_beat(combo, game.state.table.current_combo):
            return jsonify({"card_ids": [c.id for c in combo.cards]})

    # Fallback: try any bomb
    bomb = finder._find_any_bomb()
    if bomb:
        tc = game.state.table.current_combo
        if tc is None or can_beat(bomb, tc):
            return jsonify({"card_ids": [c.id for c in bomb.cards]})
    return jsonify({"card_ids": []})


@app.route("/api/debug")
def api_debug():
    game = _get_game()
    if game.state is None:
        return jsonify({"hands": []})
    hands = []
    for p in range(4):
        cards = game.state.hands[p]
        sorted_cards = sorted(cards, key=lambda c: (c.rank.value, c.suit.value))
        hands.append({
            "player": p,
            "cards": [game._card_json(c) for c in sorted_cards],
        })
    return jsonify({"hands": hands})


@app.route("/api/ai_log")
def api_ai_log():
    from ...ai.logger import AILogger
    log = AILogger.get()
    return jsonify({
        "entries": log.get_recent(500),
        "last_decision": log.get_last_decision(),
    })


@app.route("/api/ai_log/clear", methods=["POST"])
def api_ai_log_clear():
    from ...ai.logger import AILogger
    AILogger.get().clear()
    return jsonify({"ok": True})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    """Get or update AI configuration."""
    game = _get_game()
    if request.method == "POST":
        data = request.get_json()
        if data:
            if "decider" in data:
                game.config["decider"] = data["decider"]
            if "inner_model" in data:
                game.config["inner_model"] = data["inner_model"]
            if "enumerator" in data:
                game.config["enumerator"] = data["enumerator"]
            if "players" in data:
                for pid, cfg in data["players"].items():
                    p = int(pid)
                    game.config["players"][p] = cfg
            if "auto_play" in data:
                game._auto_play = data["auto_play"]
    from ...ai.registry import get_schema
    schema = get_schema()
    return jsonify({"config": game.config, "schema": schema})


@app.route("/api/suggest")
def api_suggest():
    """AI suggestion: generate candidates from hand, MC score each, return ranked."""
    from ...ai.player_view import PlayerView
    from ...ai.agent import MonteCarloAgent, _generate_lead_candidates
    from ...combo_finder import ComboFinder
    from ...combo_compare import can_beat

    game = _get_game()
    if game.state is None or not game._is_human_turn():
        return jsonify({"candidates": [], "message": "不是你的回合"})

    pid = game.HUMAN_ID
    hand = game.state.hands[pid]
    table = game.state.table
    level = game.state.level
    finder = ComboFinder(hand, level)

    # Generate candidates directly from hand (not from log)
    is_lead = table.is_empty or table.last_played_player == pid
    table_combo = table.current_combo

    if is_lead:
        candidates = _generate_lead_candidates(finder, hand)
    else:
        from ...ai.agent import _enumerate_responses
        candidates = _enumerate_responses(hand, table_combo, finder, level)

    # Run MC to score candidates + pass option
    can_pass = not is_lead
    view = PlayerView(game.state, pid, game.action_log)
    mc_agent = MonteCarloAgent(num_samples=60, time_limit_ms=6000)
    scored = mc_agent.score_candidates(view, candidates, can_pass)

    # Build result from scored candidates (include PASS)
    results = []
    for c, wr in scored:
        if c is None:
            results.append({
                "type": "PASS", "type_cn": "过牌",
                "cards": [], "length": 0, "is_bomb": False,
                "win_rate": wr,
            })
        else:
            if not is_lead and not can_beat(c, table_combo):
                continue
            results.append({
                "type": c.combo_type.name,
                "type_cn": _COMBO_TYPE_CN.get(c.combo_type.value, c.combo_type.name),
                "cards": [x.display for x in c.cards],
                "length": c.length,
                "is_bomb": c.is_bomb,
                "win_rate": wr,
            })

    results.sort(key=lambda c: c.get("win_rate", 0), reverse=True)

    return jsonify({
        "candidates": results,
        "hand_size": len(hand),
        "message": f"分析了 {len(results)} 个候选",
    })


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    """Evaluate selected cards using Monte Carlo simulation."""
    from ...combo_parser import ComboParser
    from ...combo_compare import can_beat

    game = _get_game()
    if game.state is None:
        return jsonify({"error": "游戏未开始"})

    data = request.get_json() or {}
    card_ids = data.get("card_ids", [])
    if not card_ids:
        # No cards selected — check if human has any valid play
        hand = game.state.hands[game.HUMAN_ID]
        table_combo = game.state.table.current_combo
        is_lead = (table_combo is None or game.state.table.last_played_player == game.HUMAN_ID)
        if is_lead:
            return jsonify({"info": "你是首家，可任意出牌"})

        # Check if any card in hand can beat the table
        from ...combo_finder import ComboFinder
        finder = ComboFinder(hand, game.state.level)
        response = finder.pick_response(table_combo)
        bomb = finder._find_any_bomb()
        if not response and not bomb:
            return jsonify({"info": "手牌中没有任何能压过牌桌的牌型，只能过牌"})
        return jsonify({"info": "请选中要评估的牌"})

    hand = game.state.hands[game.HUMAN_ID]
    cards = [c for c in hand if c.id in card_ids]
    if len(cards) != len(card_ids):
        return jsonify({"error": "选中的牌不在手牌中"})

    parser = ComboParser(game.state.level)
    combo = parser.parse(cards)
    if combo is None:
        return jsonify({"error": "选中的牌不构成合法牌型"})

    table_combo = game.state.table.current_combo
    is_lead = (table_combo is None or game.state.table.last_played_player == game.HUMAN_ID)
    if not is_lead and not can_beat(combo, table_combo):
        return jsonify({"error": "打不过牌桌上的牌型"})

    # Run MC to score this specific play
    from ...ai.player_view import PlayerView
    from ...ai.agent import MonteCarloAgent
    view = PlayerView(game.state, game.HUMAN_ID, game.action_log)
    mc_agent = MonteCarloAgent(num_samples=60, time_limit_ms=6000)
    scored = mc_agent.score_candidates(view, [combo], can_pass=False)

    win_rate = scored[0][1] if scored else None

    from ...ai.hand_eval import estimate_rounds
    used_ids = {c.id for c in cards}
    hand_after = tuple(c for c in hand if c.id not in used_ids)

    return jsonify({
        "valid": True,
        "combo_type": combo.combo_type.name,
        "cards": [c.display for c in cards],
        "win_rate": win_rate,
        "rounds_before": estimate_rounds(hand, game.state.level),
        "rounds_after": estimate_rounds(hand_after, game.state.level),
        "is_bomb": combo.is_bomb,
    })


@app.route("/api/auto_play", methods=["POST"])
def api_auto_play():
    """Toggle full auto-play mode."""
    game = _get_game()
    data = request.get_json() or {}
    game._auto_play = data.get("enabled", False)
    if game._auto_play and game.state is not None:
        game._ai_running = True
    return jsonify({"auto_play": game._auto_play})


@app.route("/api/new_round", methods=["POST"])
def api_new_round():
    game = _get_game()
    result = game.start_new_round()
    return jsonify(result)


# ==================================================================
# Arena API
# ==================================================================

@app.route("/api/arena/analyze", methods=["POST"])
def api_arena_analyze():
    """Analyze an endgame scenario: given hand, table combo, and level,
    return AI candidates with scores.
    """
    from ...card import Card
    from ...combo_parser import ComboParser
    from ...combo_finder import ComboFinder
    from ...ai.scorer import score_play
    from ...ai.hand_eval import hand_score
    from ...ai.logger import AILogger

    data = request.get_json()
    card_ids = data.get("hand", [])
    level = data.get("level", 2)
    table_card_ids = data.get("table", None)
    is_lead = data.get("is_lead", True)

    # Build hand
    hand = tuple(Card.from_id(i) for i in card_ids)

    # Build table combo if provided
    table_combo = None
    if table_card_ids:
        parser = ComboParser(level)
        table_combo = parser.parse([Card.from_id(i) for i in table_card_ids])

    # Clear old log and analyze
    AILogger.get().clear()
    finder = ComboFinder(hand, level)

    if is_lead or table_combo is None:
        from ...ai.agent import _generate_lead_candidates
        candidates = _generate_lead_candidates(finder, hand)
    else:
        candidates = []
        combo = finder.pick_response(table_combo)
        if combo:
            candidates.append(combo)
        bomb = finder._find_any_bomb()
        if bomb:
            candidates.append(bomb)

    # Score each
    results = []
    for c in candidates:
        used_ids = {x.id for x in c.cards}
        hand_after = tuple(x for x in hand if x.id not in used_ids)
        s = score_play(c, hand, hand_after, table_combo, level)
        results.append({
            "type": c.combo_type.name,
            "type_cn": _COMBO_TYPE_CN.get(c.combo_type.value, c.combo_type.name),
            "cards": [x.display for x in c.cards],
            "card_ids": [x.id for x in c.cards],
            "length": c.length,
            "main_rank": c.main_rank.name,
            "is_bomb": c.is_bomb,
            "score": round(s, 2),
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    hs = hand_score(hand, level)

    return jsonify({
        "hand_display": [Card.from_id(i).display for i in card_ids],
        "hand_size": len(hand),
        "hand_score": round(hs, 2),
        "table_display": [Card.from_id(i).display for i in table_card_ids] if table_card_ids else None,
        "is_lead": is_lead,
        "candidates": results,
        "ai_log": AILogger.get().get_recent(200),
    })


@app.route("/api/arena/random_hand", methods=["POST"])
def api_arena_random_hand():
    """Generate a random hand for testing."""
    import random
    data = request.get_json() or {}
    size = data.get("size", 10)
    all_ids = list(range(108))
    random.shuffle(all_ids)
    hand_ids = all_ids[:size]
    from ...card import Card
    return jsonify({
        "hand_ids": hand_ids,
        "hand_display": [Card.from_id(i).display for i in hand_ids],
    })


_COMBO_TYPE_CN = {
    1: "单张", 2: "对子", 3: "三条", 4: "三带二",
    5: "顺子", 6: "连对", 7: "钢板", 8: "炸弹", 9: "同花顺", 10: "天王炸",
}


# ==================================================================
# Main
# ==================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  掼蛋 Guandan — Web UI")
    print("  Main menu: http://localhost:8765")
    print("  Game:      http://localhost:8765/game")
    print("  Arena:     http://localhost:8765/arena")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=8765)
