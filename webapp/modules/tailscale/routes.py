"""Tailscale dashboard routes."""

from __future__ import annotations

from flask import jsonify, render_template, request

from app.infrastructure.storage.tailscale_state import (
    build_extra_args,
    load_settings,
    save_settings,
)
from app.runtime.modules import is_enabled
from webapp.modules.tailscale import tailscale_bp


def _public_payload(settings: dict) -> dict:
    payload = dict(settings)
    payload["auth_key_configured"] = bool(payload.get("auth_key"))
    payload["auth_key"] = ""
    payload["ts_extra_args_preview"] = build_extra_args(settings)
    payload["module_enabled"] = is_enabled("tailscale")
    return payload


@tailscale_bp.route("/tailscale")
def tailscale_dashboard():
    settings = load_settings()
    return render_template("tailscale.html", settings=_public_payload(settings))


@tailscale_bp.route("/api/tailscale/settings", methods=["GET"])
def api_tailscale_settings_get():
    return jsonify({"settings": _public_payload(load_settings())})


@tailscale_bp.route("/api/tailscale/settings", methods=["POST"])
def api_tailscale_settings_post():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object required"}), 400

    raw = payload.get("settings")
    if not isinstance(raw, dict):
        return jsonify({"error": "missing settings object"}), 400

    allowed = {
        "auth_key",
        "hostname",
        "advertise_routes",
        "advertise_exit_node",
        "accept_routes",
        "accept_dns",
        "enable_ssh",
        "extra_args",
        "userspace",
    }
    unknown = sorted(k for k in raw if k not in allowed)
    if unknown:
        return jsonify({"error": f"unknown setting(s): {', '.join(unknown)}"}), 400

    try:
        saved = save_settings(raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "settings": _public_payload(saved)})
