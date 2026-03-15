"""Telegram webhook route handler."""
import multiprocessing
import traceback

from flask import request
from notifications import send_message

from webapp.telegram import telegram_bp
from webapp.telegram.commands import commands


def _proc_function(command, arguments):
    try:
        commands[command]["function"](*arguments)
    except Exception as e:
        send_message(
            f"Error executing command /{command}: {e}\n{traceback.format_exc()}",
            notification=True,
        )


@telegram_bp.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    if "message" in update:
        text = update["message"]["text"]
        if text.startswith("/"):
            parts = text[1:].split(" ")
            command, arguments = parts[0], parts[1:]
            if command in commands:
                multiprocessing.Process(
                    target=_proc_function, args=(command, arguments)
                ).start()
    return "", 200
