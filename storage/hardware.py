"""Hardware metrics storage (SQLite) and device naming helpers.

Machines send samples via HTTP (see ``hardware_client`` / ``hardware_push_agent``);
``/api/monitor/push`` writes rows here. The monitor blueprint only reads this DB for the UI.
"""

from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import paths
from hardware_client import get_local_device_name, normalize_device_name
from logging_config import setup_logging

log = setup_logging("hardware")

# Drop hardware rows older than this to cap DB size (~2.6M rows/month at 1 Hz per device).
HARDWARE_RETENTION_DAYS = 30

# Prune old rows every N inserts (at 1 Hz, 600 ~= every 10 minutes).
_PRUNE_EVERY_N_INSERTS = 600

_insert_count = 0

_HW_EXTRA_COLS = (
    ("ram_percent", "REAL"),
    ("swap_percent", "REAL"),
    ("gpu_util", "REAL"),
    ("gpu_mem_percent", "REAL"),
    ("gpu_temp", "REAL"),
    ("gpu_clock", "REAL"),
    ("pcie_tx_mbps", "REAL"),
    ("pcie_rx_mbps", "REAL"),
    ("cpu_vendor", "TEXT"),
    ("gpu_vendor", "TEXT"),
)

_HW_SELECT_FIELDS = (
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


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_client_timestamp(raw: str | None) -> str:
    """Use client-supplied ISO time when valid; else server time."""
    if not raw or not isinstance(raw, str):
        return _iso_utc_now()
    s = raw.strip()
    if not s:
        return _iso_utc_now()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return _iso_utc_now()


def _float_field(sample: dict[str, Any], key: str) -> float | None:
    v = sample.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_ALLOWED_VENDORS = frozenset({"intel", "amd", "nvidia", "unknown"})


def _norm_vendor_value(v: str | None) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    if s not in _ALLOWED_VENDORS:
        return None
    return s


def _vendor_field(sample: dict[str, Any], key: str) -> str | None:
    v = sample.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        v = str(v)
    s = v.strip().lower()
    if not s or len(s) > 16:
        return None
    if s not in _ALLOWED_VENDORS:
        return None
    return s


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(hardware_metrics)")
    cols = {row[1] for row in cur.fetchall()}
    if "device" not in cols:
        conn.execute(
            "ALTER TABLE hardware_metrics ADD COLUMN device TEXT DEFAULT 'local'"
        )
        conn.execute(
            "UPDATE hardware_metrics SET device = 'local' WHERE device IS NULL OR device = ''"
        )
        cur = conn.execute("PRAGMA table_info(hardware_metrics)")
        cols = {row[1] for row in cur.fetchall()}
    for col, sql_type in _HW_EXTRA_COLS:
        if col not in cols:
            conn.execute(f"ALTER TABLE hardware_metrics ADD COLUMN {col} {sql_type}")
            cols.add(col)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hw_device_ts
        ON hardware_metrics (device, timestamp)
        """
    )


def _init_db():
    os.makedirs(os.path.dirname(paths.HARDWARE_DB), exist_ok=True)
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hardware_metrics (
                timestamp TEXT NOT NULL,
                cpu_load REAL,
                cpu_clock REAL,
                cpu_temp REAL,
                device TEXT NOT NULL DEFAULT 'local'
            )
            """
        )
        _migrate_schema(conn)


def _prune_before(conn, cutoff_iso: str) -> None:
    conn.execute("DELETE FROM hardware_metrics WHERE timestamp < ?", (cutoff_iso,))


def store_metrics(
    cpu_load: float | None,
    cpu_clock: float | None,
    cpu_temp: float | None,
    *,
    device: str | None = None,
    ram_percent: float | None = None,
    swap_percent: float | None = None,
    gpu_util: float | None = None,
    gpu_mem_percent: float | None = None,
    gpu_temp: float | None = None,
    gpu_clock: float | None = None,
    pcie_tx_mbps: float | None = None,
    pcie_rx_mbps: float | None = None,
    cpu_vendor: str | None = None,
    gpu_vendor: str | None = None,
) -> None:
    global _insert_count
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    _init_db()
    ts = _iso_utc_now()
    cv = _norm_vendor_value(cpu_vendor)
    gv = _norm_vendor_value(gpu_vendor)
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.execute(
            f"""
            INSERT INTO hardware_metrics ({", ".join(_HW_SELECT_FIELDS)})
            VALUES ({", ".join("?" * len(_HW_SELECT_FIELDS))})
            """,
            (
                ts,
                cpu_load,
                cpu_clock,
                cpu_temp,
                dev,
                ram_percent,
                swap_percent,
                gpu_util,
                gpu_mem_percent,
                gpu_temp,
                gpu_clock,
                pcie_tx_mbps,
                pcie_rx_mbps,
                cv,
                gv,
            ),
        )
        _insert_count += 1
        if _insert_count % _PRUNE_EVERY_N_INSERTS == 0:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=HARDWARE_RETENTION_DAYS)
            ).isoformat().replace("+00:00", "Z")
            _prune_before(conn, cutoff)


