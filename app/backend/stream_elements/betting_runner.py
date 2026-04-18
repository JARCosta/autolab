"""Main contest → sleep → bet workflow (Twitch `!bet` command)."""

import datetime
import json
import threading
import time

import websocket
from logging_config import setup_logging

from app.backend.notifications import (
    add_telegram_log,
    send_image_threaded,
    send_message_threaded,
    send_telegram_log,
)

from . import contests, local_state, odds, se_helpers

log = setup_logging("stream_elements.betting_runner")


def betting_function(ws: websocket.WebSocketApp, username: str, channel: str, kill_thread: threading.Event):
    if contests.test_connection(ws) is False:
        return False

    end, contest_json = contests.get_active_contest(channel.lower())
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

    end, contest_json = contests.get_active_contest(channel.lower())
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

    end, contest_json = contests.get_active_contest(channel.lower())
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
        add_telegram_log(f"Betting {round(-time_left, 2)} seconds late\n")
        send_telegram_log()
        return False
    if 5 > time_left > 0:
        bet_option, bet_amount = odds.optimal_bet(options)
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
        send_telegram_log()

        telegram_message = ""
        telegram_message += f"[{channel}, {username}] Betting with {round(time_left, 2)} seconds left\n"
        if bet_amount > 0:
            pot_ratio, bet_profit, bet_odd = odds.bet_stats(options, bet_option, bet_amount)
            telegram_message += f"https://streamelements.com/{channel}/contest/{contest_json['contest']['_id']}\n"
            for key, option in options.items():
                telegram_message += f"{key}: {json.dumps(option, indent=4)}\n"
            telegram_message += f"Bet {bet_str} on {bet_option} ({pot_ratio * 100:.2f}% of the pot)\n"
            telegram_message += f"Win probability: {options[bet_option]['probability'] * 100:.2f}%\n"
            telegram_message += f"Profits {bet_profit:.0f} points ({bet_odd:.2f}x)\n\n"
        else:
            pot_ratio, bet_profit, bet_odd = odds.bet_stats(options, bet_option, bet_amount)
            telegram_message += f"https://streamelements.com/{channel}/contest/{contest_json['contest']['_id']}\n"
            for key, option in options.items():
                telegram_message += f"{key}: {json.dumps(option, indent=4)}\n"
            telegram_message += f"Skipping bet (optimal bet:{bet_amount})\n"

        if all(amount["amount"] != 0 for amount in options.values()):
            image_path = odds.bet_analysis(options, bet_option, bet_amount)
            send_image_threaded(image_path, caption=telegram_message)
        else:
            send_message_threaded(telegram_message)

    return True
