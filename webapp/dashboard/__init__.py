"""Dashboard Blueprint: web UI for on-demand data (e.g. balance table at /)."""
from flask import Blueprint, jsonify, render_template, request

import config
from storage.balances import (
    fetch_and_cache_balances,
    get_balance_history,
    get_balance_rows_from_cache,
)

dashboard_bp = Blueprint("dashboard", __name__, template_folder="templates")


@dashboard_bp.route("/")
def index():
    rows = get_balance_rows_from_cache()
    bettors = (
        [b for b, _ in rows[0][1]]
        if rows
        else list(config.BETTORS.keys())
    )
    return render_template("index.html", rows=rows, bettors=bettors)


@dashboard_bp.route("/api/balances")
def api_balances():
    """Fetch live balances, update cache, return JSON for in-page update."""
    # The dashboard doesn't need to poll StreamElements if we already have
    # very fresh values.
    rows = fetch_and_cache_balances(min_age_seconds=5 * 60)
    payload = [
        {"channel": channel, "cells": [{"bettor": b, "balance": bal} for b, bal in cells]}
        for channel, cells in rows
    ]
    return jsonify({"rows": payload})


@dashboard_bp.route("/api/balance_history")
def api_balance_history():
    """Return time series for a single (channel, bettor)."""
    channel = request.args.get("channel")
    bettor = request.args.get("bettor")
    if not channel or not bettor:
        return jsonify({"error": "channel and bettor are required"}), 400
    history = get_balance_history(channel, bettor)
    return jsonify({"channel": channel, "bettor": bettor, "points": history})
