"""Tailscale Blueprint: module dashboard + persisted config."""

from flask import Blueprint

tailscale_bp = Blueprint(
    "tailscale",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/tailscale",
)

# Register routes on import.
from . import routes as _routes  # noqa: F401
