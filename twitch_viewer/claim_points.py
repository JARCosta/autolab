#!/usr/bin/env python3
from __future__ import annotations

import time
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
import uuid
from typing import Any

import requests

from stream_elements.oauth import check_oauth_token

GQL_ENDPOINT = "https://gql.twitch.tv/gql"
# This is the client id used by twitch.tv web; it is widely used for GQL calls.
TWITCH_WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

# Persisted query hash observed for ChannelPointsContext (see twitch_viewer/main.py).
PERSISTED_SHA_CHANNEL_POINTS_CONTEXT = "7fe050e3761eb2cf258d70ee1a21cbd76fa8cf3d7e7b12fc437e7029d446b5e3"


class TwitchError(RuntimeError):
    pass


@dataclass(frozen=True)
class TwitchSession:
    oauth_token: str
    client_session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    device_id: str = field(
        default_factory=lambda: (uuid.uuid4().hex + uuid.uuid4().hex)[:32]
    )
    client_version: str = "f0040d55-508e-4560-87be-0bded650b13c"

    def headers(self) -> dict[str, str]:
        user_agent = os.environ.get(
            "TWITCH_CLAIM_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )

        cookie_override = os.environ.get("TWITCH_CLAIM_COOKIE_HEADER", "").strip()
        cookie_header = cookie_override if cookie_override else f"auth-token={self.oauth_token}"

        client_session_id = os.environ.get("TWITCH_CLIENT_SESSION_ID", self.client_session_id)
        device_id = os.environ.get("TWITCH_X_DEVICE_ID", self.device_id)
        client_version = os.environ.get("TWITCH_CLIENT_VERSION", self.client_version)

        return {
            "authority": "gql.twitch.tv",
            "Authorization": f"OAuth {self.oauth_token}",
            "Client-Id": TWITCH_WEB_CLIENT_ID,
            # Twitch web sends this as text/plain with a JSON string body.
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Origin": "https://www.twitch.tv",
            "Referer": "https://www.twitch.tv/",
            "User-Agent": user_agent,
            # Web-client identity headers (case-insensitive).
            "client-session-id": client_session_id,
            "x-device-id": device_id,
            "client-version": client_version,
            # Required for Twitch "integrity" challenge on web GraphQL.
            # Copy this from the browser's successful ClaimCommunityPoints request headers.
            "client-integrity": os.environ.get("TWITCH_CLIENT_INTEGRITY", ""),
            # Some integrity checks expect auth-token cookie as well.
            "Cookie": cookie_header,
            # Web-client fidelity headers (best-effort defaults; can be overridden).
            "accept-language": os.environ.get("TWITCH_CLAIM_ACCEPT_LANGUAGE", "en-US"),
            "sec-fetch-mode": os.environ.get("TWITCH_CLAIM_SEC_FETCH_MODE", "cors"),
            "sec-fetch-site": os.environ.get("TWITCH_CLAIM_SEC_FETCH_SITE", "same-site"),
            "sec-fetch-dest": os.environ.get("TWITCH_CLAIM_SEC_FETCH_DEST", "empty"),
            "priority": os.environ.get("TWITCH_CLAIM_PRIORITY", "u=1, i"),
            "accept-encoding": os.environ.get(
                "TWITCH_CLAIM_ACCEPT_ENCODING", "gzip, deflate, br, zstd"
            ),
            "sec-ch-ua": os.environ.get(
                "TWITCH_CLAIM_SEC_CH_UA",
                '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
            ),
            "sec-ch-ua-mobile": os.environ.get("TWITCH_CLAIM_SEC_CH_UA_MOBILE", "?0"),
            "sec-ch-ua-platform": os.environ.get(
                "TWITCH_CLAIM_SEC_CH_UA_PLATFORM", '"Windows"'
            ),
        }


def twitch_validate_token(sess: TwitchSession) -> dict[str, Any]:
    r = requests.get(
        "https://id.twitch.tv/oauth2/validate",
        headers={"Authorization": f"OAuth {sess.oauth_token}"},
        timeout=15,
    )
    if r.status_code != 200:
        raise TwitchError(f"Token validate failed ({r.status_code}): {r.text}")
    return r.json()


@lru_cache(maxsize=32)
def _client_id_for_token(oauth_token: str) -> str:
    r = requests.get(
        "https://id.twitch.tv/oauth2/validate",
        headers={"Authorization": f"OAuth {oauth_token}"},
        timeout=15,
    )
    if r.status_code != 200:
        raise TwitchError(f"Token validate failed ({r.status_code}): {r.text}")
    data = r.json()
    client_id = data.get("client_id")
    if not client_id:
        raise TwitchError(f"Token validate missing client_id: {data}")
    return str(client_id)


def gql_call(sess: TwitchSession, payload: Any) -> Any:
    # Twitch web sends a JSON body as *text/plain* (not application/json).
    body = json.dumps(payload, separators=(",", ":"))
    r = requests.post(GQL_ENDPOINT, headers=sess.headers(), data=body, timeout=20)
    if r.status_code != 200:
        raise TwitchError(f"GQL HTTP {r.status_code}: {r.text}")
    try:
        data = r.json()
    except ValueError as e:
        ct = r.headers.get("content-type", "")
        snippet = r.text[:250] if r.text else ""
        raise TwitchError(
            f"GQL returned non-JSON (captcha?): content-type={ct} body_snippet={snippet!r}"
        ) from e
    if isinstance(data, list):
        # Some GQL calls return a list; bubble up any error.
        for item in data:
            if isinstance(item, dict) and item.get("errors"):
                raise TwitchError(
                    f"GQL errors: {item.get('errors')} response={json.dumps(item)[:800]}"
                )
    elif isinstance(data, dict) and data.get("errors"):
        raise TwitchError(
            f"GQL errors: {data.get('errors')} response={json.dumps(data)[:800]}"
        )
    return data


def gql_get_user_id_from_login(sess: TwitchSession, login: str) -> str | None:
    payload = {
        "operationName": "GetIDFromLogin",
        "variables": {"login": login},
        "extensions": {
            "persistedQuery": {
                "version": 1,
                # Persisted hash appears in twitch_viewer/main.py comments.
                "sha256Hash": "94e82a7b1e3c21e186daa73ee2afc4b8f23bade1fbbff6fe8ac133f50a2f58ca",
            }
        },
    }
    data = gql_call(sess, payload)
    user = (data.get("data") or {}).get("user")
    if user is None:
        return None
    if not isinstance(user, dict):
        raise TwitchError(f"Unexpected GetIDFromLogin response: {data}")
    user_id = user.get("id")
    if not user_id:
        return None
    return user_id


def gql_channel_points_context(sess: TwitchSession, channel_login: str) -> dict[str, Any]:
    payload = {
        "operationName": "ChannelPointsContext",
        "variables": {"channelLogin": channel_login, "includeGoalTypes": ["CREATOR", "BOOST"]},
        "extensions": {
            "persistedQuery": {"version": 1, "sha256Hash": PERSISTED_SHA_CHANNEL_POINTS_CONTEXT}
        },
    }
    data = gql_call(sess, payload)
    try:
        return data["data"]["community"]["channel"]["self"]["communityPoints"]
    except Exception as e:
        raise TwitchError(f"Unexpected ChannelPointsContext response: {data}") from e


def gql_claim_points(sess: TwitchSession, channel_id: str, claim_id: str) -> dict[str, Any]:
    # This mutation name is used by the twitch web client.
    # SHA discovered from your browser request payload:
    # extensions.persistedQuery.sha256Hash
    default_sha = "46aaeebe02c99afdf4fc97c7c0cba964124bf6b0af229395f1f6d1feed05b3d0"
    sha = os.environ.get("TWITCH_CLAIM_COMMUNITYPOINTS_SHA256", default_sha)
    retry_no_persisted = os.environ.get("TWITCH_CLAIM_RETRY_NO_PERSISTED", "0") == "1"

    payload = {
        "operationName": "ClaimCommunityPoints",
        "variables": {"input": {"channelID": channel_id, "claimID": claim_id}},
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": sha,
            }
        },
    }
    try:
        data = gql_call(sess, [payload])
    except TwitchError as e:
        if "PersistedQueryNotFound" in str(e):
            if not retry_no_persisted:
                raise TwitchError(
                    "PersistedQueryNotFound for ClaimCommunityPoints. "
                    "Set TWITCH_CLAIM_COMMUNITYPOINTS_SHA256 to the correct sha256Hash."
                ) from e
            payload_no_persisted = {
                "operationName": "ClaimCommunityPoints",
                "variables": {"input": {"channelID": channel_id, "claimID": claim_id}},
            }
            data = gql_call(sess, [payload_no_persisted])
        else:
            raise
    try:
        # Twitch sometimes returns an array of payload objects.
        if isinstance(data, list):
            if not data:
                raise TwitchError("ClaimCommunityPoints returned empty response list")
            data = data[0]
        return data["data"]["claimCommunityPoints"]
    except Exception as e:
        raise TwitchError(f"Unexpected ClaimCommunityPoints response: {data}") from e


