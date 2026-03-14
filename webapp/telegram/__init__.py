from flask import Blueprint

telegram_bp = Blueprint("telegram", __name__)

from webapp.telegram import webhook  # noqa: E402, F401
