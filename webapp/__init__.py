"""
Flask application factory with ngrok tunnel management.

The webapp is designed to be extensible -- each feature is a Flask Blueprint.
Currently registered blueprints:
  - dashboard: Web UI at / (e.g. balance table)
  - telegram: Telegram bot webhook and messaging helpers

To add a new module:
  1. Create webapp/<name>/__init__.py with a Blueprint
  2. Register it in create_app() below
"""
import logging
import os

from flask import Flask
from pyngrok import ngrok

from logging_config import setup_logging

log = setup_logging("webapp")

def create_app():
    app = Flask(__name__)

    from webapp.dashboard import dashboard_bp
    from webapp.monitor import monitor_bp
    from webapp.telegram import telegram_bp

    app.register_blueprint(dashboard_bp, url_prefix="/")
    app.register_blueprint(monitor_bp, url_prefix="/")
    app.register_blueprint(telegram_bp)

    return app


def start_ngrok(port: int):
    auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if auth_token:
        ngrok.set_auth_token(auth_token)
    api_key = os.getenv("NGROK_API_KEY")
    if api_key:
        ngrok.set_api_key(api_key)

    internal_domain = os.getenv("NGROK_INTERNAL_DOMAIN", "").strip()
    if internal_domain:
        # Cloud Endpoint + traffic policy forward-internal: agent must use the same
        # hostname as policy config.url (e.g. https://default.internal -> default.internal).
        tunnel = ngrok.connect(port, "http", domain=internal_domain)
        public = os.getenv("NGROK_PUBLIC_URL", "").strip().rstrip("/")
        log.info("ngrok internal endpoint: %s", tunnel.public_url)
        if public:
            log.info("ngrok public URL (cloud endpoint): %s", public)
        else:
            log.warning(
                "NGROK_PUBLIC_URL unset; Telegram webhook must use your cloud endpoint "
                "HTTPS URL, not the internal .internal address."
            )
    else:
        tunnel = ngrok.connect(port, "http")
        log.info("ngrok tunnel URL: %s", tunnel.public_url)
    return tunnel


def ngrok_webhook_base(tunnel) -> str:
    """HTTPS origin for webhooks (cloud endpoint URL when using forward-internal)."""
    public = os.getenv("NGROK_PUBLIC_URL", "").strip().rstrip("/")
    if public:
        return public
    return tunnel.public_url.rstrip("/")


def launch():
    """Entry point called by main.py to start the webapp process."""
    import json

    import requests

    from webapp.telegram.commands import commands

    port = 5000
    app = create_app()
    tunnel = start_ngrok(port)

    notification_token = os.getenv("TELEGRAM_NOTIFICATION_TOKEN")
    logs_token = os.getenv("TELEGRAM_LOGS_TOKEN")

    command_helper_url = f"https://api.telegram.org/bot{notification_token}/setMyCommands"
    command_helper = {"commands": json.dumps([commands[cmd]["helper"] for cmd in commands])}
    requests.post(command_helper_url, data=command_helper, timeout=10)

    command_helper_url = f"https://api.telegram.org/bot{logs_token}/setMyCommands"
    requests.post(command_helper_url, data={"commands": json.dumps([])})

    webhook_url = f"{ngrok_webhook_base(tunnel)}/webhook"
    log.info("Telegram webhook URL: %s", webhook_url)
    requests.post(
        f"https://api.telegram.org/bot{notification_token}/setWebhook",
        data={"url": webhook_url},
    )

    # Hide per-request access lines (GET/POST … 200) from Werkzeug; keep WARNING+.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    app.run(port=port, debug=False, use_reloader=False)
