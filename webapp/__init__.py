"""
Flask application factory with optional ngrok tunnel management.

Blueprints:
  - shared: site-wide static (/static/shared/…)
  - home: landing page at /
  - modules.streamelements, modules.monitor, modules.discord_bot,
    modules.wallapop, modules.tailscale, modules.system: feature UIs + APIs

The ``monitor`` blueprint is registered conditionally on
``modules.json["monitor"]`` (the rest of the per-module toggles control
separate docker-compose services and don't gate webapp routes).

To add a feature UI:
  1. Add webapp/modules/<name>/ with a Blueprint
  2. Register it in create_app() below
"""
import logging
import os
import shutil

from flask import Flask
from pyngrok import conf, ngrok

from logging_config import setup_logging

log = setup_logging("webapp")

def create_app():
    app = Flask(__name__)
    asset_version = os.getenv("WEBAPP_ASSET_VERSION", "1")

    @app.context_processor
    def inject_asset_version():
        return {"asset_version": asset_version}

    from app.runtime.modules import is_enabled
    from webapp.home import home_bp
    from webapp.modules.discord_bot import discord_bot_bp
    from webapp.modules.streamelements import streamelements_bp
    from webapp.modules.system import system_bp
    from webapp.modules.tailscale import tailscale_bp
    from webapp.modules.wallapop import wallapop_bp
    from webapp.shared import shared_bp
    from webapp.telegram import telegram_bp

    app.register_blueprint(shared_bp, url_prefix="/")
    app.register_blueprint(home_bp, url_prefix="/")
    app.register_blueprint(streamelements_bp, url_prefix="/")
    app.register_blueprint(telegram_bp)
    app.register_blueprint(discord_bot_bp, url_prefix="/")
    app.register_blueprint(wallapop_bp, url_prefix="/")
    app.register_blueprint(tailscale_bp, url_prefix="/")
    app.register_blueprint(system_bp, url_prefix="/")

    if is_enabled("monitor"):
        from webapp.modules.monitor import monitor_bp
        app.register_blueprint(monitor_bp, url_prefix="/")
    else:
        log.info("Hardware Monitor disabled in modules.json; skipping blueprint.")

    return app


def start_ngrok(port: int):
    system_bin = shutil.which("ngrok")
    if system_bin:
        conf.get_default().ngrok_path = system_bin
        log.info("Using system ngrok binary at %s (no runtime download)", system_bin)

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

    port = int(os.getenv("WEBAPP_PORT", "5000"))
    host = os.getenv("WEBAPP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    explicit_webhook = os.getenv("TELEGRAM_WEBHOOK_PUBLIC_URL", "").strip()
    ngrok_enabled = os.getenv("WEBAPP_ENABLE_NGROK", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    app = create_app()
    tunnel = None
    if explicit_webhook:
        log.info(
            "TELEGRAM_WEBHOOK_PUBLIC_URL is set; skipping ngrok (use your own HTTPS ingress)."
        )
    elif ngrok_enabled:
        try:
            tunnel = start_ngrok(port)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Keep LAN API reachable even if ngrok fails.
            log.warning("ngrok unavailable; continuing without webhook tunnel: %s", e)
    else:
        log.info("WEBAPP_ENABLE_NGROK disabled; running without webhook tunnel.")

    notification_token = os.getenv("TELEGRAM_NOTIFICATION_TOKEN")
    logs_token = os.getenv("TELEGRAM_LOGS_TOKEN")

    command_helper_url = f"https://api.telegram.org/bot{notification_token}/setMyCommands"
    command_helper = {"commands": json.dumps([commands[cmd]["helper"] for cmd in commands])}
    requests.post(command_helper_url, data=command_helper, timeout=10)

    command_helper_url = f"https://api.telegram.org/bot{logs_token}/setMyCommands"
    requests.post(command_helper_url, data={"commands": json.dumps([])}, timeout=10)

    if explicit_webhook:
        webhook_url = explicit_webhook.rstrip("/")
    elif tunnel is not None:
        webhook_url = f"{ngrok_webhook_base(tunnel)}/webhook"
    else:
        webhook_url = None

    if webhook_url:
        log.info("Telegram webhook URL: %s", webhook_url)
        requests.post(
            f"https://api.telegram.org/bot{notification_token}/setWebhook",
            data={"url": webhook_url},
            timeout=10,
        )
    else:
        log.info(
            "Skipping Telegram webhook registration "
            "(set TELEGRAM_WEBHOOK_PUBLIC_URL or fix ngrok / WEBAPP_ENABLE_NGROK)."
        )

    # Show per-request access lines by default so monitor traffic is visible.
    # Set WEBAPP_SHOW_ACCESS_LOGS=0/false/no/off to mute them.
    show_access_logs = os.getenv("WEBAPP_SHOW_ACCESS_LOGS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    logging.getLogger("werkzeug").setLevel(
        logging.INFO if show_access_logs else logging.WARNING
    )

    app.run(host=host, port=port, debug=False, use_reloader=False)
