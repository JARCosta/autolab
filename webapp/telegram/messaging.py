"""Telegram messaging helpers: send_message, send_image, and log buffer."""
import os
import time

import requests

_NOTIFICATION_TOKEN = None
_LOGS_TOKEN = None
_USER_ID = None


def _get_tokens():
    global _NOTIFICATION_TOKEN, _LOGS_TOKEN, _USER_ID
    if _NOTIFICATION_TOKEN is None:
        _NOTIFICATION_TOKEN = os.getenv("TELEGRAM_NOTIFICATION_TOKEN")
        _LOGS_TOKEN = os.getenv("TELEGRAM_LOGS_TOKEN")
        _USER_ID = os.getenv("TELEGRAM_USER_ID")
    return _NOTIFICATION_TOKEN, _LOGS_TOKEN, _USER_ID


def _do_send_message(token, params):
    while True:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=params)
            break
        except requests.exceptions.ConnectionError as e:
            print(e)
            time.sleep(2)
    if not r.ok:
        desc = r.json().get("description", "")
        if "text is too long" in desc or "message is too long" in desc:
            split_list = params["text"].split("\n")
            mid = len(split_list) // 2
            _do_send_message(token, {"chat_id": params["chat_id"], "text": "\n".join(split_list[:mid])})
            r = _do_send_message(token, {"chat_id": params["chat_id"], "text": "\n".join(split_list[mid:])})
        elif "Too Many Requests" in desc:
            wait_time = int(r.json().get("parameters", {}).get("retry_after", 5)) + 1
            time.sleep(wait_time)
            r = _do_send_message(token, params)
        else:
            raise Exception(f"Error sending message: {r.text}\nParams: {params}")
    return r


def _do_send_image(token, params, files):
    while True:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data=params, files=files)
            break
        except requests.exceptions.ConnectionError as e:
            print(e)
            time.sleep(2)
    if not r.ok:
        desc = r.json().get("description", "")
        if "Too Many Requests" in desc:
            wait_time = int(r.json().get("parameters", {}).get("retry_after", 5)) + 1
            time.sleep(wait_time)
            r = _do_send_image(token, params, files)
        else:
            raise Exception(f"Error sending image: {r.text}\nParams: {params}")
    return r


def send_message(message: str, log: bool = True, notification: bool = False):
    notification_token, logs_token, user_id = _get_tokens()
    params = {"chat_id": user_id, "text": message}
    r = None
    if notification:
        r = _do_send_message(notification_token, params)
    if log:
        r = _do_send_message(logs_token, params)
    return r.json()["result"] if r else None


def send_image(image_path: str, caption: str = "", log: bool = True, notification: bool = False):
    notification_token, logs_token, user_id = _get_tokens()
    params = {"chat_id": user_id, "caption": caption}
    files = {"photo": open(image_path, "rb")}
    r = None
    if notification:
        r = _do_send_image(notification_token, params, files)
    if log:
        r = _do_send_image(logs_token, params, files)
    return r.json()["result"] if r else None


def send_message_threaded(message: str, log: bool = True, notification: bool = False):
    import multiprocessing
    multiprocessing.Process(target=send_message, args=(message, log, notification)).start()


def send_image_threaded(image_path: str, caption: str = "", log: bool = True, notification: bool = False):
    import multiprocessing
    multiprocessing.Process(target=send_image, args=(image_path, caption, log, notification)).start()


# ── Log buffer ───────────────────────────────────────────────
_LOG_FILE = "data/telegram_message.txt"


def get_telegram_log() -> str:
    try:
        with open(_LOG_FILE, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def add_telegram_log(message: str) -> None:
    os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
    with open(_LOG_FILE, "a") as f:
        f.write(message)
    print(message, end="")


def clear_telegram_log() -> None:
    os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
    open(_LOG_FILE, "w").close()


def send_telegram_log() -> None:
    message = get_telegram_log()
    if message:
        send_message(message)
        clear_telegram_log()


def send_telegram_log_with_image(image_path: str) -> None:
    message = get_telegram_log()
    if message:
        send_image(image_path, caption=message)
        clear_telegram_log()


def send_telegram_log_threaded() -> None:
    import multiprocessing
    multiprocessing.Process(target=send_telegram_log).start()
