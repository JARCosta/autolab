"""Twitch OAuth device-flow service using storage-backed token persistence."""

from __future__ import annotations

import time

import requests

from app.infrastructure.http import twitch as twitch_http
from app.infrastructure.storage.twitch_oauth.repository import (
    load_oauth_tokens,
    save_oauth_tokens,
)
from logging_config import setup_logging

log = setup_logging("twitch.oauth")


def set_oauth_token(oauth: dict[str, str], username: str) -> str:
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
            save_oauth_tokens(oauth)
            return new_response.json()["access_token"]
        time.sleep(5)


def check_oauth_token(username: str) -> str:
    oauth = load_oauth_tokens()
    if username not in oauth:
        log.info("Set %s's oauth token", username)
        return set_oauth_token(oauth, username)

    response = twitch_http.validate_token(oauth[username])
    if response.status_code == 200:
        log.info("%s's oauth token is valid", username)
        return oauth[username]

    log.info("%s's oauth token is invalid", username)
    return set_oauth_token(oauth, username)

