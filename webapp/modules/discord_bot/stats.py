"""Read-only leaderboard rows for the Discord dashboard (Flask)."""

from app.infrastructure.storage.discord_db import load_players_document


def load_leaderboard_rows() -> list[dict]:
    """Return sorted rows for the web dashboard (Discord snowflake IDs as keys)."""
    raw = load_players_document()
    if not raw:
        return []

    rows: list[dict] = []
    for uid, data in raw.items():
        if not isinstance(data, dict):
            continue
        wins = int(data.get("wins", 0))
        losses = int(data.get("losses", 0))
        draws = int(data.get("draws", 0))
        pts = int(data.get("points", 1000))
        total = wins + losses
        wr = round((wins / total * 100), 1) if total > 0 else None
        rows.append({
            "id": str(uid),
            "name": (data.get("name") or "Unknown").strip() or "Unknown",
            "points": pts,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": wr,
        })

    rows.sort(key=lambda r: r["points"], reverse=True)
    return rows
