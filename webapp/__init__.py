"""
Flask application factory for dashboard/UI routes.

Blueprints:
  - shared: site-wide static (/static/shared/…)
  - home: landing page at /
  - modules.streamelements, modules.monitor, modules.discord_bot,
    modules.wallapop, modules.system, modules.cloud: feature UIs + APIs

The ``monitor`` blueprint is registered conditionally on
``modules.json["monitor"]`` (the rest of the per-module toggles control
separate docker-compose services and don't gate webapp routes).

**Module dashboard pages** must extend ``webapp/templates/module_layout.html`` and
follow ``webapp/shared/MODULE_PAGE.md`` (CSS shell, required Jinja blocks).

To add a feature UI:
  1. Add ``webapp/modules/<name>/`` with a Blueprint (``template_folder`` + usually ``static_folder``).
  2. Register it in ``create_app()`` below.
  3. Implement the page template per ``MODULE_PAGE.md``.
"""
import logging
import os

from flask import Flask

from logging_config import setup_logging

log = setup_logging("webapp")

def create_app():
    app = Flask(__name__)
    asset_version = os.getenv("WEBAPP_ASSET_VERSION", "1")

    @app.context_processor
    def inject_asset_version():
        return {"asset_version": asset_version}

    from app.runtime.modules import is_enabled
    from webapp.modules.cloud import cloud_bp
    from webapp.modules.continente import continente_bp
    from webapp.home import home_bp
    from webapp.modules.discord_bot import discord_bot_bp
    from webapp.modules.streamelements import streamelements_bp
    from webapp.modules.system import system_bp
    from webapp.modules.wallapop import wallapop_bp
    from webapp.shared import shared_bp

    app.register_blueprint(shared_bp, url_prefix="/")
    app.register_blueprint(home_bp, url_prefix="/")
    app.register_blueprint(cloud_bp, url_prefix="/")
    app.register_blueprint(streamelements_bp, url_prefix="/")
    app.register_blueprint(discord_bot_bp, url_prefix="/")
    app.register_blueprint(wallapop_bp, url_prefix="/")
    app.register_blueprint(continente_bp, url_prefix="/")
    app.register_blueprint(system_bp, url_prefix="/")

    if is_enabled("monitor"):
        from webapp.modules.monitor import monitor_bp
        app.register_blueprint(monitor_bp, url_prefix="/")
    else:
        log.info("Hardware Monitor disabled in modules.json; skipping blueprint.")

    return app


def launch():
    """Entry point for the ``web`` runtime service."""
    port = int(os.getenv("WEBAPP_PORT", "5000"))
    host = os.getenv("WEBAPP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    app = create_app()
    log.info("autolab-web serves dashboard/UI only; inbound webhooks run in autolab-inbound.")

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
