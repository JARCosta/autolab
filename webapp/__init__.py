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
import os

from flask import Flask
from pyngrok import ngrok

from logging_config import setup_logging

log = setup_logging("webapp")

def create_app():
    app = Flask(__name__)

    from webapp.dashboard import dashboard_bp
    from webapp.telegram import telegram_bp

    app.register_blueprint(dashboard_bp, url_prefix="/")
    app.register_blueprint(telegram_bp)

    return app


def start_ngrok(port: int):
    auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if auth_token:
        ngrok.set_auth_token(auth_token)
    tunnel = ngrok.connect(port, "http")
    log.info("ngrok tunnel URL: %s", tunnel.public_url)
    return tunnel


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

    webhook_url = f"{tunnel.public_url}/webhook"
    requests.post(
        f"https://api.telegram.org/bot{notification_token}/setWebhook",
        data={"url": webhook_url},
    )

    app.run(port=port, debug=False, use_reloader=False)
