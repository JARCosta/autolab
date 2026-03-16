"""Bettor module to connect to Twitch IRC and handle betting events."""
import threading
import time
import traceback

import numpy as np
import websocket

from logging_config import setup_logging
from notifications import add_telegram_log, send_message, send_telegram_log
from stream_elements import betting, utils

log = setup_logging("bettor")


def run_ws(websocket_url, on_message, on_error, on_open):
    ws = websocket.WebSocketApp(
        websocket_url,
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
    )
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    return ws, wst


def reconnect_ws(ws: websocket.WebSocketApp):
    websocket_url = ws.url
    on_message = ws.on_message
    on_error = ws.on_error
    on_open = ws.on_open
    ws.close()
    time.sleep(5)
    return run_ws(websocket_url, on_message, on_error, on_open)


class Bettor:

    def __init__(self, channel: str, username: str, oauth_key: str, kill_event: threading.Event, bettor: bool = False, repeater: bool = False):
        self.channel = channel
        self.username = username
        self.oauth_key = oauth_key
        self.launched_event = threading.Event()
        self.kill_event = kill_event
        self.bettor = bettor
        self.repeater = repeater
        self.last_contest = None

        self.ws, self.wst = run_ws(
            websocket_url="wss://irc-ws.chat.twitch.tv/",
            on_message=self.on_message,
            on_error=self.on_error,
            on_open=self.on_open,
        )

        self.launched_event.wait()
        if self.bettor:
            try:
                betting.betting_function(self.ws, self.username, self.channel, self.kill_event)
            except Exception:
                send_message(traceback.format_exc(), notification=True)

            _, contest = betting.get_active_contest(self.channel)
            if contest:
                self.last_contest = contest
        try:
            self.kill_event.wait()
        except KeyboardInterrupt:
            pass

        self.ws.close()
        self.wst.join(2)

    def connect(self, ws: websocket.WebSocketApp, message: str):
        if ":Welcome, GLHF!" in message:
            ws.send(f"JOIN #{self.channel}")
        elif f"ROOMSTATE #{self.channel.lower()}" in message:
            log.info("[%s, %s] %s connected", self.channel, self.username, "Bettor" if self.bettor else "Viewer")
            self.launched_event.set()
        elif ":tmi.twitch.tv RECONNECT" in message:
            add_telegram_log(f"[{self.channel}, {self.username}] RECONNECT\n")
            self.ws, self.wst = reconnect_ws(self.ws)
        elif "PING :tmi.twitch.tv" in message:
            ws.send("PONG")
            ws.send("PING")
        elif ":Login authentication failed" in message:
            send_message(f"{self.__class__.__name__.capitalize()}: Invalid {self.username}'s OAuth key", notification=True)

    def on_message(self, ws: websocket.WebSocketApp, message: str):
        self.connect(ws, message)
        parsed = utils.parse_twitch_message(message)
        if parsed is None or parsed["command"] != "PRIVMSG":
            return
        message_text = parsed["message"]
        sender = parsed["source"]["nick"]
        mentioned = utils.check_if_mentioned(message_text, self.username)

        if sender.lower() != "streamelements" and sender.lower() != "nightbot":
            if mentioned:
                if self.username.lower() != "TopGdosKwanzas".lower():
                    send_message(f"[{self.channel}, {self.username}] {sender}: {message_text}", log=False, notification=True)
                return
            if self.repeater:
                message_frequency = utils.get_message_frequency(self.channel, message_text)
                if message_frequency > 5 and not utils.is_message_on_cooldown(self.channel, message_text):
                    send_message(f"[{self.channel}, {self.username}] High frequency message detected: {message_text}\n", notification=True)
                    ws.send(f"PRIVMSG #{self.channel.lower()} : {message_text}")
                    utils.set_sent_message_timestamp(self.channel, message_text)
                return
            return

        if not self.bettor:
            return

        if mentioned:
            time.sleep(1)
            send_message(f"[{self.channel}, {self.username}] {sender}: {message_text}")

        if "a new contest has started" in message_text:
            try:
                threading.Thread(target=betting.betting_function, args=[ws, self.username, self.channel, self.kill_event]).start()
            except Exception:
                send_message(f"[{self.channel}, {self.username}] Error on betting thread:\n {traceback.format_exc()}", notification=True)

        elif "won the contest" in message_text:
            last_bet = betting.get_last_bet(self.channel)
            if self.last_contest is None or last_bet is None or self.last_contest["contest"]["_id"] != last_bet["contest_id"]:
                return
            if message_text.split('"')[1].lower() == last_bet["bet_option"]:
                options = {option: {"amount": int(value), "probability": None} for option, value in last_bet["options"].items()}
                options[last_bet["bet_option"]]["amount"] -= last_bet["bet_amount"]
                _, bet_profit, bet_odd = betting.bet_stats(options, last_bet["bet_option"], last_bet["bet_amount"])
                telegram_message = f"Won a bet of {last_bet['bet_amount']} points\n"
                telegram_message += f"Profit: {round(bet_profit, 3)} points at odd {round(bet_odd, 3)}\n"
                send_telegram_log()
                send_message(telegram_message, notification=True)
            else:
                telegram_message = f"Lost a bet of {last_bet['bet_amount']} points\n"
                send_telegram_log()
                send_message(telegram_message, notification=True)
            self.last_contest = None

        elif ", you have bet" in message_text:
            user = message_text.lower().split(", you have bet ")[0][1:]
            bet_amount = int(message_text.lower().split("you have bet ")[1].split(" points")[0])
            bet_option = message_text.lower().split(" points on ")[1].split(".")[0]
            log.info("[%s, %s] %s: %s", self.channel, self.username, sender, message_text)
            if user.lower() == self.username.lower():
                time.sleep(10)
                _, contest = betting.get_active_contest(self.channel.lower())
                if contest:
                    last_bet = betting.contest_to_bet(contest, bet_option, bet_amount)
                    betting.save_last_bet(self.channel, last_bet)

        elif mentioned and ", there is no contest currently running" in message_text:
            telegram_message = f"[{self.channel}, {self.username}] {sender}: {message_text}\n"
            end, _ = betting.get_active_contest(self.channel)
            if end is None:
                telegram_message += "No active contest found.\n"
            else:
                telegram_message += f"Contest closed at {end}.\n"
            send_message(telegram_message, log=False, notification=True)
            betting.change_variable_delay()

        elif "no longer accepting bets" in message_text:
            time.sleep(2)
            _, contest = betting.get_active_contest(self.channel)
            if contest:
                self.last_contest = contest

        elif "won the giveaway" in message_text:
            if self.username.lower() in message_text.lower():
                send_message(f"[{self.channel}, {self.username}] {sender}: {message_text}", log=False, notification=True)
                time.sleep(np.random.uniform(5, 10))
                ws.send(f"PRIVMSG #{self.channel.lower()} : GG")
                time.sleep(np.random.uniform(3, 5))
                ws.send(f"PRIVMSG #{self.channel.lower()} : parece facil")

    def on_error(self, ws: websocket.WebSocketApp, error: str):
        log.error("%s", error)
        if isinstance(error, (websocket._exceptions.WebSocketConnectionClosedException, TimeoutError)):
            add_telegram_log(f"[{self.channel}, {self.username}] RECONNECT ({error})\n")
            self.ws, self.wst = reconnect_ws(self.ws)
        else:
            telegram_message = f"[{self.channel}, {self.username}] {traceback.format_exc()}\n"
            send_message(telegram_message, notification=True)
            log.error("%s", telegram_message)

    def on_open(self, ws: websocket.WebSocketApp):
        ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
        ws.send(f"PASS oauth:{self.oauth_key}")
        ws.send(f"NICK {self.username}")
        ws.send(f"USER {self.username} 8 * :{self.username}")
