"""Dashboard Blueprint: home page and balance table UI."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template, request

import config
from storage.balances import (
    fetch_and_cache_balances,
    get_balance_history,
    get_balance_rows_from_cache,
)

dashboard_bp = Blueprint("dashboard", __name__, template_folder="templates")


@dashboard_bp.route("/")
def home():
    return render_template("home.html")


@dashboard_bp.route("/balances")
def balances():
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
    """Return time series for a single (channel, bettor).

    Query params:
      days — if set (positive int), only points from the last N calendar days (UTC).
      last_n — optional cap on the number of most recent points (after the days filter).
    """
    channel = request.args.get("channel")
    bettor = request.args.get("bettor")
    if not channel or not bettor:
        return jsonify({"error": "channel and bettor are required"}), 400

    since_iso = None
    days = request.args.get("days", type=int)
    if days is not None and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        since_iso = cutoff.isoformat().replace("+00:00", "Z")

    last_n = request.args.get("last_n", type=int)
    if last_n is not None and last_n < 1:
        last_n = None
    if last_n is not None:
        last_n = min(last_n, 500_000)

    history = get_balance_history(channel, bettor, since_iso=since_iso, last_n=last_n)
    return jsonify({"channel": channel, "bettor": bettor, "points": history})
