"""StreamElements Blueprint routes: balances page and related APIs."""

from datetime import datetime, timedelta, timezone

from flask import jsonify, redirect, render_template, request, url_for

from app.infrastructure.storage.balances_db import (
    fetch_and_store_balances,
    get_balance_history_all_pairs,
    get_balance_rows_from_cache,
)
from app.infrastructure.storage.balances_db import channels_data
from app.infrastructure.storage.balances_db.repository import init_db
from webapp.modules.streamelements import streamelements_bp


@streamelements_bp.route("/balances")
def balances():
    rows = get_balance_rows_from_cache()
    bettors = [b for b, _ in rows[0][1]] if rows else channels_data.list_account_ids_ordered()
    return render_template("streamelements.html", rows=rows, bettors=bettors)


@streamelements_bp.route("/api/betting_channels")
def api_betting_channels_get():
    """Return active channel memberships (viewers) and account list."""
    init_db()
    return jsonify(channels_data.betting_channels_api())


@streamelements_bp.route("/api/betting_channels", methods=["POST"])
def api_betting_channels_post():
    """Update active channel memberships; StreamElements IDs stay in the DB."""
    body = request.get_json(silent=True) or {}
    data = body.get("channels")
    if not isinstance(data, dict):
        return jsonify({"error": "channels object required"}), 400
    init_db()
    try:
        channels_data.merge_ui_channel_memberships(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    payload = channels_data.betting_channels_api()
    payload["ok"] = True
    return jsonify(payload)


def _api_channels_snapshot_get():
    """Export ``accounts`` + ``channels`` JSON (backup / round-trip)."""
    init_db()
    return jsonify(channels_data.export_channels_snapshot())


def _api_channels_snapshot_post():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON object required"}), 400
    init_db()
    try:
        channels_data.import_channels_snapshot(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@streamelements_bp.route("/api/channels_snapshot")
def api_channels_snapshot_get():
    return _api_channels_snapshot_get()


@streamelements_bp.route("/api/channels_snapshot", methods=["POST"])
def api_channels_snapshot_post():
    return _api_channels_snapshot_post()


@streamelements_bp.route("/api/accounts", methods=["POST"])
def api_accounts_post():
    """Add one Twitch account (stored as lowercase ``account_id``)."""
    body = request.get_json(silent=True) or {}
    raw = body.get("account_id") or body.get("id")
    if not raw or not isinstance(raw, str):
        return jsonify({"error": "account_id required"}), 400
    init_db()
    try:
        channels_data.add_account(raw)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@streamelements_bp.route("/api/bettors", methods=["POST"])
def api_bettors_post():
    """Deprecated alias for ``POST /api/accounts``."""
    return api_accounts_post()


@streamelements_bp.route("/api/channel_meta", methods=["POST"])
def api_channel_meta_post():
    """Create or overwrite ``channels`` row (StreamElements + optional Steam/Faceit). Viewers unchanged."""
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()
    sid = str(body.get("streamelements_id") or body.get("StreamElementsId") or "").strip()
    if not name or not sid:
        return jsonify({"error": "name and streamelements_id required"}), 400
    init_db()
    try:
        channels_data.upsert_channel_definition(
            name,
            sid,
            steam_id=body.get("steam_id") or body.get("SteamId"),
            faceit_id=body.get("faceit_id") or body.get("FaceitId"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    meta = channels_data.get_channel_meta(name.lower())
    return jsonify({"ok": True, "channel_def": meta})


@streamelements_bp.route("/api/channels", methods=["POST"])
def api_channels_post():
    """Add one channel row; optional Bettors map for IRC (who connects / who bets)."""
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    sid = body.get("streamelements_id") or body.get("StreamElementsId")
    if not name or not sid:
        return jsonify({"error": "name and streamelements_id required"}), 400
    bmap = body.get("Bettors") or body.get("bettors")
    if bmap is not None and not isinstance(bmap, dict):
        return jsonify({"error": "Bettors must be an object"}), 400
    init_db()
    try:
        channels_data.add_channel_with_viewers(
            str(name),
            str(sid),
            steam_id=body.get("steam_id") or body.get("SteamId"),
            faceit_id=body.get("faceit_id") or body.get("FaceitId"),
            viewers_map=bmap if isinstance(bmap, dict) else None,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@streamelements_bp.route("/api/balances")
def api_balances():
    """Fetch live balances, update cache, return JSON for in-page update."""
    # The StreamElements page doesn't need to poll StreamElements if we already
    # have very fresh values.
    rows = fetch_and_store_balances(min_age_seconds=5 * 60)
    payload = [
        {"channel": channel, "cells": [{"bettor": b, "balance": bal} for b, bal in cells]}
        for channel, cells in rows
    ]
    return jsonify({"rows": payload})


@streamelements_bp.route("/api/balance_history_batch")
def api_balance_history_batch():
    """Return time series for every configured (channel, bettor) in one response.

    Query params match ``/api/balance_history``: ``days``.
    Response shape: ``{ "series": { channel: { bettor: [ { balance, updated_at }, ... ] } } }``.
    """
    since_iso = None
    days = request.args.get("days", type=int)
    if days is not None and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        since_iso = cutoff.isoformat().replace("+00:00", "Z")
    series = get_balance_history_all_pairs(since_iso=since_iso)
    return jsonify({"series": series})
