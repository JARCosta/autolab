"""Channel metadata, Twitch accounts (one id per row), and per-channel viewers.

Twitch usernames are case-insensitive; we store a single ``account_id`` as **lowercase**
everywhere (DB, JSON, OAuth keys). Type ``El_Pipow`` in the UI if you like — it becomes
``el_pipow`` in storage. Use :func:`normalize_account_id` before compares or API calls.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

import paths

# Long enough for Docker restarts / brief concurrent readers on ``balance_cache.db``.
_SQLITE_CONNECT_TIMEOUT_S = 60.0
_SQLITE_BUSY_TIMEOUT_MS = 60_000

# JSON / UI payload keys (StreamElements page contract).
_META = frozenset({"StreamElementsId", "SteamId", "FaceitId", "Bettors"})


def normalize_account_id(raw: str) -> str:
    """Canonical Twitch login for DB, viewers, StreamElements URLs, and ``oauth.json`` keys."""
    return (raw or "").strip().lower()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(paths.BALANCE_DB, timeout=_SQLITE_CONNECT_TIMEOUT_S)
    c.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
    c.execute("PRAGMA foreign_keys = ON")
    c.row_factory = sqlite3.Row
    return c


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _migrate_legacy_table_names(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "bettors"):
        if not _table_exists(conn, "accounts"):
            conn.execute("ALTER TABLE bettors RENAME TO accounts")
        else:
            na = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            nb = conn.execute("SELECT COUNT(*) FROM bettors").fetchone()[0]
            if na == 0 and nb > 0:
                conn.execute("INSERT INTO accounts SELECT * FROM bettors")
                conn.execute("DROP TABLE bettors")

    if _table_exists(conn, "channel_bettors"):
        if not _table_exists(conn, "viewers"):
            conn.execute("ALTER TABLE channel_bettors RENAME TO viewers")
        else:
            nv = conn.execute("SELECT COUNT(*) FROM viewers").fetchone()[0]
            ncb = conn.execute("SELECT COUNT(*) FROM channel_bettors").fetchone()[0]
            if nv == 0 and ncb > 0:
                cb_cols = {row[1] for row in conn.execute("PRAGMA table_info(channel_bettors)")}
                src_acct = "account_id" if "account_id" in cb_cols else "bettor_id"
                conn.execute(
                    f"""
                    INSERT INTO viewers (channel, account_id, is_bettor)
                    SELECT channel, {src_acct}, is_bettor FROM channel_bettors
                    """
                )
                conn.execute("DROP TABLE channel_bettors")


def _ensure_viewers_account_id_column(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "viewers"):
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(viewers)")}
    if "account_id" in cols:
        return
    if "bettor_id" in cols:
        conn.execute("ALTER TABLE viewers RENAME COLUMN bettor_id TO account_id")


def _migrate_accounts_legacy_id_twitch(conn: sqlite3.Connection) -> None:
    """``id`` + ``twitch_login`` → single ``account_id`` (lowercase)."""
    if not _table_exists(conn, "accounts"):
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    if "id" not in cols:
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("ALTER TABLE accounts RENAME TO accounts_legacy")
    conn.execute(
        """
        CREATE TABLE accounts (
            account_id TEXT NOT NULL PRIMARY KEY,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    best_order: dict[str, int] = {}
    if "twitch_login" in cols:
        rows = conn.execute(
            "SELECT id, twitch_login, sort_order FROM accounts_legacy"
        ).fetchall()
        for row in rows:
            id_raw, tw_raw, so = row[0], row[1], row[2]
            aid = normalize_account_id((tw_raw or id_raw or "").strip())
            if not aid:
                continue
            so = int(so) if so is not None else 0
            if aid not in best_order or so < best_order[aid]:
                best_order[aid] = so
    else:
        rows = conn.execute("SELECT id, sort_order FROM accounts_legacy").fetchall()
        for row in rows:
            id_raw, so = row[0], row[1]
            aid = normalize_account_id((id_raw or "").strip())
            if not aid:
                continue
            so = int(so) if so is not None else 0
            if aid not in best_order or so < best_order[aid]:
                best_order[aid] = so

    for aid, so in sorted(best_order.items(), key=lambda x: (x[1], x[0])):
        conn.execute(
            "INSERT INTO accounts (account_id, sort_order) VALUES (?, ?)",
            (aid, so),
        )

    conn.execute("UPDATE viewers SET account_id = lower(trim(account_id))")
    try:
        conn.execute("UPDATE balance_history SET bettor = lower(trim(bettor))")
    except sqlite3.OperationalError:
        pass

    next_so = max(best_order.values(), default=-1) + 1
    orphans = conn.execute(
        """
        SELECT DISTINCT account_id FROM viewers
        WHERE account_id NOT IN (SELECT account_id FROM accounts)
        """
    ).fetchall()
    for (oid,) in orphans:
        c = normalize_account_id(oid or "")
        if not c:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO accounts (account_id, sort_order) VALUES (?, ?)",
            (c, next_so),
        )
        next_so += 1

    # Renaming ``accounts`` → ``accounts_legacy`` reparents viewers' FK to the legacy
    # table; DROP then leaves FK pointing at a missing table. Rebuild viewers so FK
    # targets ``accounts`` again.
    _rebuild_viewers_table_fk_to_accounts()
    conn.execute("DROP TABLE accounts_legacy")
    conn.execute("PRAGMA foreign_keys=ON")


