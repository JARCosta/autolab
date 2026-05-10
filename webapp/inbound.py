"""Dedicated inbound HTTP service (Telegram webhook endpoint only)."""

from __future__ import annotations

import os

from flask import Flask, jsonify, request

from app.runtime.telegram_ingress import configure_telegram_webhook
from logging_config import setup_logging
from webapp.telegram.webhook import process_update

log = setup_logging("inbound_web")


def create_inbound_app() -> Flask:
    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.post("/webhook")
    def webhook():
        process_update(request.get_json(silent=True))
        return "", 200

    return app


def launch() -> None:
    port = int(os.getenv("INBOUND_PORT", os.getenv("WEBAPP_PORT", "5000")))
    host = os.getenv("INBOUND_HOST", "0.0.0.0").strip() or "0.0.0.0"
    configure_telegram_webhook(port)
    log.info("Starting inbound webhook service on %s:%s", host, port)
    create_inbound_app().run(host=host, port=port, debug=False, use_reloader=False)
