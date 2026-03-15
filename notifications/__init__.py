"""
Notification channel for AutoLab: the user-facing side (frontend).

Domain services (stream_elements betting, wallapop_tracker, webapp commands) send
messages through this API. The channel is set at startup (main.py) to the Telegram
implementation — your frontend — so domain code does not depend on webapp.
"""
import threading
from typing import Any, Optional

_channel: Optional["NotificationChannel"] = None


class NotificationChannel:
    """Interface for the user-facing notification channel (e.g. Telegram)."""

    def send_message(self, message: str, log: bool = True, notification: bool = False) -> Any:
        raise NotImplementedError

    def send_image(
        self, image_path: str, caption: str = "", log: bool = True, notification: bool = False
    ) -> Any:
        raise NotImplementedError

    def add_log(self, message: str) -> None:
        raise NotImplementedError

    def get_log(self) -> str:
        raise NotImplementedError

    def clear_log(self) -> None:
        raise NotImplementedError

    def send_log(self) -> None:
        raise NotImplementedError

    def send_log_with_image(self, image_path: str) -> None:
        raise NotImplementedError


def set_channel(channel: NotificationChannel) -> None:
    global _channel
    _channel = channel


def _channel_or_raise() -> NotificationChannel:
    if _channel is None:
        raise RuntimeError(
            "Notification channel not set; call notifications.set_channel() at startup"
        )
    return _channel


def send_message(message: str, log: bool = True, notification: bool = False) -> Any:
    return _channel_or_raise().send_message(message, log=log, notification=notification)


def send_image(
    image_path: str, caption: str = "", log: bool = True, notification: bool = False
) -> Any:
    return _channel_or_raise().send_image(
        image_path, caption=caption, log=log, notification=notification
    )


def send_message_threaded(message: str, log: bool = True, notification: bool = False) -> None:
    threading.Thread(
        target=send_message,
        args=(message,),
        kwargs={"log": log, "notification": notification},
        daemon=True,
    ).start()


def send_image_threaded(
    image_path: str, caption: str = "", log: bool = True, notification: bool = False
) -> None:
    threading.Thread(
        target=send_image,
        args=(image_path,),
        kwargs={"caption": caption, "log": log, "notification": notification},
        daemon=True,
    ).start()


def add_telegram_log(message: str) -> None:
    _channel_or_raise().add_log(message)


def get_telegram_log() -> str:
    return _channel_or_raise().get_log()


def clear_telegram_log() -> None:
    _channel_or_raise().clear_log()


def send_telegram_log() -> None:
    _channel_or_raise().send_log()


def send_telegram_log_with_image(image_path: str) -> None:
    _channel_or_raise().send_log_with_image(image_path)


def send_telegram_log_threaded() -> None:
    threading.Thread(target=send_telegram_log, daemon=True).start()
