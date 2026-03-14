import datetime
import json
import os
import re
import threading
import time
import traceback
from typing import Any, Dict, Optional

import requests

import config
from webapp.telegram.messaging import send_message_threaded, send_message

RESOURCES_DIR = os.path.join("stream_elements", "resources")


def get_streamelements_id(channel: str) -> str:
    try:
        return config.CHANNELS[channel.lower()]["StreamElementsId"]
    except (KeyError, ValueError):
        send_message_threaded(f"ValueError:\n No StreamElements id found for {channel}", notification=True)


def compute_probabilities(channel: str, options: dict) -> str:
    channel_data = config.CHANNELS.get(channel.lower(), {})

    if "SteamId" not in channel_data:
        send_message_threaded(f"[{channel}] No SteamId found for {channel}. Cannot compute probabilities from Faceit.", notification=True)
        return

    if len(options) == 2 and "win" in options and "lose" in options:
        faceit_id = channel_data["FaceitId"]

        active_games_url = f"https://www.faceit.com/api/match/v1/matches/groupByState?userId={faceit_id}"
        response = requests.get(active_games_url, timeout=5)
        if response.status_code != 200:
            send_message_threaded(f"[{channel}] Error fetching Faceit data: {response.status_code}", notification=True)
            return
        response_json = response.json()
        if "ONGOING" not in response_json["payload"]:
            send_message_threaded(f"[{channel}] Couldn't find any faceit game on: {active_games_url}")
            return
        active_game_id = response_json["payload"]["ONGOING"][0]["id"]

        active_game_url = f"https://www.faceit.com/api/match/v2/match/{active_game_id}"
        response = requests.get(active_game_url, timeout=5)
        response_json = response.json()
        for faction in response_json["payload"]["teams"].keys():
            if faceit_id in [player["id"] for player in response_json["payload"]["teams"][faction]["roster"]]:
                options["win"]["probability"] = response_json["payload"]["teams"][faction]["stats"]["winProbability"]
            else:
                options["lose"]["probability"] = response_json["payload"]["teams"][faction]["stats"]["winProbability"]

    elif len(options) > 2:
        send_message_threaded("More than 2 options found in contest. Cannot compute probabilities from Faceit.", notification=True)


def get_balance(channel: str, username: str) -> int:
    channel_id = get_streamelements_id(channel)
    response = requests.get(f"https://api.streamelements.com/kappa/v2/points/{channel_id}/{username.lower()}")
    if response.json().get("error") == "Not Found":
        return 0
    elif response.status_code != 200:
        send_message_threaded(f"Error {response.status_code} getting balance for {username} in {channel}\n{response.json()}", notification=True)
        return get_balance(channel, username)
    return int(response.json()["points"])


