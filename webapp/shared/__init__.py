"""Site-wide static assets (base theme, shared components)."""

from flask import Blueprint

shared_bp = Blueprint(
    "shared",
    __name__,
    static_folder="static",
    static_url_path="/static/shared",
)
