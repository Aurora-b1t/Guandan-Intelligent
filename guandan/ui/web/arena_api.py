"""Arena API — model comparison, analysis, and benchmarking."""

import time
from flask import Blueprint, jsonify, request

from ...card import Card
from ...combo_parser import ComboParser
from ...game_state import GameState
from ...table import TableState
from ..interactive import InteractiveGame
from tests.arena.scenarios import ALL_SCENARIOS, get_scenario_by_id, list_categories
from ...ai.player_view import PlayerView
from ...ai.models import InformedScorer, RoundScorer, EndgameExactSolver, BlindScorer
from ...ai.registry import get_schema

arena_bp = Blueprint('arena_api', __name__)


def _make_arena_model(model_id: str):
    if model_id == "informed":
        return InformedScorer()
    elif model_id == "round":
        return RoundScorer()
    elif model_id == "exact":
        return EndgameExactSolver()
    elif model_id == "blind":
        return BlindScorer()
    elif model_id == "mc":
        from ...ai.mc_decider import MCDecider
        from ...ai.sampler import create_sampler
        from ...ai.candidate_enum import create_enumerator
        from ...ai.registry import _make_inner_agent
        sampler = create_sampler("random")
        inner = _make_inner_agent("informed", {})
        enumerator = create_enumerator("full")
        return MCDecider(sampler=sampler, inner=inner, enumerator=enumerator,
                        num_samples=50, time_limit_ms=5000)
    elif model_id == "ismcts":
        from ...ai.ismcts import ISMCTSDecider
        from ...ai.sampler import create_sampler
        from ...ai.candidate_enum import create_enumerator
        from ...ai.registry import _make_inner_agent
        sampler = create_sampler("random")
        inner = _make_inner_agent("informed", {})
        enumerator = create_enumerator("full")
        return ISMCTSDecider(sampler=sampler, inner=inner, enumerator=enumerator,
                            max_iterations=200, time_limit_ms=5000)
    return None


def _build_view(scenario):
    hand = tuple(Card.from_id(i) for i in scenario.hand)
    hands = {0: hand}
    for p, ids in scenario.opponents.items():
        hands[int(p)] = tuple(Card.from_id(i) for i in ids)
    for p in range(4):
        if p not in hands:
            hands[p] = tuple()
    hands_tuple = tuple(hands.get(p, tuple()) for p in range(4))

    table = TableState(trick_leader=scenario.table_player)
    if scenario.table:
        parser = ComboParser(scenario.level)
        combo = parser.parse([Card.from_id(i) for i in scenario.table])
        if combo:
            table.record_play(scenario.table_player, combo)

    played = [Card.from_id(i) for i in scenario.played_cards]
    state = GameState(level=scenario.level, round_number=1,
                      hands=hands_tuple, current_player=0,
                      table=table, trick_number=1,
                      played_cards=played)
    return PlayerView(state, 0)


# ==================================================================
# Endpoints
# ==================================================================

@arena_bp.route("/api/arena/models")
def list_models():
    schema = get_schema()
    decider = schema.get("decider", {}).get("models", {})
    inner = schema.get("inner_model", {}).get("models", {})
    return jsonify({
        "outer": [{"id": mid, "name": m["name"], "description": m.get("description",""),
                   "is_mc": m.get("is_mc", False)} for mid, m in decider.items()],
        "inner": [{"id": mid, "name": m["name"], "description": m.get("description","")}
                  for mid, m in inner.items()],
    })


@arena_bp.route("/api/arena/scenarios")
def list_scenarios():
    cat = request.args.get("category")
    scenarios = ALL_SCENARIOS
    if cat:
        scenarios = [s for s in scenarios if s.category == cat]
    return jsonify({
        "scenarios": [{"id": s.id, "name": s.name, "category": s.category,
                       "description": s.description, "hand_size": len(s.hand),
                       "has_table": s.table is not None,
                       "played_count": len(s.played_cards)} for s in scenarios],
        "categories": list_categories(),
    })


@arena_bp.route("/api/arena/scenarios/<scenario_id>")
def get_scenario(scenario_id):
    s = get_scenario_by_id(scenario_id)
    if not s: return jsonify({"error": "Not found"}), 404
    return jsonify({"id": s.id, "name": s.name, "category": s.category,
                    "description": s.description,
                    "hand": [{"id": i, "display": Card.from_id(i).display} for i in s.hand],
                    "table": [{"id": i, "display": Card.from_id(i).display} for i in (s.table or [])],
                    "level": s.level, "expected_play": s.expected_play,
                    "expected_pass": s.expected_pass, "reasoning": s.reasoning})


