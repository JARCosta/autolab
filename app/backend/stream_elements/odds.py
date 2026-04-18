"""Optimal bet math and optional matplotlib analysis chart."""

import os
import traceback
from math import sqrt

import matplotlib.pyplot as plt
import numpy as np
from logging_config import setup_logging

import paths
from app.backend.notifications import send_message_threaded

log = setup_logging("stream_elements.odds")

RESOURCES_DIR = paths.STREAMELEMENTS_RESOURCES_DIR


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


def bet_analysis(options: dict, bet_option: str, bet_amount: float) -> str:
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
