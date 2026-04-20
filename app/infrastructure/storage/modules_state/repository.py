"""Read/write helpers for module toggle state in ``data/modules.json``."""

from __future__ import annotations

import json
import os

import paths

MODULES_STATE_FILE = os.path.join(paths.DATA_DIR, "modules.json")


def load_modules_state(defaults: dict[str, bool]) -> dict[str, bool]:
    """Load saved state, overlaying it on top of ``defaults``."""
    data = dict(defaults)
    try:
        with open(MODULES_STATE_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in data:
                    data[key] = bool(value)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return data


def save_modules_state(state: dict[str, bool], known_keys: set[str]) -> None:
    """Persist known module keys only."""
    cleaned = {k: bool(v) for k, v in state.items() if k in known_keys}
    os.makedirs(os.path.dirname(MODULES_STATE_FILE), exist_ok=True)
    with open(MODULES_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2)
        f.write("\n")
