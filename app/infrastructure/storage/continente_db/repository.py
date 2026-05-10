"""SQLite repository for Continente product/rating/price tracking."""

from __future__ import annotations

import os
import sqlite3

import paths


def init_db() -> None:
    os.makedirs(os.path.dirname(paths.CONTINENTE_DB), exist_ok=True)
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS continente_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT,
                name TEXT NOT NULL,
                regular_price REAL,
                current_price REAL,
                currency TEXT NOT NULL DEFAULT 'EUR',
                likes INTEGER NOT NULL DEFAULT 0,
                dislikes INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL,
                notify_enabled INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS continente_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                seen_at TEXT NOT NULL,
                current_price REAL,
                regular_price REAL,
                FOREIGN KEY(product_id) REFERENCES continente_products(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS continente_alert_state (
                product_id INTEGER PRIMARY KEY,
                last_alert_price REAL,
                last_alert_at TEXT,
                FOREIGN KEY(product_id) REFERENCES continente_products(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_continente_products_external_id "
            "ON continente_products(external_id) WHERE external_id IS NOT NULL"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_continente_history_product_seen "
            "ON continente_price_history(product_id, seen_at)"
        )


def list_products() -> list[dict]:
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, external_id, name, regular_price, current_price, currency,
                   likes, dislikes, last_seen_at, notify_enabled
            FROM continente_products
            ORDER BY likes DESC, (likes - dislikes) DESC, name ASC
            """
        )
        return [dict(r) for r in cur.fetchall()]


def upsert_product(
    *,
    external_id: str | None,
    name: str,
    regular_price: float | None,
    current_price: float | None,
    currency: str,
    seen_at: str,
) -> int:
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        conn.row_factory = sqlite3.Row
        if external_id:
            cur = conn.execute(
                "SELECT id FROM continente_products WHERE external_id = ?",
                (external_id,),
            )
            row = cur.fetchone()
            if row:
                product_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE continente_products
                    SET name = ?, regular_price = ?, current_price = ?, currency = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (name, regular_price, current_price, currency, seen_at, product_id),
                )
                return product_id

        cur = conn.execute(
            """
            INSERT INTO continente_products (
                external_id, name, regular_price, current_price, currency, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (external_id, name, regular_price, current_price, currency, seen_at),
        )
        return int(cur.lastrowid)


def insert_price_history(
    product_id: int, seen_at: str, current_price: float | None, regular_price: float | None
) -> None:
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        conn.execute(
            """
            INSERT INTO continente_price_history (product_id, seen_at, current_price, regular_price)
            VALUES (?, ?, ?, ?)
            """,
            (product_id, seen_at, current_price, regular_price),
        )


def set_vote(product_id: int, delta: int) -> bool:
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        cur = conn.execute("SELECT id FROM continente_products WHERE id = ?", (product_id,))
        if not cur.fetchone():
            return False
        if delta > 0:
            conn.execute(
                "UPDATE continente_products SET likes = likes + 1 WHERE id = ?",
                (product_id,),
            )
        else:
            conn.execute(
                "UPDATE continente_products SET dislikes = dislikes + 1 WHERE id = ?",
                (product_id,),
            )
        return True


def set_notify_enabled(product_id: int, enabled: bool) -> bool:
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        cur = conn.execute("SELECT id FROM continente_products WHERE id = ?", (product_id,))
        if not cur.fetchone():
            return False
        conn.execute(
            "UPDATE continente_products SET notify_enabled = ? WHERE id = ?",
            (1 if enabled else 0, product_id),
        )
        return True


def get_alert_state(product_id: int) -> dict | None:
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT product_id, last_alert_price, last_alert_at FROM continente_alert_state WHERE product_id = ?",
            (product_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def upsert_alert_state(product_id: int, last_alert_price: float | None, last_alert_at: str) -> None:
    with sqlite3.connect(paths.CONTINENTE_DB) as conn:
        conn.execute(
            """
            INSERT INTO continente_alert_state (product_id, last_alert_price, last_alert_at)
            VALUES (?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                last_alert_price = excluded.last_alert_price,
                last_alert_at = excluded.last_alert_at
            """,
            (product_id, last_alert_price, last_alert_at),
        )
