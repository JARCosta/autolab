"""
Notification channel for AutoLab: the user-facing side (frontend).

Domain services (stream_elements betting, wallapop_tracker, webapp commands) send
messages through this API. The channel is set at runtime startup to the Telegram
implementation so domain code does not depend on the web layer.
"""
import threading
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

    def edit_message(self, chat_id: int, message_id: int, text: str) -> Any:
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


# Simple aggregated error notifier to collapse repeated equivalent errors
class _ErrorAggregator:
    def __init__(self):
        self._lock = threading.Lock()
        # key -> {count: int, sources: set[str], timer: threading.Timer, last_message: str}
        self._map: dict[str, dict] = {}

    def _send_summary(self, key: str):
        with self._lock:
            entry = self._map.pop(key, None)
        if not entry:
            return
        count = entry["count"]
        sources = sorted(entry["sources"])
        last = entry.get("last_message", "")
        short = last.splitlines()[0] if last else "(no details)"
        msg = f"[{count}x] Repeated error: {short}\nSources: {', '.join(sources)}\n"
        if count == 1:
            msg = f"1 occurrence: {last}\n"
        # send as notification+log when channel present
        try:
            send_message(msg, log=True, notification=True)
        except Exception:
            # best-effort: swallow to avoid recursion
            pass

    def notify(self, message: str, source: Optional[str] = None, window: int = 30) -> None:
        """Notify about an error but aggregate repeated equivalent messages.

        - message: full message (traceback ok)
        - source: identifier like "channel, username"
        - window: aggregation window in seconds
        """
        # create a simple key from the first line of message to group similar errors
        key = message.splitlines()[0] if message else ""
        with self._lock:
            entry = self._map.get(key)
            if entry is None:
                entry = {"count": 1, "sources": set(), "last_message": message, "message_result": None, "short": None}
                if source:
                    entry["sources"].add(source)
                short = message.splitlines()[0] if message else "(no details)"
                entry["short"] = short
                # send a concise notification (short headline + sources) and keep its message result for editing
                notif_text = f"{short}\nSources: {source}" if source else short
                res = send_message(notif_text, log=False, notification=True)
                entry["message_result"] = res
                # always write full details to the logs
                send_message(f"[{source}] {message}", log=True, notification=False)
                self._map[key] = entry
            else:
                entry["count"] += 1
                if source:
                    entry["sources"].add(source)
                entry["last_message"] = message
                # update the notification message to include the expanded sources list
                sources_str = ", ".join(sorted(entry["sources"])) if entry["sources"] else ""
                new_text = f"{entry['short']}\nSources: {sources_str}" if entry.get("short") else sources_str
                res = entry.get("message_result")
                if isinstance(res, dict):
                    chat_id = res.get("chat", {}).get("id")
                    message_id = res.get("message_id")
                    if chat_id and message_id:
                        edit_message(chat_id, message_id, new_text)
                # also append full details to the logs
                send_message(f"[{source}] {message}", log=True, notification=False)



# singleton aggregator
_error_aggregator = _ErrorAggregator()


def send_aggregated_error(message: str, source: Optional[str] = None, window: int = 30) -> None:
    return _error_aggregator.notify(message, source=source, window=window)


def send_image(
    image_path: str, caption: str = "", log: bool = True, notification: bool = False
) -> Any:
    return _channel_or_raise().send_image(
        image_path, caption=caption, log=log, notification=notification
    )

def edit_message(chat_id: int, message_id: int, text: str) -> Any:
    return _channel_or_raise().edit_message(chat_id, message_id, text)


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
