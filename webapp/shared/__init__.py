"""Site-wide static assets and the canonical module page template."""

from flask import Blueprint

shared_bp = Blueprint(
    "shared",
    __name__,
    static_folder="static",
    static_url_path="/static/shared",
)
