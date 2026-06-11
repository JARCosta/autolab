"""Service layer for hardware ingestion/query logic."""

from __future__ import annotations

import math
import os
import re
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
import json

from . import repository

_DEVICE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

# Drop hardware rows older than this to cap DB size (~2.6M rows/month at 1 Hz per device).
HARDWARE_RETENTION_DAYS = 7

# Prune old rows every N inserts (at 1 Hz, 600 ~= every 10 minutes).
_PRUNE_EVERY_N_INSERTS = 600

_insert_count = 0

_ALLOWED_VENDORS = frozenset({"intel", "amd", "nvidia", "unknown"})

# Max samples per POST (monitor ingest); 6 h at 1 Hz.
HARDWARE_PUSH_BATCH_MAX = 21600


def normalize_device_name(name: str | None) -> str:
    """Return a safe device id, or empty string if invalid."""
    if not name or not isinstance(name, str):
        return ""
    s = name.strip()
    if not s or len(s) > 64 or not _DEVICE_RE.match(s):
        return ""
    return s


def _installer_computer_name() -> str:
    if os.name == "nt":
        n = os.environ.get("COMPUTERNAME", "").strip()
        if n:
            return n
    n = os.environ.get("HOSTNAME", "").strip()
    if n:
        return n.split(".")[0]
    try:
        return socket.gethostname().split(".")[0]
    except OSError:
        return ""


def get_local_device_name() -> str:
    env = normalize_device_name(os.getenv("HARDWARE_DEVICE_NAME", "").strip())
    if env:
        return env
    raw = _installer_computer_name()
    return normalize_device_name(raw) or "local"


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def _ensure_db() -> None:
    repository.init_db()


def store_metrics(
    cpu_load: float | None,
    cpu_clock: float | None,
    cpu_clock_cores: Any | None,
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
    _ensure_db()
    ts = _iso_utc_now()
    cv = _norm_vendor_value(cpu_vendor)
    gv = _norm_vendor_value(gpu_vendor)

    repository.insert_metric_row(
        (
            ts,
            cpu_load,
            cpu_clock,
            (json.dumps(cpu_clock_cores) if cpu_clock_cores is not None else None),
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
        )
    )
    _insert_count += 1
    if _insert_count % _PRUNE_EVERY_N_INSERTS == 0:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=HARDWARE_RETENTION_DAYS)
        ).isoformat().replace("+00:00", "Z")
        # run prune in a short dedicated transaction
        import sqlite3
        import paths

        with sqlite3.connect(paths.HARDWARE_DB) as conn:
            repository.prune_before(conn, cutoff)


def store_metrics_batch(samples: list[dict[str, Any]], *, device: str | None = None) -> None:
    """Insert many rows in one transaction. Each sample may include ``timestamp`` (ISO UTC)."""
    global _insert_count
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    if not samples:
        return
    _ensure_db()

    rows_values: list[tuple] = []
    for sample in samples:
        ts = _parse_client_timestamp(sample.get("timestamp"))
        raw_cores = sample.get("cpu_clock_cores")
        if raw_cores is None:
            cores_val = None
        elif isinstance(raw_cores, str):
            cores_val = raw_cores
        else:
            try:
                cores_val = json.dumps(raw_cores)
            except (TypeError, ValueError):
                cores_val = None
        rows_values.append(
            (
                ts,
                _float_field(sample, "cpu_load"),
                _float_field(sample, "cpu_clock"),
                cores_val,
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
            )
        )

    repository.insert_metric_rows(rows_values)
    _insert_count += len(rows_values)
    if _insert_count % _PRUNE_EVERY_N_INSERTS == 0:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=HARDWARE_RETENTION_DAYS)
        ).isoformat().replace("+00:00", "Z")
        import sqlite3
        import paths

        with sqlite3.connect(paths.HARDWARE_DB) as conn:
            repository.prune_before(conn, cutoff)


def list_device_names() -> list[str]:
    """Distinct device ids that have rows, plus local default if missing."""
    _ensure_db()
    return repository.list_device_names(get_local_device_name())


def reassign_device_metrics(source_device: str, target_device: str) -> int:
    """Move all rows from ``source_device`` to ``target_device``."""
    src = normalize_device_name(source_device)
    dst = normalize_device_name(target_device)
    if not src or not dst:
        raise ValueError("invalid device name")
    if src == dst:
        return 0
    _ensure_db()
    return repository.reassign_device_metrics(src, dst)


_SIMPLIFY_KEYS = (
    "cpu_load",
    "cpu_clock",
    "cpu_temp",
    "ram_percent",
    "swap_percent",
    "gpu_util",
    "gpu_mem_percent",
    "gpu_temp",
    "gpu_clock",
    "pcie_tx_mbps",
    "pcie_rx_mbps",
)


def _simplify_rows_minmax(rows: list[dict], target_points: int) -> list[dict]:
    """Min/max bucket simplification that preserves spikes and endpoints."""
    if target_points <= 0 or len(rows) <= target_points:
        return rows
    if target_points <= 2:
        return [rows[0], rows[-1]] if len(rows) > 1 else rows

    bucket_count = max(1, (target_points - 2) // 2)
    interior = rows[1:-1]
    if not interior:
        return [rows[0], rows[-1]]

    bucket_size = max(1, math.ceil(len(interior) / bucket_count))
    keep_indices: set[int] = {0, len(rows) - 1}

    for start in range(0, len(interior), bucket_size):
        end = min(start + bucket_size, len(interior))
        offset = start + 1
        bucket = interior[start:end]
        if not bucket:
            continue
        if len(bucket) == 1:
            keep_indices.add(offset)
            continue

        scored: list[tuple[int, float]] = []
        for i, row in enumerate(bucket):
            vals: list[float] = []
            for key in _SIMPLIFY_KEYS:
                v = row.get(key)
                if v is None:
                    continue
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
            if vals:
                scored.append((offset + i, max(vals) - min(vals)))
            else:
                scored.append((offset + i, 0.0))
        scored.sort(key=lambda item: item[1], reverse=True)
        keep_indices.add(scored[0][0])
        if len(scored) > 1:
            keep_indices.add(scored[1][0])

    out = [rows[i] for i in sorted(keep_indices)]
    if len(out) <= target_points:
        return out
    stride = max(1, math.ceil(len(out) / target_points))
    compact = [out[i] for i in range(0, len(out), stride)]
    if compact[-1] != out[-1]:
        compact.append(out[-1])
    return compact[-target_points:]


def get_metrics_history(
    minutes: int = 60,
    *,
    end_iso: str | None = None,
    simplify_points: int | None = None,
    device: str | None = None,
) -> list[dict]:
    _ensure_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    end_dt = _parse_iso_utc(end_iso) or datetime.now(timezone.utc)
    cutoff_dt = end_dt - timedelta(minutes=minutes)
    end_s = end_dt.isoformat().replace("+00:00", "Z")
    cutoff_s = cutoff_dt.isoformat().replace("+00:00", "Z")
    rows = repository.get_rows_between(dev, cutoff_s, end_s)
    if simplify_points is None or simplify_points <= 0:
        return rows
    return _simplify_rows_minmax(rows, simplify_points)


def get_latest_metric(*, device: str | None = None) -> dict | None:
    _ensure_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    return repository.get_latest_metric(dev)


def get_metrics_since(
    since_iso: str,
    *,
    simplify_points: int | None = None,
    device: str | None = None,
) -> list[dict]:
    _ensure_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    rows = repository.get_rows_since(dev, since_iso)
    if simplify_points is None or simplify_points <= 0:
        return rows
    return _simplify_rows_minmax(rows, simplify_points)
