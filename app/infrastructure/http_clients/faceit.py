"""Outbound HTTP client for FACEIT match APIs (same endpoints the web app uses)."""

import requests

_BASE_V1 = "https://www.faceit.com/api/match/v1"
_BASE_V2 = "https://www.faceit.com/api/match/v2"


def get_matches_group_by_state(faceit_user_id: str, *, timeout: float = 5) -> requests.Response:
    return requests.get(
        f"{_BASE_V1}/matches/groupByState?userId={faceit_user_id}",
        timeout=timeout,
    )


def get_match(match_id: str, *, timeout: float = 5) -> requests.Response:
    return requests.get(f"{_BASE_V2}/match/{match_id}", timeout=timeout)
