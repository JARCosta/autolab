"""Continente module: product votes and price-drop alert controls."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from app.backend.continente_tracker import run_once
from app.infrastructure.storage.continente_db import list_products, set_notify, vote
from logging_config import setup_logging

log = setup_logging("webapp.continente")

continente_bp = Blueprint(
    "continente",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/continente",
)


@continente_bp.route("/continente")
def continente_page():
    return render_template("continente.html", products=list_products())


@continente_bp.route("/api/continente/products")
def api_products():
    return jsonify({"products": list_products()})


@continente_bp.route("/api/continente/vote", methods=["POST"])
def api_vote():
    data = request.get_json(silent=True) or {}
    try:
        product_id = int(data.get("product_id", 0))
        delta = int(data.get("delta", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid product_id or delta"}), 400
    if product_id <= 0 or delta not in (-1, 1):
        return jsonify({"error": "invalid product_id or delta"}), 400
    ok = vote(product_id, delta)
    if not ok:
        return jsonify({"error": "unknown product"}), 404
    return jsonify({"ok": True})


@continente_bp.route("/api/continente/notify", methods=["POST"])
def api_notify():
    data = request.get_json(silent=True) or {}
    try:
        product_id = int(data.get("product_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid product_id"}), 400
    enabled = bool(data.get("enabled", True))
    if product_id <= 0:
        return jsonify({"error": "invalid product_id"}), 400
    ok = set_notify(product_id, enabled)
    if not ok:
        return jsonify({"error": "unknown product"}), 404
    return jsonify({"ok": True})


@continente_bp.route("/api/continente/sync", methods=["POST"])
def api_sync():
    try:
        result = run_once()
        return jsonify({"ok": True, **result})
    except Exception:
        log.exception("Continente sync failed from dashboard")
        return jsonify({"ok": False, "error": "sync failed — see server logs"}), 500
