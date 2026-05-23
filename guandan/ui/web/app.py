"""Flask web server for Guandan interactive play.

Run: python -m guandan.ui.web.app
"""

import os
import uuid
from flask import Flask, jsonify, render_template, request, session

from ..interactive import InteractiveGame

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Store game sessions: {session_id: InteractiveGame}
_games: dict = {}


def _get_game() -> InteractiveGame:
    """Get or create the game for the current session."""
    sid = session.get("game_id")
    if sid and sid in _games:
        return _games[sid]
    sid = uuid.uuid4().hex
    session["game_id"] = sid
    game = InteractiveGame(level=2)
    _games[sid] = game
    return game


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/")
def index():
    game = _get_game()
    if game.state is None:
        game.start_new_round()
    return render_template("game.html")


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
    """Get a suggested play for the current situation."""
    game = _get_game()
    if game.state is None:
        return jsonify({"card_ids": []})
    if not game._is_human_turn():
        return jsonify({"card_ids": []})

    from ...combo_finder import ComboFinder
    hand = game.state.hands[game.HUMAN_ID]
    finder = ComboFinder(hand, game.state.level)

    if game.state.table.is_empty or game.state.table.last_played_player == game.HUMAN_ID:
        combo = finder.pick_lead()
    else:
        combo = finder.pick_response(game.state.table.current_combo)

    if combo:
        return jsonify({"card_ids": [c.id for c in combo.cards]})
    # Try bomb as fallback
    bomb = finder._find_any_bomb()
    if bomb:
        return jsonify({"card_ids": [c.id for c in bomb.cards]})
    return jsonify({"card_ids": []})


@app.route("/api/debug")
def api_debug():
    """Return all players' hands for debug mode."""
    game = _get_game()
    if game.state is None:
        return jsonify({"hands": []})
    hands = []
    for p in range(4):
        cards = game.state.hands[p]
        # Sort by rank then suit
        sorted_cards = sorted(cards, key=lambda c: (c.rank.value, c.suit.value))
        hands.append({
            "player": p,
            "cards": [game._card_json(c) for c in sorted_cards],
        })
    return jsonify({"hands": hands})


@app.route("/api/new_round", methods=["POST"])
def api_new_round():
    game = _get_game()
    result = game.start_new_round()
    return jsonify(result)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("  掼蛋 Guandan — Web UI")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)
