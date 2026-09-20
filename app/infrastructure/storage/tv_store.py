"""Persistent storage for saved iframe-based livestream entries."""

from __future__ import annotations

import json
import os
import re
from html import unescape
from urllib.parse import urlparse

import paths

TV_STREAMS_FILE = os.path.join(paths.DATA_DIR, "tv_streams.json")


def _sanitize_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _normalise_name(raw_name: str, url: str) -> str:
    name = raw_name.strip()
    if name:
        return name
    parsed = urlparse(url)
    host = parsed.netloc or 'stream'
    return host.replace('www.', '').split(':', 1)[0].title()


def _source_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc or 'custom'
    return host.replace('www.', '').split(':', 1)[0]


def normalize_stream(data: dict | None) -> dict:
    item = dict(data or {})
    url = _sanitize_text(item.get("url"), "")
    if not url:
        raise ValueError("An iframe URL is required.")

    stream = {
        "name": _normalise_name(_sanitize_text(item.get("name"), ""), url),
        "url": url,
        "source": _sanitize_text(item.get("source"), _source_from_url(url)),
    }
    return stream


def extract_stream_from_iframe(raw_iframe: str, fallback_name: str = "") -> dict:
    candidate = unescape(_sanitize_text(raw_iframe, ""))
    if not candidate:
        raise ValueError("The iframe input is empty.")

    match = re.search(r'''src\s*=\s*["']([^"']+)["']''', candidate, re.IGNORECASE)
    if not match:
        match = re.search(r'https?://\S+', candidate, re.IGNORECASE)
    if not match:
        raise ValueError("No valid iframe source URL was found.")

    url = match.group(1) if match.lastindex else match.group(0)
    payload = {
        "name": fallback_name,
        "url": url,
    }
    return normalize_stream(payload)


def load_streams() -> list[dict]:
    os.makedirs(os.path.dirname(TV_STREAMS_FILE), exist_ok=True)
    try:
        with open(TV_STREAMS_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    if not isinstance(raw, list):
        return []

    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            cleaned.append(normalize_stream(item))
        except ValueError:
            continue
    if raw != cleaned:
        save_streams(cleaned)
    return cleaned


def save_streams(streams: list[dict]) -> None:
    normalised = []
    for item in streams:
        if isinstance(item, dict):
            try:
                normalised.append(normalize_stream(item))
            except ValueError:
                continue
    os.makedirs(os.path.dirname(TV_STREAMS_FILE), exist_ok=True)
    with open(TV_STREAMS_FILE, "w", encoding="utf-8") as fh:
        json.dump(normalised, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
