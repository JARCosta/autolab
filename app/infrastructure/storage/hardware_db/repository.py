"""SQLite repository for hardware metrics."""

from __future__ import annotations

import os
import sqlite3

import paths

HW_SELECT_FIELDS = (
    "timestamp",
    "cpu_load",
    "cpu_clock",
    "cpu_temp",
    "device",
    "ram_percent",
    "swap_percent",
    "gpu_util",
    "gpu_mem_percent",
    "gpu_temp",
    "gpu_clock",
    "pcie_tx_mbps",
    "pcie_rx_mbps",
    "cpu_vendor",
    "gpu_vendor",
)


def init_db() -> None:
    os.makedirs(os.path.dirname(paths.HARDWARE_DB), exist_ok=True)
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hardware_metrics (
                timestamp TEXT NOT NULL,
                cpu_load REAL,
                cpu_clock REAL,
                cpu_temp REAL,
                device TEXT NOT NULL DEFAULT 'local',
                ram_percent REAL,
                swap_percent REAL,
                gpu_util REAL,
                gpu_mem_percent REAL,
                gpu_temp REAL,
                gpu_clock REAL,
                pcie_tx_mbps REAL,
                pcie_rx_mbps REAL,
                cpu_vendor TEXT,
                gpu_vendor TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hw_device_ts
            ON hardware_metrics (device, timestamp)
            """
        )


def prune_before(conn: sqlite3.Connection, cutoff_iso: str) -> None:
    conn.execute("DELETE FROM hardware_metrics WHERE timestamp < ?", (cutoff_iso,))


def insert_metric_row(row_values: tuple) -> None:
    fields = ", ".join(HW_SELECT_FIELDS)
    placeholders = ", ".join("?" * len(HW_SELECT_FIELDS))
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.execute(
            f"INSERT INTO hardware_metrics ({fields}) VALUES ({placeholders})",
            row_values,
        )


def insert_metric_rows(rows_values: list[tuple]) -> None:
    if not rows_values:
        return
    fields = ", ".join(HW_SELECT_FIELDS)
    placeholders = ", ".join("?" * len(HW_SELECT_FIELDS))
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        for row_values in rows_values:
            conn.execute(
                f"INSERT INTO hardware_metrics ({fields}) VALUES ({placeholders})",
                row_values,
            )


def list_device_names(default_device: str) -> list[str]:
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        cur = conn.execute(
            "SELECT DISTINCT device FROM hardware_metrics ORDER BY device"
        )
        seen = [row[0] for row in cur.fetchall() if row[0]]
    out: list[str] = []
    if default_device not in seen:
        out.append(default_device)
    out.extend(seen)
    return out


def reassign_device_metrics(source_device: str, target_device: str) -> int:
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        cur = conn.execute(
            "UPDATE hardware_metrics SET device = ? WHERE device = ?",
            (target_device, source_device),
        )
        moved = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    return int(moved)


def get_latest_metric(device: str) -> dict | None:
    fields = ", ".join(HW_SELECT_FIELDS)
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"""
            SELECT {fields}
            FROM hardware_metrics
            WHERE device = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (device,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_rows_since(device: str, since_iso: str, cap: int) -> list[dict]:
    fields = ", ".join(HW_SELECT_FIELDS)
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"""
            SELECT {fields}
            FROM hardware_metrics
            WHERE device = ?
              AND julianday(replace(timestamp, 'Z', '+00:00')) > julianday(replace(?, 'Z', '+00:00'))
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (device, since_iso, cap),
        )
        return [dict(r) for r in cur.fetchall()]


def get_rows_since_cutoff(device: str, cutoff_iso: str) -> list[dict]:
    fields = ", ".join(HW_SELECT_FIELDS)
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"""
            SELECT {fields}
            FROM hardware_metrics
            WHERE device = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (device, cutoff_iso),
        )
        return [dict(r) for r in cur.fetchall()]


def count_rows_since_cutoff(device: str, cutoff_iso: str) -> int:
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        cur = conn.execute(
            """
            SELECT COUNT(*)
            FROM hardware_metrics
            WHERE device = ? AND timestamp >= ?
            """,
            (device, cutoff_iso),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def get_rows_since_cutoff_strided(
    device: str, cutoff_iso: str, stride: int
) -> list[dict]:
    fields = ", ".join(HW_SELECT_FIELDS)
    step = max(int(stride), 1)
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"""
            WITH bounds AS (
                SELECT
                    MIN(rowid) AS min_rowid,
                    MAX(rowid) AS max_rowid
                FROM hardware_metrics
                WHERE device = ? AND timestamp >= ?
            )
            SELECT {fields}
            FROM hardware_metrics
            WHERE device = ? AND timestamp >= ?
              AND (
                  (rowid - (SELECT min_rowid FROM bounds)) % ? = 0
                  OR rowid = (SELECT min_rowid FROM bounds)
                  OR rowid = (SELECT max_rowid FROM bounds)
              )
            ORDER BY timestamp ASC
            """,
            (device, cutoff_iso, device, cutoff_iso, step),
        )
        return [dict(r) for r in cur.fetchall()]
