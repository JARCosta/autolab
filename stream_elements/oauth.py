"""OAuth handling for Twitch tokens used by StreamElements betting."""
import json
import os
import time

import requests

from logging_config import setup_logging
import paths

log = setup_logging("oauth")
OAUTH_FILE = paths.OAUTH_FILE


def set_oauth_token(oauth: dict, username: str):
    url = "https://id.twitch.tv/oauth2/device?client_id=kimne78kx3ncx6brgo4mv6wki5h1ko&scope=channel%3Amanage%3Apolls+channel%3Aread%3Apolls"
    response = requests.post(url, timeout=10)
    log.info("%s's Oauth_key: %s", username, response.json()["verification_uri"])
    while True:
        url = (
            "https://id.twitch.tv/oauth2/token?"
            "client_id=kimne78kx3ncx6brgo4mv6wki5h1ko&"
            "scope=channel%3Amanage%3Apolls+channel%3Aread%3Apolls&"
            f"device_code={response.json()['device_code']}&"
            "grant_type=urn:ietf:params:oauth:grant-type:device_code"
        )
        try:
            new_response = requests.post(url, timeout=15)
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
        log.info("Set %s's oauth token", username.upper())
        return set_oauth_token(oauth, username)

    with open(OAUTH_FILE, "r", encoding="utf-8") as f:
        oauth = json.load(f)
        if username not in oauth:
            return set_oauth_token(oauth, username)

        url = "https://id.twitch.tv/oauth2/validate"
        headers = {
            "Authorization": f"OAuth {oauth[username]}"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            log.info("%s's oauth token is valid", username.upper())
            return oauth[username]
        else:
            log.info("%s's oauth token is invalid", username.upper())
            return set_oauth_token(oauth, username)
