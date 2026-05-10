"""Shared Telegram ingress helpers (webhook URL + optional ngrok)."""

from __future__ import annotations

import json
import os
import shutil

import requests

from logging_config import setup_logging
from webapp.telegram.commands import commands

log = setup_logging("telegram_ingress")


def start_ngrok(port: int):
    from pyngrok import conf, ngrok

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


def _ngrok_webhook_base(tunnel) -> str:
    public = os.getenv("NGROK_PUBLIC_URL", "").strip().rstrip("/")
    if public:
        return public
    return tunnel.public_url.rstrip("/")


def configure_telegram_webhook(port: int) -> str | None:
    """Register Telegram webhook from env/ngrok settings; return webhook URL."""
    explicit_webhook = os.getenv("TELEGRAM_WEBHOOK_PUBLIC_URL", "").strip()
    ngrok_enabled = os.getenv("WEBAPP_ENABLE_NGROK", "0").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    tunnel = None
    if explicit_webhook:
        log.info(
            "TELEGRAM_WEBHOOK_PUBLIC_URL is set; skipping ngrok (use your own HTTPS ingress)."
        )
    elif ngrok_enabled:
        try:
            tunnel = start_ngrok(port)
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.warning("ngrok unavailable; continuing without webhook tunnel: %s", e)
    else:
        log.info("WEBAPP_ENABLE_NGROK disabled; running without webhook tunnel.")

    notification_token = os.getenv("TELEGRAM_NOTIFICATION_TOKEN")
    logs_token = os.getenv("TELEGRAM_LOGS_TOKEN")

    if notification_token:
        command_helper_url = f"https://api.telegram.org/bot{notification_token}/setMyCommands"
        command_helper = {"commands": json.dumps([commands[cmd]["helper"] for cmd in commands])}
        requests.post(command_helper_url, data=command_helper, timeout=10)
    if logs_token:
        command_helper_url = f"https://api.telegram.org/bot{logs_token}/setMyCommands"
        requests.post(command_helper_url, data={"commands": json.dumps([])}, timeout=10)

    if explicit_webhook:
        webhook_url = explicit_webhook.rstrip("/")
    elif tunnel is not None:
        webhook_url = f"{_ngrok_webhook_base(tunnel)}/webhook"
    else:
        webhook_url = None

    if webhook_url and notification_token:
        log.info("Telegram webhook URL: %s", webhook_url)
        requests.post(
            f"https://api.telegram.org/bot{notification_token}/setWebhook",
            data={"url": webhook_url},
            timeout=10,
        )
    else:
        log.info(
            "Skipping Telegram webhook registration "
            "(set TELEGRAM_WEBHOOK_PUBLIC_URL for a public HTTPS URL, or set "
            "WEBAPP_ENABLE_NGROK=1 and NGROK_AUTH_TOKEN to use ngrok)."
        )
    return webhook_url