# Max samples per POST (monitor ingest); ~1 h at 1 Hz.
HARDWARE_PUSH_BATCH_MAX = 3600


def store_metrics_batch(samples: list[dict[str, Any]], *, device: str | None = None) -> None:
    """Insert many rows in one transaction. Each sample may include ``timestamp`` (ISO UTC)."""
    global _insert_count
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    if not samples:
        return
    _init_db()
    fields = ", ".join(_HW_SELECT_FIELDS)
    placeholders = ", ".join("?" * len(_HW_SELECT_FIELDS))
    insert_sql = f"INSERT INTO hardware_metrics ({fields}) VALUES ({placeholders})"
    cutoff_tpl = (
        datetime.now(timezone.utc) - timedelta(days=HARDWARE_RETENTION_DAYS)
    ).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        for sample in samples:
            ts = _parse_client_timestamp(sample.get("timestamp"))
            conn.execute(
                insert_sql,
                (
                    ts,
                    _float_field(sample, "cpu_load"),
                    _float_field(sample, "cpu_clock"),
                    _float_field(sample, "cpu_temp"),
                    dev,
                    _float_field(sample, "ram_percent"),
                    _float_field(sample, "swap_percent"),
                    _float_field(sample, "gpu_util"),
                    _float_field(sample, "gpu_mem_percent"),
                    _float_field(sample, "gpu_temp"),
                    _float_field(sample, "gpu_clock"),
                    _float_field(sample, "pcie_tx_mbps"),
                    _float_field(sample, "pcie_rx_mbps"),
                    _vendor_field(sample, "cpu_vendor"),
                    _vendor_field(sample, "gpu_vendor"),
                ),
            )
            _insert_count += 1
            if _insert_count % _PRUNE_EVERY_N_INSERTS == 0:
                _prune_before(conn, cutoff_tpl)


def list_device_names() -> list[str]:
    """Distinct device ids that have rows, plus local default if missing."""
    _init_db()
    default = get_local_device_name()
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        cur = conn.execute(
            "SELECT DISTINCT device FROM hardware_metrics ORDER BY device"
        )
        seen = [row[0] for row in cur.fetchall() if row[0]]
    out: list[str] = []
    if default not in seen:
        out.append(default)
    out.extend(seen)
    return out


def reassign_device_metrics(source_device: str, target_device: str) -> int:
    """Move all rows from ``source_device`` to ``target_device``.

    Returns number of moved rows.
    """
    src = normalize_device_name(source_device)
    dst = normalize_device_name(target_device)
    if not src or not dst:
        raise ValueError("invalid device name")
    if src == dst:
        return 0

    _init_db()
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        cur = conn.execute(
            "UPDATE hardware_metrics SET device = ? WHERE device = ?",
            (dst, src),
        )
        moved = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    return int(moved)


def get_metrics_history(
    minutes: int = 60,
    max_points: int = 4000,
    *,
    device: str | None = None,
) -> list[dict]:
    """Return metrics since ``minutes`` ago for ``device``, oldest first."""
    _init_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    cutoff = (
        (datetime.now(timezone.utc) - timedelta(minutes=minutes))
        .isoformat()
        .replace("+00:00", "Z")
    )
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.row_factory = sqlite3.Row
        fields = ", ".join(_HW_SELECT_FIELDS)
        cur = conn.execute(
            f"""
            SELECT {fields}
            FROM hardware_metrics
            WHERE device = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (dev, cutoff),
        )
        rows = [dict(r) for r in cur.fetchall()]
    n = len(rows)
    if n <= max_points or n <= 1:
        return rows
    stride = max(1, math.ceil(n / max_points))
    sampled = rows[::stride]
    if sampled[-1]["timestamp"] != rows[-1]["timestamp"]:
        sampled.append(rows[-1])
    return sampled


def get_latest_metric(*, device: str | None = None) -> dict | None:
    _init_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    with sqlite3.connect(paths.HARDWARE_DB) as conn:
        conn.row_factory = sqlite3.Row
        fields = ", ".join(_HW_SELECT_FIELDS)
        cur = conn.execute(
            f"""
            SELECT {fields}
            FROM hardware_metrics
            WHERE device = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (dev,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
