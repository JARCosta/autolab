"""
System Blueprint: per-module on/off toggles.

The home page persists toggles to ``data/modules.json``; the host must run
``autolab restart`` (or ``scripts/start.sh``) to apply compose profile changes.
Restart cannot be triggered from inside ``autolab-web`` (no host systemd /
Docker socket in the default image).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.runtime.modules import (
    MODULES,
    load_state,
    save_state,
)
from logging_config import setup_logging

log = setup_logging("system")

system_bp = Blueprint("system", __name__)


@system_bp.route("/api/modules", methods=["GET"])
def api_modules():
    """Current on/off state for every registered module."""
    state = load_state()
    return jsonify({
        "modules": [
            {
                "name": m.name,
                "label": m.label,
                "enabled": state.get(m.name, m.default_enabled),
                "container": m.container,
            }
            for m in MODULES
        ]
    })


@system_bp.route("/api/modules", methods=["POST"])
def api_save_modules():
    """Persist all module flags at once (takes effect after restart)."""
    payload = request.get_json(silent=True) or {}
    raw_state = payload.get("state")
    if not isinstance(raw_state, dict):
        return jsonify({"error": "missing 'state' object"}), 400

    known = {m.name for m in MODULES}
    unknown = sorted(name for name in raw_state if name not in known)
    if unknown:
        return jsonify({"error": f"unknown module(s): {', '.join(unknown)}"}), 400

    current = load_state()
    merged = {
        m.name: bool(current.get(m.name, m.default_enabled))
        for m in MODULES
    }
    for name, enabled in raw_state.items():
        merged[name] = bool(enabled)

    save_state(merged)
    log.info("Saved modules state in one batch (restart required): %s", merged)
    return jsonify({"ok": True, "state": merged})
