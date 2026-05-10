"""
Per-service entrypoint.

Each docker-compose service runs::

    python -m app.runtime.entrypoint <service>

where ``<service>`` is one of: ``web``, ``bettors``, ``discord``, ``wallapop``,
``continente``, or ``inbound``.

The **autolab-tailscale** service is a separate Docker image in ``docker-compose.yml``; it is not launched by this Python entrypoint.

Containerised services (``bettors``/``discord``/``wallapop``) read
``data/modules.json`` first; if their module is disabled, they exit cleanly
with code 0 so docker compose (with ``restart: on-failure``) leaves them
stopped until the next ``autolab restart`` brings them back according to the
enabled profiles.
"""
from __future__ import annotations

import argparse
import sys
import threading

from dotenv import load_dotenv


def _setup_common():
    """Init shared cross-cutting concerns (logging, .env, notifications, DB)."""
    load_dotenv()

    import app.backend.notifications as notifications
    from app.backend.notifications.telegram import TelegramChannel
    from app.infrastructure.storage.balances_db.repository import init_db
    from logging_config import setup_logging

    log = setup_logging("autolab")
    notifications.set_channel(TelegramChannel())
    init_db()
    return log


def _run_bettors(kill_event: threading.Event) -> list[threading.Thread]:
    """Spawn one Bettor thread per (channel, username) pair."""
    from app.backend.stream_elements import Bettor
    from app.infrastructure.storage.balances_db.channels_data import (
        active_channels_nested,
    )
    from app.infrastructure.storage.twitch_oauth import check_oauth_token

    channels = active_channels_nested()
    viewers = list({
        viewer
        for data in channels.values()
        for viewer in data["Bettors"].keys()
    })
    oauth = {viewer: check_oauth_token(viewer) for viewer in viewers}

    threads: list[threading.Thread] = []
    for channel, data in channels.items():
        for username, is_bettor in data["Bettors"].items():
            args = (channel, username, oauth[username], kill_event, is_bettor)
            t = threading.Thread(
                target=Bettor,
                args=args,
                daemon=False,
                name=f"bettor:{channel}:{username}",
            )
            threads.append(t)
    return threads


def _run_wallapop(kill_event: threading.Event) -> threading.Thread:
    from app.backend.wallapop_tracker.tracker import SearchRunner

    def loop():
        runner = SearchRunner()
        while not kill_event.is_set():
            kill_event.wait(timeout=60)
        for proc in runner.processes.values():
            proc.terminate()

    return threading.Thread(target=loop, daemon=True, name="wallapop")


def _exit_if_disabled(name: str, log) -> None:
    """Containerised modules exit 0 when their toggle is off."""
    from app.runtime.modules import is_enabled

    if not is_enabled(name):
        log.info("Module %r is disabled in modules.json; exiting.", name)
        sys.exit(0)


def cmd_web(_args) -> int:
    log = _setup_common()
    from app.runtime.modules import container_profiles, load_state

    st = load_state()
    profiles = container_profiles()
    log.info("Starting webapp service (Flask only in this container).")
    log.info(
        "modules.json flags: %s — compose profiles for sibling containers: %s",
        st,
        profiles or "(none — only autolab-web will be running)",
    )
    import webapp

    webapp.launch()
    return 0


def cmd_bettors(_args) -> int:
    log = _setup_common()
    _exit_if_disabled("bettors", log)

    log.info("autolab-bettors: StreamElements / Twitch IRC (separate container from autolab-web).")
    kill_event = threading.Event()
    threads = _run_bettors(kill_event)
    if not threads:
        log.warning("No active bettor configurations found; exiting.")
        return 0

    for t in threads:
        t.start()
    log.info("Started %d bettor thread(s): %s.", len(threads), ", ".join(t.name for t in threads))

    try:
        kill_event.wait()
    except KeyboardInterrupt:
        log.info("Shutdown signal received; stopping bettors...")
        kill_event.set()

    for t in threads:
        t.join(timeout=10)
    log.info("Bettors stopped.")
    return 0


def cmd_discord(_args) -> int:
    log = _setup_common()
    _exit_if_disabled("discord", log)

    from app.backend.boost_bot.main import run_bot

    log.info("Starting Discord boost_bot.")
    run_bot()  # blocks
    return 0


def cmd_wallapop(_args) -> int:
    log = _setup_common()
    _exit_if_disabled("wallapop", log)

    kill_event = threading.Event()
    t = _run_wallapop(kill_event)
    t.start()
    log.info("Started Wallapop tracker.")

    try:
        kill_event.wait()
    except KeyboardInterrupt:
        log.info("Shutdown signal received; stopping wallapop...")
        kill_event.set()
    t.join(timeout=15)
    log.info("Wallapop stopped.")
    return 0


def cmd_inbound(_args) -> int:
    log = _setup_common()
    import webapp.inbound as inbound_web

    log.info("Starting inbound gateway (Telegram webhook + optional ngrok).")
    inbound_web.launch()
    return 0


def cmd_continente(_args) -> int:
    log = _setup_common()
    _exit_if_disabled("continente", log)

    from app.backend.continente_tracker.tracker import run_forever

    log.info("Starting Continente tracker polling loop.")
    run_forever()
    return 0


_COMMANDS = {
    "web": cmd_web,
    "bettors": cmd_bettors,
    "discord": cmd_discord,
    "wallapop": cmd_wallapop,
    "continente": cmd_continente,
    "inbound": cmd_inbound,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autolab")
    parser.add_argument("service", choices=sorted(_COMMANDS.keys()))
    args = parser.parse_args(argv)
    return _COMMANDS[args.service](args)


if __name__ == "__main__":
    raise SystemExit(main())