def _rebuild_viewers_table_fk_to_accounts() -> None:
    """Recreate ``viewers`` so ``account_id`` references ``accounts`` (not a renamed table).

    Uses a **separate** SQLite connection from the one running ``init_channel_tables``.
    Rebuilding on the same connection can raise ``OperationalError: database table is locked``
    after earlier DDL/PRAGMA work on that connection.
    """
    script = """
        DROP TABLE IF EXISTS viewers_rebuild;
        CREATE TABLE viewers_rebuild (
            channel TEXT NOT NULL,
            account_id TEXT NOT NULL,
            is_bettor INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (channel, account_id),
            FOREIGN KEY (channel) REFERENCES channels(name) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id)
        );
        INSERT INTO viewers_rebuild (channel, account_id, is_bettor)
        SELECT channel, account_id, is_bettor FROM viewers;
        DROP TABLE viewers;
        ALTER TABLE viewers_rebuild RENAME TO viewers;
        CREATE INDEX IF NOT EXISTS idx_viewers_channel ON viewers (channel);
        """
    delay = 0.05
    last_err: sqlite3.OperationalError | None = None
    for attempt in range(8):
        try:
            with sqlite3.connect(paths.BALANCE_DB, timeout=_SQLITE_CONNECT_TIMEOUT_S) as c:
                c.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
                if not _table_exists(c, "viewers"):
                    return
                c.execute("PRAGMA foreign_keys=OFF")
                c.executescript(script)
            return
        except sqlite3.OperationalError as e:
            last_err = e
            msg = str(e).lower()
            if "locked" not in msg or attempt == 7:
                raise
            time.sleep(delay)
            delay = min(1.0, delay * 2)
    assert last_err is not None
    raise last_err


def _repair_viewers_fk_if_broken(_conn: sqlite3.Connection) -> None:
    """Fix DBs where ``viewers.account_id`` still references a dropped ``accounts_legacy``."""
    # Uses a dedicated connection; the init connection can otherwise hit SQLITE_LOCKED on DROP.
    with sqlite3.connect(paths.BALANCE_DB, timeout=_SQLITE_CONNECT_TIMEOUT_S) as c:
        c.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
        if not _table_exists(c, "viewers") or not _table_exists(c, "accounts"):
            return
        fk_rows = list(c.execute("PRAGMA foreign_key_list(viewers)"))
    broken = any(
        row[3] == "account_id" and row[2] != "accounts" for row in fk_rows
    )
    if broken:
        _rebuild_viewers_table_fk_to_accounts()


