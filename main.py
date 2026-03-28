"""
AutoLab - Process orchestrator.
Launches all services: StreamElements bettors, Telegram webapp, and Discord bot.
Uses threading (I/O-bound workload); one process keeps memory low and logs consistent.
"""
import threading
from dotenv import load_dotenv

from config import STREAMELEMENTS_BETTORS, WALLAPOP_POLL_ENABLED

load_dotenv()

if __name__ == "__main__":
    from logging_config import setup_logging
    from notifications.telegram import TelegramChannel
    import notifications

    log = setup_logging("autolab")
    notifications.set_channel(TelegramChannel())

    kill_event = threading.Event()

    from stream_elements.oauth import check_oauth_token

    OAUTH = {
        "El_Pipow": check_oauth_token("El_Pipow"),
        "JRCosta": check_oauth_token("JRCosta"),
    }

    threads = []

    from stream_elements.bettor import Bettor

    for channel, bettors in STREAMELEMENTS_BETTORS.items():
        for username, is_bettor in bettors.items():
            args = (channel, username, OAUTH[username], kill_event, is_bettor)
            t = threading.Thread(target=Bettor, args=args, daemon=False)
            threads.append(t)

    import webapp
    t_webapp = threading.Thread(target=webapp.launch, args=(), daemon=True)
    threads.append(t_webapp)

    from boost_bot.main import run_bot as run_discord_bot
    t_discord = threading.Thread(target=run_discord_bot, args=(), daemon=True)
    threads.append(t_discord)

    import os

    def run_server_hardware_client():
        token = os.getenv("HARDWARE_PUSH_TOKEN", "").strip()
        if not token:
            return
        url = os.getenv("HARDWARE_PUSH_URL", "").strip() or (
            "http://127.0.0.1:5000/api/monitor/push"
        )
        from hardware_client import get_local_device_name, run_push_loop

        interval = float(os.getenv("HARDWARE_PUSH_INTERVAL", "10"))
        run_push_loop(
            url,
            token,
            get_local_device_name(),
            interval,
            kill_event=kill_event,
        )

    t_hw = threading.Thread(target=run_server_hardware_client, daemon=True)
    threads.append(t_hw)

    if WALLAPOP_POLL_ENABLED:
        from wallapop_tracker.tracker import SearchRunner

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