@arena_bp.route("/api/arena/compare", methods=["POST"])
def compare():
    data = request.get_json() or {}
    scenario_id = data.get("scenario_id")
    model_ids = data.get("models", ["blind", "informed"])
    scenario = get_scenario_by_id(scenario_id) if scenario_id else None
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404

    view = _build_view(scenario)
    results = []
    schema_names = {}
    s = get_schema()
    for cat in ["decider", "inner_model"]:
        for mid, m in s.get(cat, {}).get("models", {}).items():
            schema_names[mid] = m["name"]

    for entry in model_ids:
        mid = entry if isinstance(entry, str) else entry.get("id", entry)
        label = entry.get("label") if isinstance(entry, dict) else None
        model = _make_arena_model(mid)
        if model is None: continue
        name = label or schema_names.get(mid) or getattr(model, 'name', mid)
        t0 = time.time()
        try:
            result = model.analyze(view)
        except Exception as e:
            results.append({"model": mid, "model_name": name, "error": str(e)})
            continue
        elapsed = (time.time() - t0) * 1000
        results.append({
            "model": mid, "model_name": name,
            "choice": {"type": result.choice.combo_type if result.choice else "NONE",
                       "cards": result.choice.cards if result.choice else []} if result.choice else None,
            "pass_chosen": result.pass_chosen,
            "top_candidates": [{"type": c.combo_type, "cards": c.cards, "score": c.score, "win_rate": c.win_rate}
                               for c in (result.candidates or [])[:5]],
            "elapsed_ms": result.metrics.get("elapsed_ms", elapsed),
            "timed_out": result.metrics.get("timed_out", False),
        })

    return jsonify({"scenario_id": scenario.id, "scenario_name": scenario.name,
                    "expected": {"play": scenario.expected_play, "pass": scenario.expected_pass},
                    "results": results})


@arena_bp.route("/api/arena/benchmark", methods=["POST"])
def benchmark():
    data = request.get_json() or {}
    model_ids = data.get("models", ["blind", "informed"])
    category = data.get("category")
    scenarios = ALL_SCENARIOS
    if category: scenarios = [s for s in scenarios if s.category == category]

    results = []
    schema_names = {}
    s = get_schema()
    for cat in ["decider", "inner_model"]:
        for mid, m in s.get(cat, {}).get("models", {}).items():
            schema_names[mid] = m["name"]

    for scenario in scenarios:
        view = _build_view(scenario)
        for entry in model_ids:
            mid = entry if isinstance(entry, str) else entry.get("id", entry)
            label = entry.get("label") if isinstance(entry, dict) else None
            model = _make_arena_model(mid)
            if model is None: continue
            name = label or schema_names.get(mid) or getattr(model, 'name', mid)
            t0 = time.time()
            try:
                result = model.analyze(view)
            except Exception as e:
                results.append({"scenario_id": scenario.id, "scenario_name": scenario.name,
                                "category": scenario.category, "model": mid, "model_name": name,
                                "error": str(e), "correct": False, "elapsed_ms": 0})
                continue
            elapsed = (time.time() - t0) * 1000
            correct = False
            if scenario.expected_pass:
                correct = result.pass_chosen
            elif scenario.expected_play and result.choice:
                correct = set(result.choice.card_ids) == set(scenario.expected_play)
            results.append({
                "scenario_id": scenario.id, "scenario_name": scenario.name,
                "category": scenario.category, "model": mid, "model_name": name,
                "choice_type": result.choice.combo_type if result.choice else "NONE",
                "chosen_cards": result.choice.cards if result.choice else [],
                "pass_chosen": result.pass_chosen, "correct": correct,
                "elapsed_ms": result.metrics.get("elapsed_ms", elapsed),
                "timed_out": result.metrics.get("timed_out", False),
            })

    by_model = {}
    for r in results:
        mid = r["model"]
        if mid not in by_model: by_model[mid] = {"total":0,"correct":0,"total_ms":0,"name":r.get("model_name",mid)}
        by_model[mid]["total"] += 1
        if r["correct"]: by_model[mid]["correct"] += 1
        by_model[mid]["total_ms"] += r["elapsed_ms"]
    summary = []
    for mid, s in by_model.items():
        summary.append({"model":mid,"model_name":s["name"],
                        "accuracy":round(s["correct"]/s["total"]*100,1) if s["total"]>0 else 0,
                        "avg_ms":round(s["total_ms"]/s["total"],1) if s["total"]>0 else 0,
                        "correct":s["correct"],"total":s["total"]})
    summary.sort(key=lambda x: x["accuracy"], reverse=True)
    return jsonify({"results": results, "summary": summary})
