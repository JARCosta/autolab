"""Shared balance data for on-demand views (Telegram command and web UI)."""
import sqlite3
from datetime import datetime

import config
import paths
from stream_elements import utils


def _get_bettors_channels():
    bettors = list(config.BETTORS.keys())
    channels = list(config.CHANNELS.keys())
    return bettors, channels


def get_balance_rows():
    """Fetch live from StreamElements; return list of (channel, [(bettor, balance), ...])."""
    bettors, channels = _get_bettors_channels()
    return [
        (channel, [(bettor, utils.get_balance(channel, bettor)) for bettor in bettors])
        for channel in channels
    ]


def _init_db():
    """Ensure DATA_DIR and balance_cache table exist."""
    import os
    os.makedirs(os.path.dirname(paths.BALANCE_CACHE_DB), exist_ok=True)
    with sqlite3.connect(paths.BALANCE_CACHE_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS balance_cache (
                channel TEXT,
                bettor TEXT,
                balance INTEGER,
                updated_at TEXT,
                PRIMARY KEY (channel, bettor)
            )
            """
        )


def get_balance_rows_from_cache():
    """Read balance table from SQLite cache (instant). Returns same shape as get_balance_rows()."""
    _init_db()
    bettors, channels = _get_bettors_channels()
    with sqlite3.connect(paths.BALANCE_CACHE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT channel, bettor, balance FROM balance_cache"
        )
        by_key = {(r["channel"], r["bettor"]): r["balance"] for r in cur}
    rows = []
    for channel in channels:
        cells = [(b, by_key.get((channel, b), "—")) for b in bettors]
        rows.append((channel, cells))
    return rows


def fetch_and_cache_balances():
    """Fetch live from StreamElements, write to SQLite, return balance rows."""
    rows = get_balance_rows()
    _init_db()
    now = datetime.utcnow().isoformat() + "Z"
    with sqlite3.connect(paths.BALANCE_CACHE_DB) as conn:
        for channel, cells in rows:
            for bettor, balance in cells:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO balance_cache (channel, bettor, balance, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (channel, bettor, balance, now),
                )
    return rows
