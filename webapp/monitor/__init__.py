"""Hardware Monitor Blueprint: CPU load, clock, and temperature dashboard.

Supports two node modes:
- **Push**: nodes POST batches to ``/api/monitor/push``; each success response
  includes ``pong`` (viewer active), same semantics as ``/api/monitor/ping``.
- **Pull / ping-pong**: nodes register once, then the server triggers sampling
  on demand. While viewing, the node streams batches; keep-alive uses ``pong``
  embedded in push responses, with ``/api/monitor/ping`` as a fallback when
  there is nothing to push.
"""

import os
import time

import requests as req_lib
from flask import Blueprint, jsonify, render_template, request

from logging_config import setup_logging
from storage.hardware import (
    HARDWARE_PUSH_BATCH_MAX,
    get_latest_metric,
    get_local_device_name,
    get_metrics_history,
    list_device_names,
    normalize_device_name,
    reassign_device_metrics,
    store_metrics,
    store_metrics_batch,
)

log = setup_logging("monitor")

monitor_bp = Blueprint(
    "monitor",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/monitor",
)

# ---------------------------------------------------------------------------
# In-memory state for the pull / ping-pong protocol
# ---------------------------------------------------------------------------

_registered_nodes: dict[str, dict] = {}
_viewer_activity: dict[str, float] = {}

VIEWER_ACTIVE_TIMEOUT = 10  # seconds (monotonic)


def _update_viewer_activity(device: str) -> None:
    if device:
        _viewer_activity[device] = time.monotonic()


def _is_viewer_active(device: str) -> bool:
    last = _viewer_activity.get(device)
    if last is None:
        return False
    return (time.monotonic() - last) < VIEWER_ACTIVE_TIMEOUT


def _resolve_device(raw: str) -> str:
    dev = normalize_device_name(raw) if raw else ""
    return dev or get_local_device_name()


# ---------------------------------------------------------------------------
# Node URL lookup helpers
# ---------------------------------------------------------------------------

NODE_FETCH_PATH = "/api/node/hardware/fetch"


def _static_node_url_map() -> dict[str, str]:
    """Parse ``HARDWARE_PULL_NODES`` (or legacy ``HARDWARE_PULL_CLIENTS``)."""
    raw = os.getenv("HARDWARE_PULL_NODES", "").strip() or os.getenv(
        "HARDWARE_PULL_CLIENTS", ""
    ).strip()
    out: dict[str, str] = {}
    if not raw:
        return out
    for entry in raw.split(","):
        item = entry.strip()
        if not item or "=" not in item:
            continue
        dev_raw, url_raw = item.split("=", 1)
        dev = normalize_device_name(dev_raw.strip())
        url = url_raw.strip().rstrip("/")
        if dev and (url.startswith("http://") or url.startswith("https://")):
            out[dev] = url
    return out


def _pull_node_map() -> dict[str, str]:
    """Merge static env map with runtime registrations (runtime wins)."""
    out = _static_node_url_map()
    for dev, info in _registered_nodes.items():
        out[dev] = info["url"]
    return out


def _hardware_secret() -> str:
    return os.getenv("HARDWARE_TOKEN", "").strip()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@monitor_bp.route("/monitor")
def monitor():
    return render_template("monitor.html")


@monitor_bp.route("/api/monitor/devices")
def monitor_devices():
    devices = list_device_names()
    return jsonify({"devices": devices})


@monitor_bp.route("/api/monitor/history")
def monitor_history():
    device = request.args.get("device") or ""
    _update_viewer_activity(_resolve_device(device))

    minutes = request.args.get("minutes", 60, type=int)
    minutes = min(minutes, 10080)
    max_points = request.args.get("max_points", 4000, type=int)
    max_points = min(max(max_points, 100), 20_000)
    metrics = get_metrics_history(minutes, max_points=max_points, device=device)
    latest = get_latest_metric(device=device)
    devices = list_device_names()
    return jsonify({"metrics": metrics, "latest": latest, "devices": devices})


@monitor_bp.route("/api/monitor/latest")
def monitor_latest():
    device = request.args.get("device") or ""
    _update_viewer_activity(_resolve_device(device))

    metric = get_latest_metric(device=device)
    return jsonify({"metric": metric})


# ---------------------------------------------------------------------------
# Pull / ping-pong endpoints
# ---------------------------------------------------------------------------


@monitor_bp.route("/api/monitor/register", methods=["POST"])
def monitor_register():
    """Node announces itself so the server knows how to reach it."""
    secret = _hardware_secret()
    if not secret:
        return jsonify({"error": "hardware auth disabled (set HARDWARE_TOKEN)"}), 503

    data = request.get_json(silent=True) or {}
    if data.get("token") != secret:
        return jsonify({"error": "unauthorized"}), 401

    dev = normalize_device_name(str(data.get("device", "")))
    if not dev:
        return jsonify({"error": "invalid or missing device"}), 400

    node_url = str(data.get("node_url") or data.get("client_url", "")).strip().rstrip(
        "/"
    )
    if not node_url:
        return jsonify({"error": "missing node_url"}), 400

    raw_samples = data.get("samples")
    inserted = 0
    if isinstance(raw_samples, list) and raw_samples:
        if len(raw_samples) > HARDWARE_PUSH_BATCH_MAX:
            return jsonify({"error": "too many register samples"}), 400
        cleaned: list[dict] = []
        for item in raw_samples:
            if not isinstance(item, dict):
                return jsonify({"error": "invalid register sample entry"}), 400
            cleaned.append(item)
        store_metrics_batch(cleaned, device=dev)
        inserted = len(cleaned)

    _registered_nodes[dev] = {"url": node_url, "registered_at": time.time()}
    log.info("[REGISTRY] device=%s url=%s inserted=%d", dev, node_url, inserted)
    return jsonify({"ok": True, "device": dev, "inserted": inserted})


