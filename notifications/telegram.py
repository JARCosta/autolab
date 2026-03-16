"""Telegram as the user-facing notification channel (frontend)."""
import os
import time

import requests

import paths
from logging_config import setup_logging

_log = setup_logging("notifications.telegram")


class TelegramChannel:
    """Sends messages and log buffer via Telegram Bot API (your frontend)."""

    def __init__(self):
        self._notification_token = os.getenv("TELEGRAM_NOTIFICATION_TOKEN")
        self._logs_token = os.getenv("TELEGRAM_LOGS_TOKEN")
        self._user_id = os.getenv("TELEGRAM_USER_ID")
        self._log_file = paths.TELEGRAM_LOG_FILE

    def _do_send_message(self, token: str, params: dict):
        while True:
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage", data=params, timeout=30
                )
                break
            except requests.exceptions.ConnectionError as e:
                _log.warning("Connection error: %s", e)
                time.sleep(2)
        if not r.ok:
            desc = r.json().get("description", "")
            if "text is too long" in desc or "message is too long" in desc:
                split_list = params["text"].split("\n")
                mid = len(split_list) // 2
                self._do_send_message(token, {"chat_id": params["chat_id"], "text": "\n".join(split_list[:mid])})
                r = self._do_send_message(token, {"chat_id": params["chat_id"], "text": "\n".join(split_list[mid:])})
            elif "Too Many Requests" in desc:
                wait_time = int(r.json().get("parameters", {}).get("retry_after", 5)) + 1
                time.sleep(wait_time)
                r = self._do_send_message(token, params)
            else:
                raise Exception(f"Error sending message: {r.text}\nParams: {params}")
        return r

    def _do_send_image(self, token: str, params: dict, files: dict):
        while True:
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data=params,
                    files=files,
                    timeout=30,
                )
                break
            except requests.exceptions.ConnectionError as e:
                _log.warning("Connection error: %s", e)
                time.sleep(2)
        if not r.ok:
            desc = r.json().get("description", "")
            if "Too Many Requests" in desc:
                wait_time = int(r.json().get("parameters", {}).get("retry_after", 5)) + 1
                time.sleep(wait_time)
                r = self._do_send_image(token, params, files)
            else:
                raise Exception(f"Error sending image: {r.text}\nParams: {params}")
        return r

    def send_message(self, message: str, log: bool = True, notification: bool = False):
        params = {"chat_id": self._user_id, "text": message}
        r = None
        if notification and self._notification_token:
            r = self._do_send_message(self._notification_token, params)
        if log and self._logs_token:
            r = self._do_send_message(self._logs_token, params)
        return r.json()["result"] if r else None

    def send_image(
        self, image_path: str, caption: str = "", log: bool = True, notification: bool = False
    ):
        params = {"chat_id": self._user_id, "caption": caption}
        r = None
        if notification and self._notification_token:
            with open(image_path, "rb") as f:
                r = self._do_send_image(self._notification_token, params, {"photo": f})
        if log and self._logs_token:
            with open(image_path, "rb") as f:
                r = self._do_send_image(self._logs_token, params, {"photo": f})
        return r.json()["result"] if r else None

    def add_log(self, message: str) -> None:
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(message)
        _log.info("%s", message.rstrip())

    def get_log(self) -> str:
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def clear_log(self) -> None:
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
        open(self._log_file, "w").close()

    def send_log(self) -> None:
        msg = self.get_log()
        if msg:
            self.send_message(msg)
            self.clear_log()

    def send_log_with_image(self, image_path: str) -> None:
        msg = self.get_log()
        if msg:
            self.send_image(image_path, caption=msg)
            self.clear_log()
