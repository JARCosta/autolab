"""Betting utilities and routines for StreamElements betting system."""
import datetime
import json
import os
import threading
import time
import traceback
from math import sqrt

import matplotlib.pyplot as plt

from logging_config import setup_logging

log = setup_logging("stream_elements.betting")
import numpy as np
import requests
import websocket

import paths
from notifications import (
    add_telegram_log,
    send_image_threaded,
    send_message_threaded,
    send_telegram_log,
)
from stream_elements import utils

RESOURCES_DIR = paths.STREAMELEMENTS_RESOURCES_DIR
DELAY_DEFAULT = 2.05
DELAY_GOAL = 0.4


# ── Variable delay ───────────────────────────────────────────


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


def change_variable_delay(amount: float = 0.1) -> None:
    if round(amount, 2) == 0:
        return
    variable_delay = round(get_variable_delay() + amount, 2)
    set_variable_delay(variable_delay)
    sign = "+" if amount > 0 else "-"
    add_telegram_log(f"Variable delay changed to {get_variable_delay()}({sign}{round(abs(amount), 2)})\n")


# ── Last bet tracking ────────────────────────────────────────

_LAST_BET_FILE = paths.STREAMELEMENTS_LAST_BET_FILE


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


# ── Betting ──────────────────────────────────────────────────


def test_connection(ws: websocket.WebSocketApp) -> bool:
    try:
        ws.send("PING")
        return True
    except Exception:
        send_message_threaded(f"Error when testing connection: {traceback.format_exc()}", notification=True)
        return False


def get_active_contest(channel: str):
    channel_id = utils.get_streamelements_id(channel)
    while True:
        try:
            r = requests.get(f"https://api.streamelements.com/kappa/v2/contests/{channel_id}/active", timeout=10)
            break
        except Exception:
            send_message_threaded(f"[{channel}, streamElements] Error getting active contest: {traceback.format_exc()}")
            time.sleep(2)
    if not r.ok or r.json()["contest"] is None:
        return None, None
    response_json = r.json()
    start = datetime.datetime.strptime(response_json["contest"]["startedAt"], "%Y-%m-%dT%H:%M:%S.%fZ") + datetime.timedelta(hours=time.localtime().tm_isdst)
    end = start + datetime.timedelta(minutes=response_json["contest"]["duration"])
    return end, response_json


def get_contest_details(channel: str, contest_id: str):
    channel_id = utils.get_streamelements_id(channel)
    while True:
        try:
            r = requests.get(f"https://api.streamelements.com/kappa/v2/contests/{channel_id}/{contest_id}", timeout=10)
            break
        except Exception:
            send_message_threaded(f"[{channel}, streamElements] Error getting contest details: {traceback.format_exc()}")
            time.sleep(2)
    if not r.ok:
        return None
    return r.json()


# ── Optimal bet calculation ──────────────────────────────────


def optimal_bet(options: dict) -> tuple[str, int]:
    options_amounts = {option: option_data["amount"] for option, option_data in options.items()}

    if all(data["probability"] is not None for data in options.values()):
        options_probabilities = {option: option_data["probability"] for option, option_data in options.items()}
    elif all(data["probability"] is None for data in options.values()):
        options_probabilities = {option: 1 / len(options) for option in options.keys()}
    else:
        send_message_threaded(f"Error calculating optimal bet: Incomplete probabilities data\nOptions: {options}", notification=True)
        options_probabilities = {option: 1 / len(options) for option in options.keys()}

    no_bet_options = [option for option, amount in options_amounts.items() if amount == 0]
    if len(options) == len(no_bet_options):
        return None, 0
    if len(no_bet_options) > 0:
        max_probability_option = max(no_bet_options, key=lambda opt: options_probabilities[opt])
        return max_probability_option, 0

    expected_returns = {option: sum(options_amounts.values()) / amount * options_probabilities[option] for option, amount in options_amounts.items()}
    best_option = max(expected_returns, key=lambda opt: expected_returns[opt])
    if expected_returns[best_option] <= 1.0:
        return None, 0

    Ba = options_amounts[best_option]
    Oa = sum(options_amounts.values()) - Ba
    Bp = options_probabilities[best_option]
    optimal_bet_amount = -Ba + sqrt((Bp * Ba * Oa) / (1 / 1))
    del Ba, Oa, Bp

    log.info("Optimal bet for option '%s': %.2f points", best_option, optimal_bet_amount)
    return best_option, optimal_bet_amount


def bet_stats(options: dict, bet_option: str, bet_amount: float) -> tuple[float, float, float]:
    b = bet_amount
    if bet_option is None or bet_amount <= 0:
        return 0.0, 0.0, 0.0
    Ba = options[bet_option]["amount"]
    Oa = sum(option["amount"] for option in options.values()) - Ba
    pot_ratio = b / (Ba + b) if (Ba + b) > 0 else 0
    bet_profit = pot_ratio * Oa
    bet_odd = (b + bet_profit) / b if b > 0 else 0
    return pot_ratio, bet_profit, bet_odd


