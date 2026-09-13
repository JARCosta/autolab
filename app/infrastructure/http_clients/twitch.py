# app/infrastructure/http/twitch.py

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import requests

_OAUTH_URL = "https://id.twitch.tv/oauth2"
_GQL_URL = "https://gql.twitch.tv/gql"



def _client_id() -> str:
    client_id = os.getenv("TWITCH_CLIENT_ID")
    if not client_id:
        raise RuntimeError("TWITCH_CLIENT_ID is not set")
    return client_id


def device_flow_start(scopes: list[str] | None = None) -> requests.Response:
    scope_value = " ".join(scopes or ["chat:read", "chat:edit"])
    return requests.post(
        f"{_OAUTH_URL}/device",
        data={"client_id": _client_id(), "scopes": scope_value},
        timeout=10,
    )


def device_flow_poll(device_code: str) -> requests.Response:
    return requests.post(
        f"{_OAUTH_URL}/token",
        data={
            "client_id": _client_id(),
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
        timeout=10,
    )


def validate_token(access_token: str) -> requests.Response:
    response = requests.get(
        f"{_OAUTH_URL}/validate",
        headers={"Authorization": f"OAuth {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response


@lru_cache(maxsize=256)
def client_id_for_token(access_token: str) -> str:
    response = validate_token(access_token)
    client_id = response.json().get("client_id")
    if not client_id:
        raise RuntimeError("Twitch token validation did not return a client_id")
    return str(client_id)


def fetch_live_broadcast(
    channel_login: str,
    access_token: str,
) -> dict[str, Any] | None:
    client_id = client_id_for_token(access_token)
    response = requests.post(
        _GQL_URL,
        json=[{
            "operationName": "UseLiveBroadcast",
            "variables": {"channelLogin": channel_login},
            "query": "query UseLiveBroadcast($channelLogin: String!) { user(login: $channelLogin) { stream { id createdAt } } }",
        }],
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()[0].get("data", {})
    user = data.get("user") or {}
    return user.get("stream")


def is_channel_live(
    channel_login: str,
    access_token: str,
) -> bool:
    return fetch_live_broadcast(channel_login, access_token) is not None
