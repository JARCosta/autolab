"""
Notification channel for AutoLab: the user-facing side (frontend).

Domain services (stream_elements betting, wallapop_tracker, webapp commands) send
messages through this API. The channel is set at runtime startup to the Telegram
implementation so domain code does not depend on the web layer.
"""
from dataclasses import dataclass, field
import threading
import time
from typing import Any, Optional

_channel: Optional["NotificationChannel"] = None


class NotificationChannel:
    """Interface for the user-facing notification channel (e.g. Telegram)."""

    def send_message(self, message: str, log: bool = True, notification: bool = False) -> Any:
        """Send a message to the user."""
        raise NotImplementedError

    def send_image(
        self, image_path: str, caption: str = "", log: bool = True, notification: bool = False
    ) -> Any:
        """Send an image with optional caption."""
        raise NotImplementedError

    def edit_message(
        self, chat_id: int, message_id: int, text: str, notification: bool = True
    ) -> Any:
        """Edit a previously-sent message."""
        raise NotImplementedError

    def add_log(self, message: str) -> None:
        """Add a message to the log."""
        raise NotImplementedError

    def get_log(self) -> str:
        """Get the current log as a string."""
        raise NotImplementedError

    def clear_log(self) -> None:
        """Clear the current log."""
        raise NotImplementedError

    def send_log(self) -> None:
        """Send the current log to the user."""
        raise NotImplementedError

    def send_log_with_image(self, image_path: str) -> None:
        """Send the current log to the user with an image."""
        raise NotImplementedError


def set_channel(channel: NotificationChannel) -> None:
    globals()["_channel"] = channel


def _channel_or_raise() -> NotificationChannel:
    if _channel is None:
        raise RuntimeError(
            "Notification channel not set; call notifications.set_channel() at startup"
        )
    return _channel


@dataclass
class _MessageEntry:
    message: str
    created_at: float
    last_seen: float
    count: int = 1
    sources: set[str] = field(default_factory=set)
    notification_result: Any = None
    log_result: Any = None


class _MessageMerger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _MessageEntry] = {}

    @staticmethod
    def _key(message: str, log: bool, notification: bool) -> str:
        normalized = message.strip().splitlines()[-1].lower()
        return f"{normalized}:{int(log)}:{int(notification)}"
        # return hash(message)

    @staticmethod
    def _render(key: str, message: str, sources: set[str], count: int) -> str:
        parts = [message.strip()]
        if count > 1:
            parts.append(f"Merged {count} messages")
        if sources:
            parts.append(f"Sources: {', '.join(sorted(sources))}")
        # parts.append(f"Key: {key}, Hash: {hash(message)}")
        return "\n".join(parts)

    @staticmethod
    def _edit_result(result: Any, text: str, notification: bool) -> None:
        if not isinstance(result, dict):
            return
        chat_id = result.get("chat", {}).get("id")
        message_id = result.get("message_id")
        if chat_id and message_id:
            edit_message(chat_id, message_id, text, notification=notification)

    def send(
        self,
        message: str,
        *,
        log: bool = True,
        notification: bool = False,
        source: Optional[str] = None,
        window: int = 300,
    ) -> Any:
        key = self._key(message, log, notification)
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and now - entry.last_seen <= window:
                entry.count += 1
                entry.last_seen = now
                if source:
                    entry.sources.add(source)

                rendered = self._render(key, entry.message, entry.sources, entry.count)
                self._edit_result(entry.notification_result, rendered, notification=True)
                self._edit_result(entry.log_result, rendered, notification=False)
                return entry.notification_result or entry.log_result

            if entry is not None:
                self._entries.pop(key, None)

            rendered_sources: set[str] = {source} if source else set()
            rendered = self._render(key, message, rendered_sources, 1)

            channel = _channel_or_raise()
            notification_result = None
            log_result = None
            if notification:
                notification_result = channel.send_message(rendered, log=False, notification=True)
            if log:
                log_result = channel.send_message(rendered, log=True, notification=False)

            self._entries[key] = _MessageEntry(
                message=message,
                created_at=now,
                last_seen=now,
                count=1,
                sources=rendered_sources,
                notification_result=notification_result,
                log_result=log_result,
            )
            return notification_result or log_result


_message_merger = _MessageMerger()


def send_message(
    message: str,
    log: bool = True,
    notification: bool = False,
    source: Optional[str] = None,
    window: int = 300,
) -> Any:
    return _message_merger.send(
        message,
        log=log,
        notification=notification,
        source=source,
        window=window,
    )


def send_image(
    image_path: str, caption: str = "", log: bool = True, notification: bool = False
) -> Any:
    return _channel_or_raise().send_image(
        image_path, caption=caption, log=log, notification=notification
    )


def edit_message(chat_id: int, message_id: int, text: str, notification: bool = True) -> Any:
    return _channel_or_raise().edit_message(chat_id, message_id, text, notification=notification)


def send_message_threaded(
    message: str,
    log: bool = True,
    notification: bool = False,
    source: Optional[str] = None,
    window: int = 30,
) -> None:
    threading.Thread(
        target=send_message,
        args=(message,),
        kwargs={
            "log": log,
            "notification": notification,
            "source": source,
            "window": window,
        },
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
    send_message(message, log=True, notification=False)


def get_telegram_log() -> str:
    return ""


def clear_telegram_log() -> None:
    return None


def send_telegram_log() -> None:
    return None


def send_telegram_log_with_image(image_path: str) -> None:
    del image_path
    return None


def send_telegram_log_threaded() -> None:
    threading.Thread(target=send_telegram_log, daemon=True).start()