def init_channel_tables(conn: sqlite3.Connection) -> None:
    _migrate_legacy_table_names(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT NOT NULL PRIMARY KEY,
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS channels (
            name TEXT NOT NULL PRIMARY KEY,
            streamelements_id TEXT NOT NULL,
            steam_id TEXT,
            faceit_id TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS viewers (
            channel TEXT NOT NULL,
            account_id TEXT NOT NULL,
            is_bettor INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (channel, account_id),
            FOREIGN KEY (channel) REFERENCES channels(name) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id)
        );

        CREATE INDEX IF NOT EXISTS idx_viewers_channel ON viewers (channel);
        """
    )
    _ensure_viewers_account_id_column(conn)
    _migrate_accounts_legacy_id_twitch(conn)
    _repair_viewers_fk_if_broken(conn)
    conn.execute("PRAGMA foreign_keys=ON")


def _next_account_sort(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM accounts").fetchone()
    return int(row["n"])


def _next_channel_sort(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM channels").fetchone()
    return int(row["n"])


def _canonical_account_from_entry(key: str, meta: Any) -> str:
    """Snapshot / import: object key or legacy ``{"twitch": "..."}`` → normalized id."""
    if isinstance(meta, dict) and meta.get("twitch"):
        return normalize_account_id(str(meta["twitch"]))
    return normalize_account_id(key)


def _insert_accounts_dict(conn: sqlite3.Connection, accounts: dict[str, Any]) -> None:
    ordered: list[str] = []
    for key, u in accounts.items():
        aid = _canonical_account_from_entry(key, u)
        if not aid or aid in ordered:
            continue
        ordered.append(aid)
    for i, aid in enumerate(ordered):
        conn.execute(
            "INSERT INTO accounts (account_id, sort_order) VALUES (?, ?)",
            (aid, i),
        )


def _insert_channels_nested(conn: sqlite3.Connection, nested: dict[str, Any]) -> None:
    for i, (ch, meta) in enumerate(nested.items()):
        if not isinstance(meta, dict):
            raise ValueError(f"channel {ch!r}: expected object")
        sid = meta.get("StreamElementsId")
        if not sid:
            raise ValueError(f"channel {ch!r}: missing StreamElementsId")
        name = ch.lower()
        conn.execute(
            """
            INSERT INTO channels (name, streamelements_id, steam_id, faceit_id, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, str(sid), meta.get("SteamId"), meta.get("FaceitId"), i),
        )
    known = {r["account_id"] for r in conn.execute("SELECT account_id FROM accounts")}
    for ch, meta in nested.items():
        name = ch.lower()
        for aid_raw, is_b in (meta.get("Bettors") or {}).items():
            aid = normalize_account_id(aid_raw)
            if aid not in known:
                raise ValueError(f"unknown account {aid_raw!r}")
            conn.execute(
                """
                INSERT INTO viewers (channel, account_id, is_bettor)
                VALUES (?, ?, ?)
                """,
                (name, aid, 1 if is_b else 0),
            )


def viewers_for_channel(channel: str) -> list[tuple[str, bool]]:
    """Each viewer: ``(account_id, is_bettor)``, sorted by ``account_id``."""
    ch = channel.lower()
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT account_id, is_bettor FROM viewers
            WHERE channel = ? ORDER BY account_id
            """,
            (ch,),
        )
        return [(r["account_id"], bool(r["is_bettor"])) for r in cur.fetchall()]


def export_channels_snapshot() -> dict[str, Any]:
    """JSON backup: ``accounts`` (keys = lowercase ids) + ``channels``."""
    accts = all_accounts()
    with _conn() as conn:
        cur = conn.execute(
            "SELECT name, streamelements_id, steam_id, faceit_id, sort_order FROM channels ORDER BY sort_order, name"
        )
        channels_out: dict[str, Any] = {}
        for row in cur.fetchall():
            ch = row["name"]
            base = _as_ui_channel_row(row)
            base["Bettors"] = _viewer_flags_for_channel(conn, ch)
            channels_out[ch] = base
    return {"accounts": accts, "channels": channels_out}


def import_channels_snapshot(data: dict[str, Any]) -> None:
    """Replace accounts/channels/viewers from snapshot JSON (``balance_history`` unchanged)."""
    if not isinstance(data, dict):
        raise ValueError("snapshot must be a JSON object")
    accounts = data.get("accounts") or data.get("bettors") or {}
    nested = data.get("channels") or data.get("STREAMELEMENTS") or {}
    if not isinstance(accounts, dict) or not isinstance(nested, dict):
        raise ValueError("accounts and channels must be objects")
    if not accounts:
        raise ValueError("accounts must be non-empty")
    with _conn() as conn:
        init_channel_tables(conn)
        conn.executescript("DELETE FROM viewers; DELETE FROM accounts; DELETE FROM channels;")
        _insert_accounts_dict(conn, accounts)
        _insert_channels_nested(conn, nested)


def add_account(raw_account_id: str) -> None:
    """Register one Twitch account; ``raw_account_id`` is normalized to lowercase."""
    aid = normalize_account_id(raw_account_id)
    if not aid:
        raise ValueError("account id required")
    with _conn() as conn:
        init_channel_tables(conn)
        if conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (aid,)).fetchone():
            raise ValueError(f"account {aid!r} already exists")
        conn.execute(
            "INSERT INTO accounts (account_id, sort_order) VALUES (?, ?)",
            (aid, _next_account_sort(conn)),
        )


def add_channel_with_viewers(
    name: str,
    streamelements_id: str,
    *,
    steam_id: str | None = None,
    faceit_id: str | None = None,
    viewers_map: dict[str, bool] | None = None,
) -> None:
    """Insert channel; ``viewers_map`` keys are normalized to match ``accounts``."""
    ch = name.lower().strip()
    sid = streamelements_id.strip()
    if not ch or not sid:
        raise ValueError("channel name and StreamElements id required")
    vmap = viewers_map or {}
    with _conn() as conn:
        init_channel_tables(conn)
        if conn.execute("SELECT 1 FROM channels WHERE name = ?", (ch,)).fetchone():
            raise ValueError(f"channel {ch!r} already exists")
        known = {r["account_id"] for r in conn.execute("SELECT account_id FROM accounts")}
        norm_map = {normalize_account_id(k): v for k, v in vmap.items()}
        for aid in norm_map:
            if aid not in known:
                raise ValueError(f"unknown account {aid!r}")
        conn.execute(
            """
            INSERT INTO channels (name, streamelements_id, steam_id, faceit_id, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ch, sid, steam_id or None, faceit_id or None, _next_channel_sort(conn)),
        )
        for aid, is_b in norm_map.items():
            conn.execute(
                """
                INSERT INTO viewers (channel, account_id, is_bettor)
                VALUES (?, ?, ?)
                """,
                (ch, aid, 1 if is_b else 0),
            )


