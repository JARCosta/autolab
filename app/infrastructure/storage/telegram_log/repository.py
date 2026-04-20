"""Read/write helpers for Telegram log buffer file."""

from __future__ import annotations

import os

import paths


def _ensure_log_dir() -> None:
    os.makedirs(os.path.dirname(paths.TELEGRAM_LOG_FILE), exist_ok=True)


def append_log(message: str) -> None:
    _ensure_log_dir()
    with open(paths.TELEGRAM_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message)


def read_log() -> str:
    try:
        with open(paths.TELEGRAM_LOG_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def clear_log() -> None:
    _ensure_log_dir()
    with open(paths.TELEGRAM_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")
