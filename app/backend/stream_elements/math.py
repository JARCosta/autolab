"""Optimal bet math and optional matplotlib analysis chart."""

import datetime
import json
import os
import threading
import traceback
from math import sqrt

import matplotlib.pyplot as plt
import numpy as np
import websocket

import paths
from app.backend.notifications import (send_image_threaded, send_message,
                                       send_message_threaded)
from logging_config import setup_logging

from . import local_state, se_helpers

log = setup_logging("stream_elements.odds")

RESOURCES_DIR = paths.STREAMELEMENTS_RESOURCES_DIR



#region Betting Function
def betting_function(ws: websocket.WebSocketApp, username: str, channel: str, kill_thread: threading.Event):
    if se_helpers.test_connection(ws) is False:
        return False

    end, contest_json = se_helpers.get_active_contest(channel.lower())
    contest_id_1 = contest_json["contest"]["_id"] if contest_json else None
    if contest_id_1 is None:
        return False
    log.info(
        "[%s, %s] Contest found: https://streamelements.com/%s/contest/%s",
        channel,
        username,
        channel,
        contest_id_1,
    )
    se_helpers.sleep_until(end - datetime.timedelta(seconds=10), kill_thread=kill_thread)

    end, contest_json = se_helpers.get_active_contest(channel.lower())
    contest_id_2 = contest_json["contest"]["_id"] if contest_json else None
    if contest_id_2 is None or contest_id_1 != contest_id_2:
        return False
    options = {
        option["command"]: {"amount": int(option["totalAmount"]), "probability": None}
        for option in contest_json["contest"]["options"]
    }
    # TODO: Re-enable this when Faceit API is fixed
    # se_helpers.compute_probabilities(channel, options)
    if any(option["probability"] is None for option in options.values()):
        for option in options.values():
            option["probability"] = 1 / len(options)
    balance = se_helpers.fetch_balance(channel, username)
    se_helpers.sleep_until(
        end - datetime.timedelta(seconds=local_state.get_variable_delay()),
        kill_thread=kill_thread,
    )

    end, contest_json = se_helpers.get_active_contest(channel.lower())
    contest_id_3 = contest_json["contest"]["_id"] if contest_json else None
    if contest_id_3 is None or contest_id_1 != contest_id_3:
        return False
    for option in contest_json["contest"]["options"]:
        options[option["command"]]["amount"] = int(option["totalAmount"])

    log.info("[%s, %s] Final options before betting: %s", channel, username, options)
    time_left = (end - datetime.datetime.now()).total_seconds()
    if time_left > 5:
        return False
    if 0 > time_left > -5:
        local_state.change_variable_delay((local_state.DELAY_GOAL - time_left))
        send_message(f"Betting {round(-time_left, 2)} seconds late\n", log=True)
        return False
    if 5 > time_left > 0:
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
        local_state.change_variable_delay((local_state.DELAY_GOAL - time_left) / 4)

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
            image_path = bet_graph(options, bet_option, bet_amount)
            send_image_threaded(image_path, caption=telegram_message)
        else:
            send_message_threaded(telegram_message)

    return True

# region Betting Math
def optimal_bet(options: dict) -> tuple[str | None, int]:
    options_amounts = {option: option_data["amount"] for option, option_data in options.items()}

    if all(data["probability"] is not None for data in options.values()):
        options_probabilities = {option: option_data["probability"] for option, option_data in options.items()}
    elif all(data["probability"] is None for data in options.values()):
        options_probabilities = {option: 1 / len(options) for option in options.keys()}
    else:
        send_message_threaded(f"Error calculating optimal bet: Incomplete probabilities data\nOptions: {options}", notification=True)
        options_probabilities = {option: 1 / len(options) for option in options.keys()}

    sum_of_amounts = sum(options_amounts.values())

    no_bet_options = [option for option, amount in options_amounts.items() if amount == 0]
    if sum_of_amounts < 500:
        return None, 0
    if len(no_bet_options) > 0:
        max_probability_no_bet_option = max(no_bet_options, key=lambda option: options_probabilities[option])
        return max_probability_no_bet_option, 0

    expected_returns = {
        option: sum(options_amounts.values()) / amount * options_probabilities[option]
        for option, amount in options_amounts.items()
    }
    best_option = max(expected_returns, key=lambda opt: expected_returns[opt])
    if expected_returns[best_option] <= 1.0:
        return None, 0

    Ba = options_amounts[best_option]
    Oa = sum(options_amounts.values()) - Ba
    Bp = options_probabilities[best_option]
    optimal_bet_amount = -Ba + sqrt((Bp * Ba * Oa) / (1 / 1))

    log.info("Optimal bet for option '%s': %.2f points", best_option, optimal_bet_amount)
    return best_option, optimal_bet_amount

#region Statistics and Analysis
def bet_stats(options: dict, bet_option: str | None, bet_amount: float) -> tuple[float, float, float]:
    b = bet_amount
    if bet_option is None or bet_amount <= 0:
        return 0.0, 0.0, 0.0
    Ba = options[bet_option]["amount"]
    Oa = sum(option["amount"] for option in options.values()) - Ba
    pot_ratio = b / (Ba + b) if (Ba + b) > 0 else 0
    bet_profit = pot_ratio * Oa
    bet_odd = (b + bet_profit) / b if b > 0 else 0
    return pot_ratio, bet_profit, bet_odd


def bet_graph(options: dict, bet_option: str, bet_amount: float) -> str:
    try:
        Ba = options[bet_option]["amount"]
    except KeyError as exc:
        raise KeyError(f"Error accessing bet option data: {traceback.format_exc()}") from exc
    Bp = options[bet_option]["probability"]
    Oa = sum(option["amount"] for option in options.values()) - Ba

    xmin, xmax = -Ba, Oa * 1.2
    ymin, ymax = -Ba, Oa * 1.2

    versions = {"1.1": [], "2.0": [], "2.2": []}
    bet_axis = np.linspace(xmin, xmax, 500)
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
        version_indexes = max(i for (i, val) in enumerate(version_list) if ymin < val < ymax)
        plt.text(
            bet_axis[version_indexes],
            version_list[version_indexes],
            f"Risk v{version}",
            color="darkgray",
            va="bottom",
            ha="right",
        )

    plt.axvline(x=bet_amount, color="red")
    plt.axhline(y=Oa, color="orange")
    plt.text(bet_axis[0], Oa * 0.95, [option for option in options if option != bet_option], color="orange")
    plt.ylim(bottom=ymin, top=ymax)
    plt.xlim(left=min(bet_axis), right=max(bet_axis))
    plt.title(f"Bet Analysis for Option: {bet_option}")
    plt.grid(which="both", linestyle="--", linewidth=0.5)

    image_path = os.path.join(RESOURCES_DIR, "bet_analysis.png")
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    plt.savefig(image_path, bbox_inches="tight")
    plt.close()
    return image_path
