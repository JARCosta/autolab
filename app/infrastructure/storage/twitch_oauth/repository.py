"""Persistence helpers for Twitch OAuth tokens in ``data/oauth.json``."""

from __future__ import annotations

import json
import os

import paths


def load_oauth_tokens() -> dict[str, str]:
    try:
        with open(paths.OAUTH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return {}


def save_oauth_tokens(tokens: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(paths.OAUTH_FILE), exist_ok=True)
    with open(paths.OAUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f)

