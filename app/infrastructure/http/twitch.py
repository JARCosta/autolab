"""Outbound HTTP client for Twitch OAuth (device flow + token validation)."""

import requests

_BASE = "https://id.twitch.tv/oauth2"
_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
# channel:manage:polls + channel:read:polls
_SCOPE = "channel%3Amanage%3Apolls+channel%3Aread%3Apolls"


def device_flow_start(*, timeout: float = 10) -> requests.Response:
    url = f"{_BASE}/device?client_id={_CLIENT_ID}&scope={_SCOPE}"
    return requests.post(url, timeout=timeout)


def device_flow_poll(device_code: str, *, timeout: float = 15) -> requests.Response:
    url = (
        f"{_BASE}/token?"
        f"client_id={_CLIENT_ID}&"
        f"scope={_SCOPE}&"
        f"device_code={device_code}&"
        "grant_type=urn:ietf:params:oauth:grant-type:device_code"
    )
    return requests.post(url, timeout=timeout)


def validate_token(access_token: str, *, timeout: float = 10) -> requests.Response:
    headers = {"Authorization": f"OAuth {access_token}"}
    return requests.get(f"{_BASE}/validate", headers=headers, timeout=timeout)
