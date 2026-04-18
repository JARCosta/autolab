"""StreamElements + Faceit helpers used by betting (IDs, balances, probabilities, timing)."""

import datetime
import threading

from app.backend.notifications import send_message, send_message_threaded
from app.infrastructure.http import faceit, streamelements
from app.infrastructure.storage.balances_db.channels_data import get_channel_meta, streamelements_account_id
from logging_config import setup_logging

log = setup_logging("stream_elements.se_helpers")


def get_streamelements_id(channel: str) -> str | None:
    sid = streamelements_account_id(channel)
    if sid:
        return sid
    send_message_threaded(f"ValueError:\n No StreamElements id found for {channel}", notification=True)
    return None


def compute_probabilities(channel: str, options: dict) -> None:
    channel_data = get_channel_meta(channel) or {}

    if "SteamId" not in channel_data:
        send_message_threaded(
            f"[{channel}] No SteamId found for {channel}. Cannot compute probabilities from Faceit.",
            notification=True,
        )
        return None

    if len(options) == 2 and "win" in options and "lose" in options:
        faceit_id = channel_data["FaceitId"]

        response = faceit.get_matches_group_by_state(faceit_id)
        if response.status_code != 200:
            send_message_threaded(f"[{channel}] Error fetching Faceit data: {response.status_code}", notification=True)
            return None
        response_json = response.json()
        if "ONGOING" not in response_json["payload"]:
            send_message_threaded(
                f"[{channel}] Couldn't find any faceit game for Faceit user {faceit_id}"
            )
            return None
        active_game_id = response_json["payload"]["ONGOING"][0]["id"]

        response = faceit.get_match(active_game_id)
        response_json = response.json()
        for faction in response_json["payload"]["teams"].keys():
            if faceit_id in [player["id"] for player in response_json["payload"]["teams"][faction]["roster"]]:
                options["win"]["probability"] = response_json["payload"]["teams"][faction]["stats"]["winProbability"]
            else:
                options["lose"]["probability"] = response_json["payload"]["teams"][faction]["stats"]["winProbability"]

    elif len(options) > 2:
        send_message_threaded(
            "More than 2 options found in contest. Cannot compute probabilities from Faceit.",
            notification=True,
        )
    return None


def fetch_balance(channel: str, username: str) -> int:
    channel_id = get_streamelements_id(channel)
    if not channel_id:
        return 0
    response = streamelements.get_points(channel_id, username)
    if response.json().get("error") == "Not Found":
        return 0
    if response.status_code != 200:
        send_message_threaded(
            f"Error {response.status_code} getting balance for {username} in {channel}\n{response.json()}",
            notification=True,
        )
        return fetch_balance(channel, username)
    return int(response.json()["points"])


def sleep_until(end: datetime.datetime, kill_thread: threading.Event):
    import time

    now = datetime.datetime.now()
    if now < end:
        sleep_time = (end - now).total_seconds()
        log.info("Sleeping for %s seconds", sleep_time)
        for _ in range(int(sleep_time) // 10):
            time.sleep(10)
            if kill_thread.is_set():
                break
        time.sleep(sleep_time % 10)
        return True
    send_message(f"Time has already passed\nNow: {now}\nEnd: {end}\n\n")
    return False
