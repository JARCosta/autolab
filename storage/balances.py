"""Balance persistence and caching (SQLite).

This module is intentionally UI-agnostic so it can be used from:
- webapp (dashboard / telegram)
- stream_elements (IRC/betting events)
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

import config
import paths
from stream_elements import utils


def _get_bettors_channels():
    bettors = list(config.BETTORS.keys())
    channels = list(config.CHANNELS.keys())
    return bettors, channels


def _init_db():
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS balance_history (
                channel TEXT,
                bettor TEXT,
                balance INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_balance_history_lookup
            ON balance_history (channel, bettor, updated_at)
            """
        )


def _parse_iso_utc(s: str) -> datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_balance_rows_from_cache():
    """Read balance table from SQLite cache (instant)."""
    _init_db()
    bettors, channels = _get_bettors_channels()
    with sqlite3.connect(paths.BALANCE_CACHE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT channel, bettor, balance FROM balance_cache")
        by_key = {(r["channel"], r["bettor"]): r["balance"] for r in cur}

    rows = []
    for channel in channels:
        cells = [(b, by_key.get((channel, b), "—")) for b in bettors]
        rows.append((channel, cells))
    return rows


def record_balance_snapshot(channel: str, bettor: str, balance: int, updated_at: str | None = None) -> None:
    """Upsert cache and append to history if the value changed."""
    _init_db()
    ts = updated_at or _iso_utc_now()
    with sqlite3.connect(paths.BALANCE_CACHE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT balance FROM balance_cache WHERE channel = ? AND bettor = ?",
            (channel, bettor),
        )
        row = cur.fetchone()
        prev_balance = row["balance"] if row else None

        conn.execute(
            """
            INSERT OR REPLACE INTO balance_cache (channel, bettor, balance, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (channel, bettor, balance, ts),
        )
        if prev_balance is None or prev_balance != balance:
            conn.execute(
                """
                INSERT INTO balance_history (channel, bettor, balance, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (channel, bettor, balance, ts),
            )


def refresh_and_record_balance(channel: str, bettor: str) -> int:
    """Fetch live balance for (channel, bettor) and persist if changed."""
    bal = utils.get_balance(channel, bettor)
    record_balance_snapshot(channel, bettor, bal)
    return bal


def fetch_and_cache_balances(min_age_seconds: int = 0):
    """Return list of (channel, [(bettor, balance), ...]).

    If min_age_seconds > 0, only fetch entries whose cached updated_at is older
    than that threshold (or missing). Fresh entries are served from cache.
    """
    _init_db()
    now = _iso_utc_now()
    now_dt = _parse_iso_utc(now) or datetime.now(timezone.utc)

    bettors, channels = _get_bettors_channels()
    with sqlite3.connect(paths.BALANCE_CACHE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT channel, bettor, balance, updated_at FROM balance_cache")
        cache = {(r["channel"], r["bettor"]): (r["balance"], r["updated_at"]) for r in cur}

        rows_out: list[tuple[str, list[tuple[str, int]]]] = []
        for channel in channels:
            cells_out: list[tuple[str, int]] = []
            for bettor in bettors:
                cached = cache.get((channel, bettor))
                should_fetch = True
                if cached is not None and min_age_seconds > 0:
                    _, cached_ts = cached
                    cached_dt = _parse_iso_utc(cached_ts)
                    if cached_dt is not None:
                        age = (now_dt - cached_dt).total_seconds()
                        if age < float(min_age_seconds):
                            should_fetch = False

                if cached is not None and not should_fetch:
                    balance = int(cached[0])
                else:
                    balance = utils.get_balance(channel, bettor)

                prev_balance = cached[0] if cached is not None else None
                conn.execute(
                    """
                    INSERT OR REPLACE INTO balance_cache (channel, bettor, balance, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (channel, bettor, balance, now),
                )
                if prev_balance is None or prev_balance != balance:
                    conn.execute(
                        """
                        INSERT INTO balance_history (channel, bettor, balance, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (channel, bettor, balance, now),
                    )

                cells_out.append((bettor, balance))
            rows_out.append((channel, cells_out))

    return rows_out


def get_balance_rows():
    """Fetch live from StreamElements (no cache)."""
    bettors, channels = _get_bettors_channels()
    return [
        (channel, [(bettor, utils.get_balance(channel, bettor)) for bettor in bettors])
        for channel in channels
    ]


def get_balance_history(channel: str, bettor: str, limit: int = 100):
    """Return time series of balances for a given (channel, bettor), oldest first."""
    _init_db()
    with sqlite3.connect(paths.BALANCE_CACHE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT balance, updated_at
            FROM balance_history
            WHERE channel = ? AND bettor = ?
            ORDER BY updated_at ASC
            """,
            (channel, bettor),
        )
        rows = cur.fetchall()
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    return [{"balance": r["balance"], "updated_at": r["updated_at"]} for r in rows]