def channel_points_bonus_snapshot(sess: TwitchSession, channel_login: str) -> dict[str, Any]:
    """
    GQL ChannelPointsContext summary for logging (availableClaim vs passive balance).
    """
    channel_login = channel_login.strip().lstrip("@")
    if not channel_login:
        raise TwitchError("Missing channel login.")
    ctx = gql_channel_points_context(sess, channel_login)
    claim = ctx.get("availableClaim") or {}
    claim_id = claim.get("id")
    bonus_points = claim.get("points")
    return {
        "balance": ctx.get("balance"),
        "has_bonus": bool(claim_id),
        "claim_id": str(claim_id) if claim_id else None,
        "bonus_points": int(bonus_points) if bonus_points is not None else None,
    }


def _extract_claim_info(points_ctx: dict[str, Any]) -> tuple[int | None, str | None]:
    """
    Returns (available_points, claim_id) if claim is available, else (None, None).
    """
    claim = points_ctx.get("availableClaim")
    if not claim:
        return None, None
    claim_id = claim.get("id")
    points = claim.get("points")
    # Some responses provide `id` but omit `points`; we can still claim using `claim_id`.
    if not claim_id:
        return None, None
    if points is None:
        return None, str(claim_id)
    return int(points), str(claim_id)


def build_session(username: str) -> TwitchSession:
    if not username:
        raise TwitchError("Missing username.")
    token = check_oauth_token(username)
    sess = TwitchSession(oauth_token=token)
    twitch_validate_token(sess)
    return sess


