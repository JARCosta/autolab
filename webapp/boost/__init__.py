"""Boost CS2 Custom blueprint: closed-server 5v5 matchmaking UI."""

from flask import Blueprint, jsonify, render_template, request

from webapp.boost.store import (
    add_player,
    create_match,
    load_matches,
    load_players,
    record_result,
    remove_player,
    rename_player,
    update_match_stats,
)

boost_bp = Blueprint("boost", __name__, template_folder="templates")


@boost_bp.route("/boost")
def boost():
    return render_template("boost.html")


@boost_bp.route("/api/boost/players")
def api_players():
    players = load_players()
    result = []
    for pid, data in players.items():
        result.append({
            "id": pid,
            "name": data.get("name", "Unknown"),
            "points": data.get("points", 1000),
            "wins": data.get("wins", 0),
            "losses": data.get("losses", 0),
            "draws": data.get("draws", 0),
        })
    result.sort(key=lambda x: x["points"], reverse=True)
    return jsonify({"players": result})


@boost_bp.route("/api/boost/players", methods=["POST"])
def api_add_player():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    pid, entry = add_player(name)
    return jsonify({"id": pid, **entry})


@boost_bp.route("/api/boost/players/<player_id>", methods=["DELETE"])
def api_remove_player(player_id):
    if remove_player(player_id):
        return jsonify({"ok": True})
    return jsonify({"error": "player not found"}), 404


@boost_bp.route("/api/boost/players/<player_id>", methods=["PATCH"])
def api_rename_player(player_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if rename_player(player_id, name):
        return jsonify({"ok": True})
    return jsonify({"error": "player not found"}), 404


@boost_bp.route("/api/boost/queue", methods=["POST"])
def api_create_queue():
    data = request.get_json(silent=True) or {}
    player_ids = data.get("players", [])
    title = data.get("title", "Custom")
    if not isinstance(player_ids, list) or len(player_ids) < 2:
        return jsonify({"error": "need at least 2 players"}), 400
    if len(player_ids) % 2 != 0:
        return jsonify({"error": "need an even number of players"}), 400
    match = create_match(player_ids, title=title)
    if not match:
        return jsonify({"error": "could not create match"}), 400
    return jsonify(match)


@boost_bp.route("/api/boost/matches")
def api_matches():
    matches = load_matches()
    players = load_players()
    for m in matches:
        m["team_a_names"] = [
            players.get(pid, {}).get("name", "Unknown")
            for pid in m.get("team_a", [])
        ]
        m["team_b_names"] = [
            players.get(pid, {}).get("name", "Unknown")
            for pid in m.get("team_b", [])
        ]
    return jsonify({"matches": matches})


@boost_bp.route("/api/boost/match/<match_id>/result", methods=["POST"])
def api_record_result(match_id):
    data = request.get_json(silent=True) or {}
    result = data.get("result")
    match = record_result(match_id, result)
    if not match:
        return jsonify({"error": "invalid request"}), 400
    return jsonify(match)


@boost_bp.route("/api/boost/match/<match_id>/stats", methods=["POST"])
def api_update_stats(match_id):
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id")
    stats = data.get("stats", {})
    if not player_id:
        return jsonify({"error": "player_id required"}), 400
    if update_match_stats(match_id, player_id, stats):
        return jsonify({"ok": True})
    return jsonify({"error": "match not found"}), 404