def list_account_ids_ordered() -> list[str]:
    with _conn() as conn:
        cur = conn.execute("SELECT account_id FROM accounts ORDER BY sort_order, account_id")
        return [r["account_id"] for r in cur.fetchall()]


def list_active_channel_names_ordered() -> list[str]:
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT c.name FROM channels c
            WHERE EXISTS (SELECT 1 FROM viewers v WHERE v.channel = c.name)
            ORDER BY c.sort_order, c.name
            """
        )
        return [r["name"] for r in cur.fetchall()]


def _as_ui_channel_row(row: sqlite3.Row) -> dict[str, Any]:
    d: dict[str, Any] = {"StreamElementsId": row["streamelements_id"]}
    if row["steam_id"]:
        d["SteamId"] = row["steam_id"]
    if row["faceit_id"]:
        d["FaceitId"] = row["faceit_id"]
    return d


def _viewer_flags_for_channel(conn: sqlite3.Connection, channel: str) -> dict[str, bool]:
    cur = conn.execute(
        "SELECT account_id, is_bettor FROM viewers WHERE channel = ? ORDER BY account_id",
        (channel,),
    )
    return {r["account_id"]: bool(r["is_bettor"]) for r in cur.fetchall()}


def active_channels_nested() -> dict[str, Any]:
    """Per channel: StreamElementsId, optional Steam/Faceit, ``Bettors`` map (lowercase keys)."""
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT c.name, c.streamelements_id, c.steam_id, c.faceit_id, c.sort_order
            FROM channels c
            WHERE EXISTS (SELECT 1 FROM viewers v WHERE v.channel = c.name)
            ORDER BY c.sort_order, c.name
            """
        )
        out: dict[str, Any] = {}
        for row in cur.fetchall():
            ch = row["name"]
            base = _as_ui_channel_row(row)
            base["Bettors"] = _viewer_flags_for_channel(conn, ch)
            out[ch] = base
        return out


def get_betors():
    with _conn() as conn:
        cur = conn.execute("SELECT channel, account_id, is_bettor FROM viewers WHERE is_bettor = 1")
        return {r["channel"]: r["account_id"] for r in cur.fetchall()}

def get_bettors_list() -> list[str]:
    with _conn() as conn:
        cur = conn.execute("SELECT account_id FROM viewers WHERE is_bettor = 1")
        return [r["account_id"] for r in cur.fetchall()]

def all_accounts() -> dict[str, dict[str, str]]:
    """Account ids (lowercase) → empty object (snapshot shape; room for future fields)."""
    with _conn() as conn:
        cur = conn.execute("SELECT account_id FROM accounts ORDER BY sort_order, account_id")
        return {r["account_id"]: {} for r in cur.fetchall()}