def sleep_until(end: datetime.datetime, kill_thread: threading.Event):
    now = datetime.datetime.now()
    if now < end:
        sleep_time = (end - now).total_seconds()
        print(f"Sleeping for {sleep_time} seconds")
        for _ in range(int(sleep_time) // 10):
            time.sleep(10)
            if kill_thread.is_set():
                break
        time.sleep(sleep_time % 10)
        return True
    else:
        send_message(f"Time has already passed\nNow: {now}\nEnd: {end}\n\n")
        return False


# ── Twitch message parsing ───────────────────────────────────


def parse_twitch_message(raw_message: str) -> Optional[Dict[str, Any]]:
    if not raw_message or not raw_message.strip():
        return None

    message = raw_message.strip()
    result = {
        "tags": {},
        "source": {},
        "command": "",
        "parameters": [],
        "channel": "",
        "message": "",
    }

    if message.startswith("@"):
        tags_end = message.find(" ")
        if tags_end == -1:
            return None
        tags_section = message[1:tags_end]
        message = message[tags_end + 1:]
        for tag in tags_section.split(";"):
            if "=" in tag:
                key, value = tag.split("=", 1)
                if key == "badges" and value:
                    badges = []
                    for badge in value.split(","):
                        if "/" in badge:
                            badge_name, badge_version = badge.split("/", 1)
                            badges.append({"name": badge_name, "version": badge_version})
                    result["tags"][key] = badges
                elif key == "emotes" and value:
                    emotes = []
                    for emote_group in value.split("/"):
                        if ":" in emote_group:
                            emote_id, positions = emote_group.split(":", 1)
                            emote_positions = []
                            for pos in positions.split(","):
                                if "-" in pos:
                                    start, end = pos.split("-")
                                    emote_positions.append({"start": int(start), "end": int(end)})
                            emotes.append({"id": emote_id, "positions": emote_positions})
                    result["tags"][key] = emotes
                elif key in ["mod", "subscriber", "turbo", "first-msg", "returning-chatter"]:
                    result["tags"][key] = value == "1"
                elif key in ["room-id", "user-id", "tmi-sent-ts"]:
                    result["tags"][key] = int(value) if value else None
                else:
                    result["tags"][key] = value if value else None

    if message.startswith(":"):
        source_end = message.find(" ")
        if source_end == -1:
            return None
        source_section = message[1:source_end]
        message = message[source_end + 1:]
        if "!" in source_section:
            nick_part, host_part = source_section.split("!", 1)
            result["source"]["nick"] = nick_part
            if "@" in host_part:
                user, host = host_part.split("@", 1)
                result["source"]["user"] = user
                result["source"]["host"] = host
            else:
                result["source"]["user"] = host_part
        else:
            result["source"]["host"] = source_section

    parts = message.split(" ")
    if parts:
        result["command"] = parts[0]
        if result["command"] == "PRIVMSG" and len(parts) >= 3:
            result["channel"] = parts[1]
            message_start = message.find(":", len(parts[0]) + len(parts[1]) + 2)
            if message_start != -1:
                result["message"] = message[message_start + 1:]
            result["parameters"] = parts[1:]
        else:
            result["parameters"] = parts[1:]

    return result


def extract_mentions(message: str) -> list[str]:
    return re.findall(r"@([a-zA-Z0-9_]+)", message)


def check_if_mentioned(message: str, username: str) -> bool:
    mentions = extract_mentions(message)
    return username.lower() in [mention.lower() for mention in mentions]


def format_message_json(parsed_message: Dict[str, Any], indent: int = 2) -> str:
    return json.dumps(parsed_message, indent=indent, ensure_ascii=False)


# ── Message frequency tracking ──────────────────────────────

_MESSAGE_LOGS_FILE = os.path.join(RESOURCES_DIR, "message_logs.json")


def get_message_logs(channel: str, message_text: str) -> Dict[str, Any]:
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    if not os.path.exists(_MESSAGE_LOGS_FILE):
        with open(_MESSAGE_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(_MESSAGE_LOGS_FILE, "r", encoding="utf-8") as f:
        message_logs = json.load(f)

    if channel not in message_logs:
        message_logs[channel] = {}
    if message_text.lower() not in message_logs[channel]:
        message_logs[channel][message_text.lower()] = {"history": [], "last_sent": None}

    return message_logs


def set_sent_message_timestamp(channel: str, message_text: str):
    message_logs = get_message_logs(channel, message_text)
    message_logs[channel][message_text.lower()]["last_sent"] = datetime.datetime.now().isoformat()
    with open(_MESSAGE_LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(message_logs, f, indent=4, ensure_ascii=False)


def is_message_on_cooldown(channel: str, message_text: str, cooldown_minutes: int = 15) -> bool:
    message_logs = get_message_logs(channel, message_text)
    last_sent_str = message_logs[channel][message_text.lower()]["last_sent"]
    if last_sent_str is None:
        return False
    last_sent = datetime.datetime.fromisoformat(last_sent_str)
    return datetime.datetime.now() - last_sent < datetime.timedelta(minutes=cooldown_minutes)


def get_message_frequency(channel: str, message_text: str) -> float:
    message_logs = get_message_logs(channel, message_text)
    message_history = message_logs[channel][message_text.lower()]["history"]
    for timestamp_str in message_history.copy():
        timestamp = datetime.datetime.fromisoformat(timestamp_str)
        if datetime.datetime.now() - timestamp > datetime.timedelta(minutes=15):
            del message_history[message_history.index(timestamp_str)]
    message_history.append(datetime.datetime.now().isoformat())
    message_logs[channel][message_text.lower()]["history"] = message_history

    with open(_MESSAGE_LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(message_logs, f, indent=4, ensure_ascii=False)

    return len(message_history) / 15.0
