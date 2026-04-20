"""File-backed persistence for Discord queue player stats.

Uses ``data/boost/players.json`` (see ``paths.BOOST_PLAYERS_FILE``): one JSON
object mapping Discord user id strings to stat records. Same layout as before;
this module is the only place that reads/writes that file on disk.
"""

from __future__ import annotations

import json
import os

from paths import BOOST_DIR, BOOST_PLAYERS_FILE


def ensure_boost_data_dir() -> None:
    try:
        os.makedirs(BOOST_DIR, exist_ok=True)
    except FileNotFoundError:
        os.makedirs(os.path.dirname(BOOST_DIR), exist_ok=True)
        os.makedirs(BOOST_DIR, exist_ok=True)


def load_players_document() -> dict:
    """Return the parsed JSON object, or ``{}`` if missing or invalid."""
    try:
        with open(BOOST_PLAYERS_FILE, encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        return {}


def save_players_document(stats: dict) -> None:
    """Write ``stats`` atomically (temp file + replace)."""
    ensure_boost_data_dir()
    path = BOOST_PLAYERS_FILE
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    os.replace(tmp, path)
