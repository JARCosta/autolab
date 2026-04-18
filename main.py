"""
AutoLab - Process orchestrator.
Launches all services: StreamElements bettors, Telegram webapp, and Discord bot.
Uses threading (I/O-bound workload); one process keeps memory low and logs consistent.
"""
import threading

from dotenv import load_dotenv

load_dotenv()

WALLAPOP_POLL_ENABLED = False

if __name__ == "__main__":
    import app.backend.notifications as notifications
    from app.backend.notifications.telegram import TelegramChannel
    from logging_config import setup_logging

    log = setup_logging("autolab")
    notifications.set_channel(TelegramChannel())

    kill_event = threading.Event()

    from app.infrastructure.storage.balances_db.channels_data import (
        active_channels_nested,
    )
    from app.infrastructure.storage.balances_db.repository import init_db

    init_db()

    from app.infrastructure.twitch.oauth import check_oauth_token



    viewers = [viewer_id for channel_data in active_channels_nested().values() for viewer_id in channel_data["Bettors"].keys()]
    viewers = list(set(viewers))
    OAUTH = {viewer_id: check_oauth_token(viewer_id) for viewer_id in viewers}

    threads = []

    from app.backend.stream_elements import Bettor

    for channel, data in active_channels_nested().items():
        for username, is_bettor in data["Bettors"].items():
            args = (channel, username, OAUTH[username], kill_event, is_bettor)
            t = threading.Thread(target=Bettor, args=args, daemon=False)
            threads.append(t)

    import webapp
    t_webapp = threading.Thread(target=webapp.launch, args=(), daemon=True)
    threads.append(t_webapp)

    from app.backend.boost_bot.main import run_bot as run_discord_bot
    t_discord = threading.Thread(target=run_discord_bot, args=(), daemon=True)
    threads.append(t_discord)

    if WALLAPOP_POLL_ENABLED:
        from app.backend.wallapop_tracker.tracker import SearchRunner

        def run_wallapop():
            runner = SearchRunner()
            while not kill_event.is_set():
                kill_event.wait(timeout=60)
            for proc in runner.processes.values():
                proc.terminate()

        t_wallapop = threading.Thread(target=run_wallapop, daemon=True)
        threads.append(t_wallapop)

    for t in threads:
        t.start()

    try:
        kill_event.wait()
    except KeyboardInterrupt:
        log.info("Shutdown signal received. Stopping threads...")
        kill_event.set()

    # Join Bettor threads (non-daemon); webapp/discord are daemon and will exit with process
    join_timeout = 10
    for t in threads:
        if not t.daemon:
            t.join(timeout=join_timeout)

    log.info("All threads stopped.")
