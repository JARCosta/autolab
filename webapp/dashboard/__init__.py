"""Dashboard Blueprint: web UI for on-demand data (e.g. balance table at /)."""
import config
from flask import Blueprint, jsonify, render_template

from webapp.balance_data import (
    fetch_and_cache_balances,
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
    rows = fetch_and_cache_balances()
    payload = [
        {"channel": channel, "cells": [{"bettor": b, "balance": bal} for b, bal in cells]}
        for channel, cells in rows
    ]
    return jsonify({"rows": payload})
