"""JSON-backed betting tuning: variable delay and last-placed bet per channel."""

import json
import os

import paths
from app.backend.notifications import add_telegram_log

RESOURCES_DIR = paths.STREAMELEMENTS_RESOURCES_DIR
DELAY_DEFAULT = 2.05
DELAY_GOAL = 0.4

_LAST_BET_FILE = paths.STREAMELEMENTS_LAST_BET_FILE


def get_variable_delay() -> float:
    path = paths.STREAMELEMENTS_VARIABLE_DELAY_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            variable_delay = float(f.read())
    except FileNotFoundError:
        variable_delay = DELAY_DEFAULT
        set_variable_delay(variable_delay)
    return min(max(variable_delay, 0.0), 5.0)


def set_variable_delay(delay: float) -> float:
    path = paths.STREAMELEMENTS_VARIABLE_DELAY_FILE
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(round(delay, 2)))
    return delay


def change_variable_delay(amount: float = 0.1) -> None:
    if round(amount, 2) == 0:
        return
    variable_delay = round(get_variable_delay() + amount, 2)
    set_variable_delay(variable_delay)
    sign = "+" if amount > 0 else "-"
    add_telegram_log(f"Variable delay changed to {get_variable_delay()}({sign}{round(abs(amount), 2)})\n")


def get_last_bet_full() -> dict:
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    if not os.path.exists(_LAST_BET_FILE):
        return {}
    with open(_LAST_BET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_last_bet(channel: str):
    last_bet_full = get_last_bet_full()
    if channel not in last_bet_full:
        return None
    return last_bet_full[channel]


def contest_to_bet(contest: dict, bet_option: str, bet_amount: float) -> dict:
    return {
        "contest_id": contest["contest"]["_id"],
        "options": {option["command"]: option["totalAmount"] for option in contest["contest"]["options"]},
        "bet_option": bet_option,
        "bet_amount": bet_amount,
    }


def save_last_bet(channel: str, bet: dict) -> None:
    last_bet_full = get_last_bet_full()
    last_bet_full[channel] = bet
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    with open(_LAST_BET_FILE, "w", encoding="utf-8") as f:
        json.dump(last_bet_full, f, indent=2)
