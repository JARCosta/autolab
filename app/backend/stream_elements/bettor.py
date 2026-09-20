"""Bettor module to connect to Twitch IRC and handle betting events."""
import threading
import time
import traceback
from contextlib import suppress

import numpy as np
import requests
import websocket
from websocket._exceptions import WebSocketConnectionClosedException

from app.backend.notifications import send_message
from app.infrastructure.http_clients.twitch import is_channel_live
from app.infrastructure.storage.balances_db import fetch_and_store_balance
from logging_config import setup_logging

from .local_state import (change_variable_delay, contest_to_bet, get_last_bet,
                          save_last_bet)
from .math import bet_stats, betting_function
from .se_helpers import get_active_contest
from .twitch_chat import (check_if_mentioned, get_message_frequency,
                          is_message_on_cooldown, parse_twitch_message,
                          set_sent_message_timestamp)

log = setup_logging("bettor")


def _send_live_status_notification(channel: str, is_live: bool) -> None:
    state = "live" if is_live else "offline"
    log.info(f"Twitch channel {channel} is now {state}.")
    send_message(
        f"Twitch channel is now {state}.",
        log=True,
        notification=is_live,
        source=f"{channel}",
    )



class Bettor:

    def __init__(self, channel: str, username: str, oauth_key: str, kill_event: threading.Event, is_bettor: bool = False, is_repeater: bool = False):
        self.channel = channel
        self.username = username
        self.oauth_key = oauth_key
        self.ready = threading.Event()
        self.kill_event = kill_event
        self.is_bettor = is_bettor
        self.is_repeater = is_repeater
        self.last_contest = None
        self.is_connected = False
        self.ws: websocket.WebSocketApp = None
        self.wst: threading.Thread = None

    def run_ws(self, websocket_url):
        self.ws = websocket.WebSocketApp(
            websocket_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_open=self._on_open,
        )
        self.wst = threading.Thread(target=self.ws.run_forever)
        self.wst.daemon = True
        self.wst.start()
        return self.ws, self.wst


    def connect(self) -> bool:
        """Establish WebSocket connection to Twitch IRC."""
        try:
            self.ws, self.wst = self.run_ws(websocket_url="wss://irc-ws.chat.twitch.tv/")

            # Wait for connection to be established
            self.ready.wait(timeout=30)
            self.is_connected = True

            if self.is_bettor:
                _, contest = get_active_contest(self.channel)
                if contest:
                    self.last_contest = contest

            return True
        except Exception as e:
            log.error(f"Failed to connect to Twitch: {e}")
            send_message(f"Failed to connect to Twitch: {traceback.format_exc()}", log=True, notification=True, source=f"{self.username}({self.channel})")
            return False

    def reconnect(self):
        """Reconnect to Twitch IRC."""
        if self.ws:
            websocket_url = self.ws.url
            self.ws.close()
            time.sleep(5)
            self.ws, self.wst = self.run_ws(websocket_url)
            self.ready.clear()
            self.is_connected = False
            return True
        return False

    def disconnect(self):
        """Close WebSocket connection gracefully."""
        send_message("Disconnecting from Twitch IRC", log=True, notification=False, source=f"{self.username}({self.channel})")
        log.info("[%s, %s] Disconnecting from Twitch IRC", self.channel, self.username)
        if self.ws and self.is_connected:
            self.ws.close()
            self.wst.join(timeout=10)
            self.is_connected = False
            self.ready.clear()
            return True
        return False

    def _on_message(self, ws: websocket.WebSocketApp, message: str):
        def connect(ws: websocket.WebSocketApp, message: str):
            if ":Welcome, GLHF!" in message:
                ws.send(f"JOIN #{self.channel}")
            elif f"ROOMSTATE #{self.channel.lower()}" in message:
                send_message(f"{"Bettor" if self.is_bettor else "Viewer"} connected to Twitch IRC", log=True, notification=False, source=f"{self.username}({self.channel})")
                log.info("[%s, %s] %s connected", self.channel, self.username, "Bettor" if self.is_bettor else "Viewer")
                self.ready.set()
                self.is_connected = True
            elif ":tmi.twitch.tv RECONNECT" in message:
                self.is_connected = False
                self.reconnect()
                send_message("RECONNECT", log=True, notification=False, source=f"{self.username}({self.channel})")
            elif "PING :tmi.twitch.tv" in message:
                ws.send("PONG")
                ws.send("PING")
            elif ":Login authentication failed" in message:
                send_message(f"{self.__class__.__name__.capitalize()}: Invalid {self.username}'s OAuth key", notification=True, source=f"{self.username}({self.channel})")

        connect(ws, message)
        parsed = parse_twitch_message(message)
        if parsed is None or parsed["command"] != "PRIVMSG":
            return
        message_text = parsed["message"]
        sender = parsed["source"]["nick"]
        am_mentioned = check_if_mentioned(message_text, self.username)

        if sender.lower() != "streamelements" and sender.lower() != "nightbot":
            if am_mentioned:
                if self.username.lower() != "TopGdosKwanzas".lower():
                    send_message(f"{sender}: {message_text}", log=False, notification=True, source=f"{self.username}({self.channel})")
                return
            if self.is_repeater:
                message_frequency = get_message_frequency(self.channel, message_text)
                if message_frequency > 5 and not is_message_on_cooldown(self.channel, message_text):
                    send_message(f"High frequency message detected: {message_text}\n", log=True, notification=True, source=f"{self.username}({self.channel})")
                    ws.send(f"PRIVMSG #{self.channel.lower()} : {message_text}")
                    set_sent_message_timestamp(self.channel, message_text)
                return
            return

        if not self.is_bettor:
            return

        if am_mentioned:
            send_message(f"Mention: {sender}: {message_text}", source=f"{self.username}({self.channel})", log=False, notification=True)

        if "a new contest has started" in message_text:
            try:
                threading.Thread(target=betting_function, args=[ws, self.username, self.channel, self.kill_event]).start()
            except (OSError, RuntimeError, TypeError, ValueError, websocket.WebSocketException, KeyError):
                send_message(f"Error on betting thread:\n {traceback.format_exc()}", log=True, notification=True, source=f"{self.username}({self.channel})")

        elif "won the contest" in message_text:
            last_bet = get_last_bet(self.channel)
            if self.last_contest is None or last_bet is None or self.last_contest["contest"]["_id"] != last_bet["contest_id"]:
                return
            if message_text.split('"')[1].lower() == last_bet["bet_option"]:
                options = {option: {"amount": int(value), "probability": None} for option, value in last_bet["options"].items()}
                options[last_bet["bet_option"]]["amount"] -= last_bet["bet_amount"]
                _, bet_profit, bet_odd = bet_stats(options, last_bet["bet_option"], last_bet["bet_amount"])
                telegram_message = f"Won a bet of {last_bet['bet_amount']} points\n"
                telegram_message += f"Profit: {round(bet_profit, 3)} points at odd {round(bet_odd, 3)}\n"
            else:
                telegram_message = f"Lost a bet of {last_bet['bet_amount']} points\n"
            send_message(telegram_message, notification=True, source=f"{self.username}({self.channel})")
            self.last_contest = None
            # StreamElements has settled the contest; balance may have changed.
            with suppress(Exception):
                time.sleep(2)
                fetch_and_store_balance(self.channel, self.username)

        elif ", you have bet" in message_text: # anyone betting, not just the bettor
            user = message_text.lower().split(", you have bet ")[0][1:]
            bet_amount = int(message_text.lower().split("you have bet ")[1].split(" points")[0])
            bet_option = message_text.lower().split(" points on ")[1].split(".")[0]
            log.info("[%s, %s] %s: %s", self.channel, self.username, sender, message_text)
            if user.lower() == self.username.lower():
                time.sleep(10)
                _, contest = get_active_contest(self.channel.lower())
                if contest:
                    last_bet = contest_to_bet(contest, bet_option, bet_amount)
                    save_last_bet(self.channel, last_bet)
                # Bet placement normally changes the user's balance quickly.
                with suppress(Exception):
                    fetch_and_store_balance(self.channel, self.username)

        elif am_mentioned and ", there is no contest currently running" in message_text:
            telegram_message = f"Contest info: {sender}: {message_text}\n"
            end, _ = get_active_contest(self.channel)
            if end is None:
                telegram_message += "No active contest found.\n"
            else:
                telegram_message += f"Contest closed at {end}.\n"
            send_message(telegram_message, log=False, notification=True, source=f"{self.username}({self.channel})")
            change_variable_delay()

        elif "no longer accepting bets" in message_text:
            time.sleep(2)
            _, contest = get_active_contest(self.channel)
            if contest:
                self.last_contest = contest

        elif "won the giveaway" in message_text:
            if self.username.lower() in message_text.lower():
                send_message(f"Giveaway: {sender}: {message_text}", log=False, notification=True, source=f"{self.username}({self.channel})")
                time.sleep(np.random.uniform(5, 10))
                ws.send(f"PRIVMSG #{self.channel.lower()} : GG")
                time.sleep(np.random.uniform(3, 5))
                ws.send(f"PRIVMSG #{self.channel.lower()} : parece facil")

    def _on_error(self, _ws: websocket.WebSocketApp, error: str):
        log.error("%s", error)
        if isinstance(error, (WebSocketConnectionClosedException, TimeoutError)):
            send_message("Connection timeout.", log=True, notification=False, source=f"{self.username}({self.channel})")
            self.ws, self.wst = self.reconnect()
        elif isinstance(error, OSError) and error.errno == 113:
            send_message("No route to host.", log=True, notification=False, source=f"{self.username}({self.channel})")
            self.ws, self.wst = self.reconnect()
        else:
            send_message(f"Bettor Error: {traceback.format_exc()}", log=True, notification=True, source=f"{self.username}({self.channel})")
            log.error("%s", f"{self.username}({self.channel})")

    def _on_open(self, ws: websocket.WebSocketApp):
        ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
        ws.send(f"PASS oauth:{self.oauth_key}")
        ws.send(f"NICK {self.username}")
        ws.send(f"USER {self.username} 8 * :{self.username}")