def bet_analysis(options: dict, bet_option: str, bet_amount: float) -> str:
    try:
        Ba = options[bet_option]["amount"]
    except KeyError as exc:
        raise KeyError(f"Error accessing bet option data: {traceback.format_exc()}") from exc
    Bp = options[bet_option]["probability"]
    Oa = sum(option["amount"] for option in options.values()) - Ba

    Xmin, Xmax = -Ba, Oa * 1.2
    Ymin, Ymax = -Ba, Oa * 1.2

    versions = {"1.1": [], "2.0": [], "2.2": []}
    bet_axis = np.linspace(Xmin, Xmax, 500)
    for b in bet_axis:
        pot_ratio = b / (Ba + b) if (Ba + b) > 0 else 0
        bet_profit = pot_ratio * Oa
        versions["1.1"].append(bet_profit - (2) * b)
        versions["2.0"].append(bet_profit - ((1 / 2) / Bp) * b)
        versions["2.2"].append(bet_profit - ((2 / 3) / Bp) * b)

    plt.figure(figsize=(10, 5))
    for _, version_list in versions.items():
        plt.plot(bet_axis, version_list, color="darkgray")
    for version, version_list in versions.items():
        version_indexes = max(i for (i, val) in enumerate(version_list) if Ymin < val < Ymax)
        plt.text(bet_axis[version_indexes], version_list[version_indexes], f"Risk v{version}", color="darkgray", va="bottom", ha="right")

    plt.axvline(x=bet_amount, color="red")
    plt.axhline(y=Oa, color="orange")
    plt.text(bet_axis[0], Oa * 0.95, [option for option in options if option != bet_option], color="orange")
    plt.ylim(bottom=Ymin, top=Ymax)
    plt.xlim(left=min(bet_axis), right=max(bet_axis))
    plt.title(f"Bet Analysis for Option: {bet_option}")
    plt.grid(which="both", linestyle="--", linewidth=0.5)

    image_path = os.path.join(RESOURCES_DIR, "bet_analysis.png")
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    plt.savefig(image_path, bbox_inches="tight")
    plt.close()
    return image_path


# ── Main betting routine ─────────────────────────────────────


def betting_function(ws: websocket.WebSocketApp, username: str, channel: str, kill_thread: threading.Event):
    if test_connection(ws) is False:
        return False

    end, contest_json = get_active_contest(channel.lower())
    contest_id_1 = contest_json["contest"]["_id"] if contest_json else None
    if contest_id_1 is None:
        return False
    log.info("[%s, %s] Contest found: https://streamelements.com/%s/contest/%s", channel, username, channel, contest_id_1)
    utils.sleep_until(end - datetime.timedelta(seconds=10), kill_thread=kill_thread)

    end, contest_json = get_active_contest(channel.lower())
    contest_id_2 = contest_json["contest"]["_id"] if contest_json else None
    if contest_id_2 is None or contest_id_1 != contest_id_2:
        return False
    options = {option["command"]: {"amount": int(option["totalAmount"]), "probability": None} for option in contest_json["contest"]["options"]}
    utils.compute_probabilities(channel, options)
    if any(option["probability"] is None for option in options.values()):
        for option in options.values():
            option["probability"] = 1 / len(options)
    balance = utils.get_balance(channel, username)
    utils.sleep_until(end - datetime.timedelta(seconds=get_variable_delay()), kill_thread=kill_thread)

    end, contest_json = get_active_contest(channel.lower())
    contest_id_3 = contest_json["contest"]["_id"] if contest_json else None
    if contest_id_3 is None or contest_id_1 != contest_id_3:
        return False
    for option in contest_json["contest"]["options"]:
        options[option["command"]]["amount"] = int(option["totalAmount"])

    log.info("[%s, %s] Final options before betting: %s", channel, username, options)
    time_left = (end - datetime.datetime.now()).total_seconds()
    if time_left > 5:
        return False
    elif 0 > time_left > -5:
        change_variable_delay((DELAY_GOAL - time_left))
        add_telegram_log(f"Betting {round(-time_left, 2)} seconds late\n")
        send_telegram_log()
        return False
    elif 5 > time_left > 0:
        bet_option, bet_amount = optimal_bet(options)
        min_bet, max_bet = contest_json["contest"]["minBet"], contest_json["contest"]["maxBet"]

        if bet_option is None or bet_amount < 0:
            bet_amount = 0
        elif 0 <= bet_amount < min_bet:
            bet_amount = min_bet
        elif bet_amount > max_bet:
            bet_amount = max_bet
        else:
            bet_amount = round(bet_amount * 2, -2) // 2

        if bet_amount > balance:
            bet_amount = balance
            bet_str = "all"
        else:
            bet_str = str(bet_amount)

        if bet_amount >= min_bet:
            ws.send(f"PRIVMSG #{channel.lower()} :!bet {bet_option} {bet_str.replace('.0', '')}")

        time_left = (end - datetime.datetime.now()).total_seconds()
        change_variable_delay((DELAY_GOAL - time_left) / 4)
        send_telegram_log()

        telegram_message = ""
        telegram_message += f"[{channel}, {username}] Betting with {round(time_left, 2)} seconds left\n"
        if bet_amount > 0:
            pot_ratio, bet_profit, bet_odd = bet_stats(options, bet_option, bet_amount)
            telegram_message += f"https://streamelements.com/{channel}/contest/{contest_json['contest']['_id']}\n"
            for key, option in options.items():
                telegram_message += f"{key}: {json.dumps(option, indent=4)}\n"
            telegram_message += f"Bet {bet_str} on {bet_option} ({pot_ratio * 100:.2f}% of the pot)\n"
            telegram_message += f"Win probability: {options[bet_option]['probability'] * 100:.2f}%\n"
            telegram_message += f"Profits {bet_profit:.0f} points ({bet_odd:.2f}x)\n\n"
        else:
            pot_ratio, bet_profit, bet_odd = bet_stats(options, bet_option, bet_amount)
            telegram_message += f"https://streamelements.com/{channel}/contest/{contest_json['contest']['_id']}\n"
            for key, option in options.items():
                telegram_message += f"{key}: {json.dumps(option, indent=4)}\n"
            telegram_message += f"Skipping bet (optimal bet:{bet_amount})\n"

        if all(amount["amount"] != 0 for amount in options.values()):
            image_path = bet_analysis(options, bet_option, bet_amount)
            send_image_threaded(image_path, caption=telegram_message)
        else:
            send_message_threaded(telegram_message)

    return True
