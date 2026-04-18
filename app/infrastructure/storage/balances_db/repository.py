"""SQLite repository for balance history (latest row per channel/bettor = current)."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

import paths

_BALANCE_DB_TIMEOUT_S = 60.0
_BALANCE_DB_BUSY_TIMEOUT_MS = 60_000


def init_db() -> None:
    """Initialize the balance database."""
    os.makedirs(os.path.dirname(paths.BALANCE_DB), exist_ok=True)
    with sqlite3.connect(paths.BALANCE_DB, timeout=_BALANCE_DB_TIMEOUT_S) as conn:
        conn.execute(f"PRAGMA busy_timeout={_BALANCE_DB_BUSY_TIMEOUT_MS}")
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
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='balance_cache'"
        )
        if cur.fetchone():
            conn.execute(
                """
                INSERT INTO balance_history (channel, bettor, balance, updated_at)
                SELECT channel, bettor, balance, updated_at FROM balance_cache
                """
            )
            conn.execute("DROP TABLE balance_cache")

        from .channels_data import init_channel_tables

        init_channel_tables(conn)


####################################################################################################
# Date/time utilities ##############################################################################
####################################################################################################

def iso_utc_now() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso_utc(s: str) -> datetime | None:
    """Parse ISO 8601 time string to datetime object."""
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None





####################################################################################################
# Balance storage ##########################################################################
####################################################################################################


def _latest_history_subquery() -> str:
    """Latest row per (channel, bettor) by updated_at (ties: one arbitrary row)."""
    return """
        SELECT channel, bettor, balance, updated_at
        FROM (
            SELECT channel, bettor, balance, updated_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY channel, bettor ORDER BY updated_at DESC
                   ) AS rn
            FROM balance_history
        )
        WHERE rn = 1
    """


def get_balance_snapshots() -> dict[tuple[str, str], tuple[int, str]]:
    """Return map of (channel, bettor) to (balance, updated_at) from latest history row each."""
    with sqlite3.connect(paths.BALANCE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(_latest_history_subquery())
        return {(r["channel"], r["bettor"]): (r["balance"], r["updated_at"]) for r in cur}


def get_balance_values() -> dict[tuple[str, str], int]:
    """Return map of (channel, bettor) to balance from latest history row each."""
    with sqlite3.connect(paths.BALANCE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"SELECT channel, bettor, balance FROM ({_latest_history_subquery().strip()}) AS latest"
        )
        return {(r["channel"], r["bettor"]): r["balance"] for r in cur}


def append_balance_snapshot(
    channel: str,
    bettor: str,
    balance: int,
    ts: str,
) -> None:
    """Append a balance reading to history (latest row per key is treated as current)."""
    with sqlite3.connect(paths.BALANCE_DB) as conn:
        conn.execute(
            """
            INSERT INTO balance_history (channel, bettor, balance, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (channel, bettor, balance, ts),
        )

def bulk_refresh_balances(rows: list[tuple[str, str, int, str]]) -> None:
    """Append one history row per (channel, bettor, balance, updated_at)."""
    if not rows:
        return
    with sqlite3.connect(paths.BALANCE_DB) as conn:
        conn.executemany(
            """
            INSERT INTO balance_history (channel, bettor, balance, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )






def get_balance_history_batch(
    keys: list[tuple[str, str]],
    *,
    since_iso: str | None = None,
) -> dict[tuple[str, str], list[dict]]:
    """Return history for each (channel, bettor), oldest first within each series."""
    if not keys:
        return {}
    or_parts = " OR ".join("(channel = ? AND bettor = ?)" for _ in keys)
    where = f"({or_parts})"
    params: list[str | int] = [x for pair in keys for x in pair]
    if since_iso:
        where += " AND updated_at >= ?"
        params.append(since_iso)

    with sqlite3.connect(paths.BALANCE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"""
            SELECT channel, bettor, balance, updated_at
            FROM balance_history
            WHERE {where}
            ORDER BY channel, bettor, updated_at ASC
            """,
            params,
        )
        rows = cur.fetchall()

    out: dict[tuple[str, str], list[dict]] = {k: [] for k in keys}
    for r in rows:
        key = (r["channel"], r["bettor"])
        if key in out:
            out[key].append({"balance": r["balance"], "updated_at": r["updated_at"]})
    return out
