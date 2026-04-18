"""Service layer for hardware ingestion/query logic."""

from __future__ import annotations

import math
import os
import re
import socket
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from . import repository

_DEVICE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

# Drop hardware rows older than this to cap DB size (~2.6M rows/month at 1 Hz per device).
HARDWARE_RETENTION_DAYS = 7

# Prune old rows every N inserts (at 1 Hz, 600 ~= every 10 minutes).
_PRUNE_EVERY_N_INSERTS = 600

_insert_count = 0

_ALLOWED_VENDORS = frozenset({"intel", "amd", "nvidia", "unknown"})

# Older history is compacted by selecting representative points that preserve
# shape and spikes. Recent data stays at full resolution.
_ADAPTIVE_RECENT_SECONDS = 60 * 60  # 1 hour
_ADAPTIVE_EST_POINTS_PER_BUCKET = 10  # first+last+min/max over key metrics
_ADAPTIVE_SPIKE_KEYS = (
    "cpu_load",
    "cpu_temp",
    "gpu_util",
    "gpu_temp",
)

_SERVER_DOWNSAMPLE_MULTIPLIER = 6

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


def _parse_iso_to_epoch_seconds(raw: str | None) -> float | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


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
        rows_values.append(
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


def _thin_with_stride(rows: list[dict], max_points: int) -> list[dict]:
    """Uniform fallback thinning; keeps the final point."""
    if len(rows) <= max_points or max_points <= 0:
        return rows
    stride = max(1, math.ceil(len(rows) / max_points))
    out = [rows[i] for i in range(0, len(rows), stride)]
    if out and rows[-1]["timestamp"] != out[-1]["timestamp"]:
        out.append(rows[-1])
    if len(out) > max_points:
        out = out[-max_points:]
    return out


def _bucket_representatives(bucket_rows: list[dict]) -> list[dict]:
    """Keep first/last plus local min/max on selected spike-sensitive metrics."""
    if not bucket_rows:
        return []
    if len(bucket_rows) <= 2:
        return bucket_rows

    keep_idx: set[int] = {0, len(bucket_rows) - 1}
    for key in _ADAPTIVE_SPIKE_KEYS:
        min_idx: int | None = None
        max_idx: int | None = None
        min_val: float | None = None
        max_val: float | None = None
        for i, row in enumerate(bucket_rows):
            v = row.get(key)
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if min_val is None or fv < min_val:
                min_val = fv
                min_idx = i
            if max_val is None or fv > max_val:
                max_val = fv
                max_idx = i
        if min_idx is not None:
            keep_idx.add(min_idx)
        if max_idx is not None:
            keep_idx.add(max_idx)
    return [bucket_rows[i] for i in sorted(keep_idx)]


def _adaptive_downsample_history(rows: list[dict], *, max_points: int) -> list[dict]:
    if len(rows) <= max_points or max_points <= 0:
        return rows

    now_s = datetime.now(timezone.utc).timestamp()
    recent_cutoff_s = now_s - _ADAPTIVE_RECENT_SECONDS

    recent_rows: list[dict] = []
    old_rows: list[dict] = []
    for row in rows:
        ts_s = _parse_iso_to_epoch_seconds(row.get("timestamp"))
        if ts_s is None:
            recent_rows.append(row)
        elif ts_s >= recent_cutoff_s:
            recent_rows.append(row)
        else:
            old_rows.append(row)

    if len(recent_rows) >= max_points:
        return _thin_with_stride(recent_rows, max_points)
    if not old_rows:
        return recent_rows

    budget_old = max_points - len(recent_rows)
    if budget_old <= 0:
        return recent_rows

    first_old_ts = _parse_iso_to_epoch_seconds(old_rows[0].get("timestamp"))
    if first_old_ts is None:
        return _thin_with_stride(old_rows + recent_rows, max_points)
    old_span_seconds = max(1, int(recent_cutoff_s - first_old_ts))
    target_bucket_count = max(1, budget_old // _ADAPTIVE_EST_POINTS_PER_BUCKET)
    bucket_seconds = max(1, math.ceil(old_span_seconds / target_bucket_count))

    buckets: dict[int, list[dict]] = defaultdict(list)
    for row in old_rows:
        ts_s = _parse_iso_to_epoch_seconds(row.get("timestamp"))
        if ts_s is None:
            continue
        bucket_id = int(ts_s // bucket_seconds)
        buckets[bucket_id].append(row)

    compact_old: list[dict] = []
    for bucket_id in sorted(buckets.keys()):
        compact_old.extend(_bucket_representatives(buckets[bucket_id]))

    compact_old = _thin_with_stride(compact_old, budget_old)
    merged = compact_old + recent_rows
    merged.sort(key=lambda r: r.get("timestamp") or "")
    return _thin_with_stride(merged, max_points)


def get_metrics_history(
    minutes: int = 60,
    max_points: int = 4000,
    *,
    device: str | None = None,
) -> list[dict]:
    _ensure_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    cutoff = (
        (datetime.now(timezone.utc) - timedelta(minutes=minutes))
        .isoformat()
        .replace("+00:00", "Z")
    )
    # Avoid loading massive 7d rowsets into Python: pre-thin in SQL when row count is far
    # above the response budget, then run adaptive spike-preserving compaction.
    total_rows = repository.count_rows_since_cutoff(dev, cutoff)
    if total_rows > (max_points * _SERVER_DOWNSAMPLE_MULTIPLIER):
        stride = max(2, math.ceil(total_rows / (max_points * 2)))
        try:
            rows = repository.get_rows_since_cutoff_strided(dev, cutoff, stride)
        except sqlite3.OperationalError:
            rows = repository.get_rows_since_cutoff(dev, cutoff)
    else:
        rows = repository.get_rows_since_cutoff(dev, cutoff)
    if len(rows) <= max_points or len(rows) <= 1:
        return rows
    return _adaptive_downsample_history(rows, max_points=max_points)


def get_latest_metric(*, device: str | None = None) -> dict | None:
    _ensure_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    return repository.get_latest_metric(dev)


def get_metrics_since(
    since_iso: str,
    *,
    max_points: int = 5000,
    device: str | None = None,
) -> list[dict]:
    _ensure_db()
    dev = normalize_device_name(device) if device else ""
    if not dev:
        dev = get_local_device_name()
    cap = min(max(max_points, 1), 20_000)
    return repository.get_rows_since(dev, since_iso, cap)
