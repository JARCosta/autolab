"""Discord bot dashboard: slash-command reference + shared leaderboard (read-only)."""

from flask import Blueprint, jsonify, redirect, render_template

from webapp.modules.discord_bot.stats import load_leaderboard_rows

discord_bot_bp = Blueprint(
    "discord_bot",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/discord_bot",
)


@discord_bot_bp.route("/boost")
def boost_redirect():
    """Old CS2 Custom UI was removed; keep links working."""
    return redirect("/discord", code=301)


@discord_bot_bp.route("/discord")
def discord_dashboard():
    return render_template("discord_dashboard.html")


@discord_bot_bp.route("/api/discord/leaderboard")
def api_leaderboard():
    return jsonify({"players": load_leaderboard_rows()})