def claim_points_once(sess: TwitchSession, channel_login: str) -> dict[str, Any]:
    channel_login = channel_login.strip().lstrip("@")
    if not channel_login:
        raise TwitchError("Missing channel login.")

    channel_id = gql_get_user_id_from_login(sess, channel_login)
    if not channel_id:
        return {
            "claimed": False,
            "channel_login": channel_login,
            "channel_id": None,
            "balance": None,
            "available_points": None,
            "claim_id": None,
            "status": "CHANNEL_NOT_FOUND",
        }
    ctx = gql_channel_points_context(sess, channel_login)
    balance = ctx.get("balance")
    available_points, claim_id = _extract_claim_info(ctx)

    if not claim_id:
        return {
            "claimed": False,
            "channel_login": channel_login,
            "channel_id": channel_id,
            "balance": balance,
            "available_points": None,
            "claim_id": None,
            "status": "NO_BONUS",
        }

    result = gql_claim_points(sess, channel_id, claim_id)
    if result.get("status") != "CLAIMED":
        raise TwitchError(f"Claim did not succeed: {result}")
    return {
        "claimed": True,
        "channel_login": channel_login,
        "channel_id": channel_id,
        "balance": balance,
        "available_points": available_points,
        "claim_id": claim_id,
        "new_balance": result.get("newBalance"),
        "status": result.get("status"),
    }


def is_channel_live(sess: TwitchSession, channel_login: str) -> bool:
    channel_login = channel_login.strip().lstrip("@")
    if not channel_login:
        raise TwitchError("Missing channel login.")
    helix_client_id = _client_id_for_token(sess.oauth_token)
    response = requests.get(
        "https://api.twitch.tv/helix/streams",
        params={"user_login": channel_login},
        headers={
            "Authorization": f"Bearer {sess.oauth_token}",
            "Client-Id": helix_client_id,
            "Accept": "application/json",
        },
        timeout=15,
    )
    if response.status_code == 200:
        payload = response.json()
        data = payload.get("data") or []
        if data:
            return True

    # Fallback to Twitch web GQL stream state used by the site itself.
    payload = {
        "operationName": "VideoPlayerStatusOverlayChannel",
        "variables": {"channel": channel_login},
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "938d155c890df88b5da53592e327d36ae9b851d2ee38bdb13342a1402fc24ad2",
            }
        },
    }
    data = gql_call(sess, payload)
    data_root = data.get("data") or {}
    user = data_root.get("user") or {}
    if not isinstance(user, dict):
        return False
    stream = user.get("stream")
    return bool(stream)


def claim_points_loop(
    sess: TwitchSession, channel_login: str, interval_seconds: int = 60
) -> None:
    if interval_seconds < 10:
        raise TwitchError("interval_seconds must be >= 10.")
    while True:
        claim_points_once(sess, channel_login)
        time.sleep(interval_seconds)