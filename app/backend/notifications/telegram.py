"""Telegram as the user-facing notification channel (frontend)."""
import os
import time

import requests

from app.backend.notifications import NotificationChannel
from app.infrastructure.storage.telegram_log import append_log, clear_log, read_log
from logging_config import setup_logging

_log = setup_logging("notifications.telegram")


class TelegramChannel(NotificationChannel):
    """Sends messages and log buffer via Telegram Bot API (your frontend)."""

    def __init__(self):
        self._notification_token = os.getenv("TELEGRAM_NOTIFICATION_TOKEN")
        self._logs_token = os.getenv("TELEGRAM_LOGS_TOKEN")
        self._user_id = os.getenv("TELEGRAM_USER_ID")

    def _do_send(self, token: str, params: dict, files: dict = None):
        endpoint = "sendPhoto" if files else "sendMessage"
        while True:
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/{endpoint}",
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
            if "text is too long" in desc or "message is too long" in desc:
                text = params.get("text") or params.get("caption") or ""
                split_list = text.split("\n")
                mid = len(split_list) // 2
                part1 = {"chat_id": params["chat_id"], "text": "\n".join(split_list[:mid])}
                part2 = {"chat_id": params["chat_id"], "text": "\n".join(split_list[mid:])}
                r1 = self._do_send(token, part1, None)
                r2 = self._do_send(token, part2, None)
                r = r1 and r2
            elif "Too Many Requests" in desc:
                wait_time = int(r.json().get("parameters", {}).get("retry_after", 5)) + 1
                time.sleep(wait_time)
                r = self._do_send(token, params, files)
            else:
                raise Exception(f"Error sending message: {r.text}\nParams: {params}")
        return r

    def send_message(self, message: str, log: bool = True, notification: bool = False):
        params = {"chat_id": self._user_id, "text": message}
        r = None
        if notification and self._notification_token:
            r = self._do_send(self._notification_token, params)
        if log and self._logs_token:
            r = self._do_send(self._logs_token, params)
        return r.json()["result"] if r else None

    def edit_message(self, chat_id: int, message_id: int, text: str):
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if not self._notification_token:
            return None
        # editMessageText endpoint
        while True:
            try:
                r = requests.post(f"https://api.telegram.org/bot{self._notification_token}/editMessageText", data=params, timeout=30)
                break
            except requests.exceptions.ConnectionError as e:
                _log.warning("Connection error: %s", e)
                time.sleep(2)
        if not r.ok:
            desc = r.json().get("description", "")
            if "Too Many Requests" in desc:
                wait_time = int(r.json().get("parameters", {}).get("retry_after", 5)) + 1
                time.sleep(wait_time)
                return self.edit_message(chat_id, message_id, text)
            else:
                raise Exception(f"Error editing message: {r.text}\nParams: {params}")
        return r.json().get("result")

    def send_image(
        self, image_path: str, caption: str = "", log: bool = True, notification: bool = False
    ):
        params = {"chat_id": self._user_id, "caption": caption}
        r = None
        if notification and self._notification_token:
            with open(image_path, "rb") as f:
                r = self._do_send(self._notification_token, params, {"photo": f})
        if log and self._logs_token:
            with open(image_path, "rb") as f:
                r = self._do_send(self._logs_token, params, {"photo": f})
        return r.json()["result"] if r else None

    def add_log(self, message: str) -> None:
        append_log(message)
        _log.info("%s", message.rstrip())

    def get_log(self) -> str:
        return read_log()

    def clear_log(self) -> None:
        clear_log()

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
