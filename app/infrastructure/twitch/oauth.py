"""Twitch OAuth device flow and token storage (``data/oauth.json``).

Used at startup so IRC/WebSocket clients can authenticate; not StreamElements-specific.
"""
import json
import os
import time

import requests

import paths
from app.infrastructure.http import twitch as twitch_http
from logging_config import setup_logging

log = setup_logging("twitch.oauth")
OAUTH_FILE = paths.OAUTH_FILE


def set_oauth_token(oauth: dict, username: str):
    response = twitch_http.device_flow_start()
    log.info("%s's Oauth_key: %s", username, response.json()["verification_uri"])
    device_code = response.json()["device_code"]
    while True:
        try:
            new_response = twitch_http.device_flow_poll(device_code)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            log.warning("Twitch OAuth request error for %s: %s; retrying in 5s", username, e)
            time.sleep(5)
            continue
        log.debug("%s %s", new_response.status_code, new_response.json())
        if new_response.status_code == 200:
            oauth[username] = new_response.json()["access_token"]
            os.makedirs(os.path.dirname(OAUTH_FILE), exist_ok=True)
            with open(OAUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(oauth, f)
            return new_response.json()["access_token"]
        time.sleep(5)


def check_oauth_token(username):

    if not os.path.exists(OAUTH_FILE):
        oauth = {}
        log.info("Set %s's oauth token", username)
        return set_oauth_token(oauth, username)

    with open(OAUTH_FILE, "r", encoding="utf-8") as f:
        oauth = json.load(f)
        if username not in oauth:
            return set_oauth_token(oauth, username)

        response = twitch_http.validate_token(oauth[username])
        if response.status_code == 200:
            log.info("%s's oauth token is valid", username)
            return oauth[username]
        else:
            log.info("%s's oauth token is invalid", username)
            return set_oauth_token(oauth, username)