def all_channel_definitions() -> dict[str, Any]:
    """Every row in ``channels``: name → ``{StreamElementsId, SteamId?, FaceitId?}`` (no Bettors)."""
    with _conn() as conn:
        init_channel_tables(conn)
        cur = conn.execute(
            "SELECT name, streamelements_id, steam_id, faceit_id FROM channels ORDER BY sort_order, name"
        )
        return {row["name"]: _as_ui_channel_row(row) for row in cur.fetchall()}


def upsert_channel_definition(
    name: str,
    streamelements_id: str,
    *,
    steam_id: str | None = None,
    faceit_id: str | None = None,
) -> None:
    """Insert or update ``channels`` row (IDs only; viewers unchanged)."""
    ch = name.lower().strip()
    sid = (streamelements_id or "").strip()
    if not ch or not sid:
        raise ValueError("channel name and streamelements_id required")
    steam = (steam_id or "").strip() or None
    faceit = (faceit_id or "").strip() or None
    with _conn() as conn:
        init_channel_tables(conn)
        if conn.execute("SELECT 1 FROM channels WHERE name = ?", (ch,)).fetchone():
            conn.execute(
                """
                UPDATE channels
                SET streamelements_id = ?, steam_id = ?, faceit_id = ?
                WHERE name = ?
                """,
                (sid, steam, faceit, ch),
            )
        else:
            conn.execute(
                """
                INSERT INTO channels (name, streamelements_id, steam_id, faceit_id, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ch, sid, steam, faceit, _next_channel_sort(conn)),
            )


def betting_channels_api() -> dict[str, Any]:
    """Active sidebar channels, all channel ID rows, and account list."""
    active = active_channels_nested()
    return {
        "channels": active,
        "accounts": list_account_ids_ordered(),
        "channel_defs": all_channel_definitions(),
    }


def get_channel_meta(channel: str) -> dict[str, Any] | None:
    ch = channel.lower()
    with _conn() as conn:
        cur = conn.execute(
            "SELECT name, streamelements_id, steam_id, faceit_id FROM channels WHERE name = ?",
            (ch,),
        )
        row = cur.fetchone()
        return _as_ui_channel_row(row) if row else None


def streamelements_account_id(channel: str) -> str | None:
    meta = get_channel_meta(channel)
    if not meta:
        return None
    sid = meta.get("StreamElementsId")
    return str(sid) if sid else None


def _bettors_map_from_payload(obj: dict[str, Any]) -> dict[str, bool]:
    if "Bettors" in obj:
        raw = obj["Bettors"]
        if not isinstance(raw, dict):
            raise ValueError("Bettors must be an object")
        return {normalize_account_id(k): bool(v) for k, v in raw.items()}
    return {
        normalize_account_id(k): bool(v)
        for k, v in obj.items()
        if k not in _META
    }


def merge_ui_channel_memberships(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("channels object required")
    with _conn() as conn:
        prev = {
            r["name"]
            for r in conn.execute(
                """
                SELECT c.name FROM channels c
                WHERE EXISTS (SELECT 1 FROM viewers v WHERE v.channel = c.name)
                """
            )
        }
        new = {k.lower() for k in payload}
        for ch in prev - new:
            conn.execute("DELETE FROM viewers WHERE channel = ?", (ch,))

        for raw, obj in payload.items():
            ch = raw.lower()
            if not isinstance(obj, dict):
                raise ValueError(f"invalid channel payload: {raw!r}")
            if not conn.execute("SELECT 1 FROM channels WHERE name = ?", (ch,)).fetchone():
                raise ValueError(f"unknown channel {raw!r} — add it in the setup panel or import a snapshot")
            bmap = _bettors_map_from_payload(obj)
            known = {r["account_id"] for r in conn.execute("SELECT account_id FROM accounts")}
            for aid in bmap:
                if aid not in known:
                    raise ValueError(f"unknown account {aid!r}")
            conn.execute("DELETE FROM viewers WHERE channel = ?", (ch,))
            for aid, is_b in bmap.items():
                conn.execute(
                    "INSERT INTO viewers (channel, account_id, is_bettor) VALUES (?, ?, ?)",
                    (ch, aid, 1 if is_b else 0),
                )


