"""OAuth handling for Twitch tokens used by StreamElements betting."""
import json
import os
import time

import requests

OAUTH_FILE = os.path.join("data", "oauth.json")


def set_oauth_token(oauth: dict, username: str):
    url = "https://id.twitch.tv/oauth2/device?client_id=kimne78kx3ncx6brgo4mv6wki5h1ko&scope=channel%3Amanage%3Apolls+channel%3Aread%3Apolls"
    response = requests.post(url, timeout=10)
    print(f"{username}'s Oauth_key:", response.json()["verification_uri"])
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
            print(f"Twitch OAuth request error for {username}: {e}; retrying in 5s")
            time.sleep(5)
            continue
        print(new_response.status_code, new_response.json())
        if new_response.status_code == 200:
            oauth[username] = new_response.json()["access_token"]
            os.makedirs(os.path.dirname(OAUTH_FILE), exist_ok=True)
            with open(OAUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(oauth, f)
            return new_response.json()["access_token"]
        time.sleep(5)


def check_oauth_token(username):
    try:
        with open(OAUTH_FILE, "r", encoding="utf-8") as f:
            oauth = json.load(f)
            if username not in oauth:
                return set_oauth_token(oauth, username)
            return oauth[username]
    except (FileNotFoundError, json.JSONDecodeError):
        oauth = {}
        print(f"Set {username.upper()}'s oauth token:")
        return set_oauth_token(oauth, username)
