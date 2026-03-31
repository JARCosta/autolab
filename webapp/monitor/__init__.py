"""Hardware Monitor Blueprint: CPU load, clock, and temperature dashboard."""

import os

from flask import Blueprint, jsonify, render_template, request

from storage.hardware import (
    HARDWARE_PUSH_BATCH_MAX,
    get_latest_metric,
    get_metrics_history,
    list_device_names,
    normalize_device_name,
    store_metrics,
    store_metrics_batch,
)

monitor_bp = Blueprint(
    "monitor",
    __name__,
    template_folder="templates",
    static_folder="static",
)


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
    metric = get_latest_metric(device=device)
    return jsonify({"metric": metric})


@monitor_bp.route("/api/monitor/push", methods=["POST"])
def monitor_push():
    """Ingest metrics from a remote machine. Requires ``HARDWARE_PUSH_TOKEN`` on the server."""
    secret = os.getenv("HARDWARE_PUSH_TOKEN", "").strip()
    if not secret:
        return jsonify({"error": "push disabled (set HARDWARE_PUSH_TOKEN)"}), 503

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
        return jsonify({"ok": True, "inserted": len(cleaned)})

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
    return jsonify({"ok": True})
