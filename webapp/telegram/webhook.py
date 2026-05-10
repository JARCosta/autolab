"""Telegram update handler used by inbound ingress."""
import multiprocessing
import traceback

from app.backend.notifications import send_message
from webapp.telegram.commands import commands


def _proc_function(command, arguments):
    try:
        commands[command]["function"](*arguments)
    except Exception as e:
        send_message(
            f"Error executing command /{command}: {e}\n{traceback.format_exc()}",
            notification=True,
        )


def process_update(update: dict | None) -> None:
    """Handle one Telegram update payload."""
    if not isinstance(update, dict):
        return
    if "message" in update:
        text = str(update["message"].get("text") or "")
        if text.startswith("/"):
            parts = text[1:].split(" ")
            command, arguments = parts[0], parts[1:]
            if command in commands:
                multiprocessing.Process(
                    target=_proc_function, args=(command, arguments)
                ).start()