@monitor_bp.route("/api/monitor/ping", methods=["POST"])
def monitor_ping():
    """Node asks whether a viewer is still watching; respond with pong."""
    secret = _hardware_secret()
    data = request.get_json(silent=True) or {}
    if not secret or data.get("token") != secret:
        return jsonify({"pong": False}), 200

    dev = normalize_device_name(str(data.get("device", "")))
    if not dev:
        return jsonify({"pong": False}), 200

    pong = _is_viewer_active(dev)
    log.info("[PING] device=%s pong=%s", dev, "yes" if pong else "no")
    return jsonify({"pong": pong})


@monitor_bp.route("/api/monitor/fetch", methods=["POST"])
def monitor_fetch_now():
    """Ask a node to flush its buffer and begin streaming."""
    data = request.get_json(silent=True) or {}
    dev = normalize_device_name(str(data.get("device", "")))
    if not dev:
        return jsonify({"error": "invalid or missing device"}), 400

    _update_viewer_activity(dev)

    nodes = _pull_node_map()
    node_url = nodes.get(dev)
    if not node_url:
        return jsonify({"error": f"device '{dev}' is not registered or configured"}), 400

    secret = _hardware_secret()
    if not secret:
        return jsonify({"error": "hardware auth disabled (set HARDWARE_TOKEN)"}), 503

    endpoint = f"{node_url}{NODE_FETCH_PATH}"
    log.info("[FETCH] requesting device=%s endpoint=%s", dev, endpoint)
    try:
        r = req_lib.post(
            endpoint,
            json={"token": secret},
            timeout=120,
        )
    except req_lib.RequestException as exc:
        return jsonify({"error": f"node request failed: {exc}"}), 502

    try:
        body = r.json()
    except ValueError:
        body = {"raw": (r.text or "")[:300]}

    if r.status_code >= 400:
        return jsonify({
            "error": "node rejected request",
            "node_status": r.status_code,
            "node_response": body,
        }), 502

    latest = get_latest_metric(device=dev)
    inserted = body.get("inserted") if isinstance(body, dict) else None
    log.info("[FETCH] device=%s accepted inserted=%s", dev, inserted)
    return jsonify({"ok": True, "node": body, "latest": latest, "device": dev})


# ---------------------------------------------------------------------------
# Push ingest (unchanged, used by both legacy push loop and streaming mode)
# ---------------------------------------------------------------------------


@monitor_bp.route("/api/monitor/push", methods=["POST"])
def monitor_push():
    """Ingest metrics from a remote machine. Requires ``HARDWARE_TOKEN`` on the server."""
    secret = _hardware_secret()
    if not secret:
        return jsonify({"error": "hardware auth disabled (set HARDWARE_TOKEN)"}), 503

    data = request.get_json(silent=True) or {}
    if data.get("token") != secret:
        return jsonify({"error": "unauthorized"}), 401

    dev = normalize_device_name(str(data.get("device", "")))
    if not dev:
        return jsonify({"error": "invalid or missing device"}), 400

    def _f(key: str):
        v = data.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _vendor(key: str):
        v = data.get(key)
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        s = v.strip().lower()
        if s not in ("intel", "amd", "nvidia", "unknown"):
            return None
        return s

    raw_samples = data.get("samples")
    if isinstance(raw_samples, list):
        if not raw_samples:
            return jsonify({"error": "empty samples"}), 400
        if len(raw_samples) > HARDWARE_PUSH_BATCH_MAX:
            return jsonify({"error": "too many samples"}), 400
        cleaned: list[dict] = []
        for item in raw_samples:
            if not isinstance(item, dict):
                return jsonify({"error": "invalid sample entry"}), 400
            cleaned.append(item)
        store_metrics_batch(cleaned, device=dev)
        pong = _is_viewer_active(dev)
        return jsonify({"ok": True, "inserted": len(cleaned), "pong": pong})

    store_metrics(
        _f("cpu_load"),
        _f("cpu_clock"),
        _f("cpu_temp"),
        device=dev,
        ram_percent=_f("ram_percent"),
        swap_percent=_f("swap_percent"),
        gpu_util=_f("gpu_util"),
        gpu_mem_percent=_f("gpu_mem_percent"),
        gpu_temp=_f("gpu_temp"),
        gpu_clock=_f("gpu_clock"),
        pcie_tx_mbps=_f("pcie_tx_mbps"),
        pcie_rx_mbps=_f("pcie_rx_mbps"),
        cpu_vendor=_vendor("cpu_vendor"),
        gpu_vendor=_vendor("gpu_vendor"),
    )
    pong = _is_viewer_active(dev)
    log.info("[PUSH] device=%s samples=1 pong=%s", dev, "yes" if pong else "no")
    return jsonify({"ok": True, "pong": pong})


# ---------------------------------------------------------------------------
# Device reassign
# ---------------------------------------------------------------------------


@monitor_bp.route("/api/monitor/device/reassign", methods=["POST"])
def monitor_reassign_device():
    """Move all samples from one device id into another."""
    data = request.get_json(silent=True) or {}
    source = normalize_device_name(str(data.get("source", "")))
    target = normalize_device_name(str(data.get("target", "")))

    if not source or not target:
        return jsonify({"error": "invalid or missing source/target"}), 400
    if source == target:
        return jsonify({"error": "source and target must be different"}), 400

    moved = reassign_device_metrics(source, target)
    latest = get_latest_metric(device=target)
    devices = list_device_names()
    return jsonify(
        {
            "ok": True,
            "moved": moved,
            "source": source,
            "target": target,
            "latest": latest,
            "devices": devices,
        }
    )
