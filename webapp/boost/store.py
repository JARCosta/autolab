"""Sync data layer for the Boost CS2 Custom manager.

Stores player roster and match history as JSON files under DATA_DIR/boost/.
Shares the team-balancing algorithm from the Discord bot (subset-sum DP).
"""

import json
import os
import uuid
from datetime import datetime, timezone

from paths import BOOST_DIR, BOOST_MATCHES_FILE, BOOST_PLAYERS_FILE

PLAYERS_FILE = BOOST_PLAYERS_FILE
MATCHES_FILE = BOOST_MATCHES_FILE
POINTS_DELTA = 25


def _ensure_dir():
    os.makedirs(BOOST_DIR, exist_ok=True)


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_json(path, data):
    _ensure_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

def load_players() -> dict:
    data = _load_json(PLAYERS_FILE)
    return data if isinstance(data, dict) else {}


def save_players(players: dict):
    _save_json(PLAYERS_FILE, players)


def add_player(name: str) -> tuple[str, dict]:
    players = load_players()
    pid = uuid.uuid4().hex[:8]
    while pid in players:
        pid = uuid.uuid4().hex[:8]
    entry = {
        "name": name.strip(),
        "points": 1000,
        "wins": 0,
        "losses": 0,
        "draws": 0,
    }
    players[pid] = entry
    save_players(players)
    return pid, entry


def remove_player(player_id: str) -> bool:
    players = load_players()
    if player_id in players:
        del players[player_id]
        save_players(players)
        return True
    return False


def rename_player(player_id: str, new_name: str) -> bool:
    players = load_players()
    if player_id in players:
        players[player_id]["name"] = new_name.strip()
        save_players(players)
        return True
    return False


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------

def load_matches() -> list:
    data = _load_json(MATCHES_FILE)
    return data if isinstance(data, list) else []


def save_matches(matches: list):
    _save_json(MATCHES_FILE, matches)


def partition_teams(
    player_points: list[tuple[str, int]],
) -> tuple[list[str], list[str]]:
    """Split players into two balanced teams (subset-sum DP).

    Ported from boost_bot/views.py ``_partition_teams``.
    """
    if not player_points:
        return [], []

    n = len(player_points)
    if n % 2 != 0:
        player_points = player_points[:-1]
        n = len(player_points)

    team_size = n // 2
    total_points = sum(pts for _, pts in player_points)
    target = total_points / 2

    dp: dict[tuple[int, int], set[str]] = {(0, 0): set()}
    for pid, pts in player_points:
        new_entries: dict[tuple[int, int], set[str]] = {}
        for (current_sum, count), current_set in dp.items():
            if count < team_size:
                key = (current_sum + pts, count + 1)
                if key not in dp and key not in new_entries:
                    new_entries[key] = current_set | {pid}
        dp.update(new_entries)

    half_subsets = {k: v for k, v in dp.items() if k[1] == team_size}
    if half_subsets:
        best_key = min(half_subsets, key=lambda x: abs(x[0] - target))
        team_a_set = half_subsets[best_key]
        team_a = [pid for pid, _ in player_points if pid in team_a_set]
        team_b = [pid for pid, _ in player_points if pid not in team_a_set]
    else:
        team_a: list[str] = []
        team_b: list[str] = []
        sum_a = sum_b = 0
        for pid, pts in player_points:
            if len(team_a) < team_size and (
                len(team_b) == team_size or sum_a <= sum_b
            ):
                team_a.append(pid)
                sum_a += pts
            else:
                team_b.append(pid)
                sum_b += pts

    return team_a, team_b


def create_match(player_ids: list[str], title: str = "Custom") -> dict | None:
    if len(player_ids) < 2 or len(player_ids) % 2 != 0:
        return None

    players = load_players()
    player_points = []
    for pid in player_ids:
        if pid not in players:
            return None
        player_points.append((pid, players[pid].get("points", 1000)))
    player_points.sort(key=lambda x: x[1], reverse=True)

    team_a, team_b = partition_teams(player_points)

    match = {
        "id": uuid.uuid4().hex[:8],
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "team_a": team_a,
        "team_b": team_b,
        "result": None,
        "points_delta": POINTS_DELTA,
        "player_stats": {},
    }

    matches = load_matches()
    matches.insert(0, match)
    save_matches(matches)
    return match


def record_result(match_id: str, result: str) -> dict | None:
    if result not in ("team_a", "team_b", "draw", "cancelled"):
        return None

    matches = load_matches()
    match = next((m for m in matches if m["id"] == match_id), None)
    if not match or match.get("result") is not None:
        return None

    match["result"] = result
    delta = match.get("points_delta", POINTS_DELTA)

    if result in ("team_a", "team_b"):
        players = load_players()
        winners = match["team_a"] if result == "team_a" else match["team_b"]
        losers = match["team_b"] if result == "team_a" else match["team_a"]
        for pid in winners:
            if pid in players:
                players[pid]["points"] = players[pid].get("points", 1000) + delta
                players[pid]["wins"] = players[pid].get("wins", 0) + 1
        for pid in losers:
            if pid in players:
                players[pid]["points"] = players[pid].get("points", 1000) - delta
                players[pid]["losses"] = players[pid].get("losses", 0) + 1
        save_players(players)
    elif result == "draw":
        players = load_players()
        for pid in match["team_a"] + match["team_b"]:
            if pid in players:
                players[pid]["draws"] = players[pid].get("draws", 0) + 1
        save_players(players)

    save_matches(matches)
    return match


def update_match_stats(match_id: str, player_id: str, stats: dict) -> bool:
    matches = load_matches()
    for m in matches:
        if m["id"] == match_id:
            if "player_stats" not in m:
                m["player_stats"] = {}
            allowed = {"kills", "deaths", "assists", "damage"}
            clean = {}
            for k in allowed:
                v = stats.get(k)
                if v is not None:
                    try:
                        clean[k] = int(v)
                    except (TypeError, ValueError):
                        pass
            m["player_stats"][player_id] = clean
            save_matches(matches)
            return True
    return False
