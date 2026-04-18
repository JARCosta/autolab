"""Outbound HTTP client for the StreamElements kappa API (points, contests)."""

import requests

_BASE = "https://api.streamelements.com/kappa/v2"


def get_points(channel_id: str, username: str, *, timeout: float = 30) -> requests.Response:
    return requests.get(
        f"{_BASE}/points/{channel_id}/{username.lower()}",
        timeout=timeout,
    )


def get_active_contest(channel_id: str, *, timeout: float = 10) -> requests.Response:
    return requests.get(f"{_BASE}/contests/{channel_id}/active", timeout=timeout)


def get_contest(channel_id: str, contest_id: str, *, timeout: float = 10) -> requests.Response:
    return requests.get(f"{_BASE}/contests/{channel_id}/{contest_id}", timeout=timeout)