def run_when_live(
    channel: str,
    username: str,
    oauth_key: str,
    kill_event: threading.Event,
    is_bettor: bool = False,
    is_repeater: bool = False,
):
    """Keep a Bettor session connected only while the Twitch channel is live."""

    last_live: bool | None = None
    bettor_instance = Bettor(channel, username, oauth_key, kill_event, is_bettor, is_repeater)
    while not kill_event.is_set():
        try:
            is_live = is_channel_live(channel.lower(), oauth_key)

            if is_live != last_live:
                _send_live_status_notification(channel, is_live=is_live)
                if is_live and not bettor_instance.is_connected:
                        bettor_instance.connect()
                elif not is_live and bettor_instance.is_connected:
                        bettor_instance.disconnect()
            last_live = is_live
        except requests.exceptions.ReadTimeout:
            log.error(f"Read timeout error on {username}({channel}).")
            send_message(f"Read timeout error.", log=True, notification=False, source=f"{username}({channel})")
        except requests.exceptions.ConnectionError:
            log.error(f"Connection error on {username}({channel}).")
            send_message(f"Connection error.", log=True, notification=False, source=f"{username}({channel})")
        except requests.exceptions.HTTPError:
            log.error(f"HTTP error on {username}({channel}).")
            send_message(f"HTTP error.", log=True, notification=False, source=f"{username}({channel})")
        except Exception as e:
            log.error(f"Bettor loop error for {channel}: {e}")
            send_message(f"Bettor error: {traceback.format_exc()}", log=True, notification=True, source=f"{username}({channel})")
        time.sleep(30)  # Check every 30 seconds
    return bettor_instance  # Return for potential reuse
