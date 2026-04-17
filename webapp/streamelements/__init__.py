"""StreamElements blueprint package."""

from flask import Blueprint

streamelements_bp = Blueprint(
    "streamelements",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/streamelements",
)

# Register routes on import.
from . import routes as _routes  # noqa: F401
