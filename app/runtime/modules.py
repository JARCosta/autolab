"""
Module registry + on/off state.

Toggles from the home-page UI are persisted to ``data/modules.json``. The
``autolab`` CLI reads this file on ``autolab restart`` and starts only the
docker-compose services whose profile is enabled. Inside the webapp container,
the ``monitor`` blueprint is registered conditionally on the same flag.

Adding a new module:
    1. Append an entry to ``MODULES`` below (name = compose-profile name).
    2. If it has a per-service container, add a service to ``docker-compose.yml``
       with a matching ``profiles: [<name>]`` entry.
    3. If it adds a UI card, render it via ``modules_for_home()``.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Iterable

import paths


MODULES_STATE_FILE = os.path.join(paths.DATA_DIR, "modules.json")


@dataclass(frozen=True)
class ModuleSpec:
    """Static metadata for a toggleable module."""
    name: str            # compose profile name + state-file key
    label: str           # card title on the home page
    description: str
    href: str | None     # card link target (None = no dashboard yet)
    icon_color: str      # CSS class suffix in home.css (.card-icon.<color>)
    icon_svg: str        # inline SVG markup for the card icon
    default_enabled: bool = True
    container: bool = True  # has its own compose service (False = webapp-internal toggle)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# `name` MUST match the compose profile + service suffix (e.g. autolab-bettors).
MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        name="bettors",
        label="StreamElements",
        description="Twitch IRC bettor threads. Balances and history live in the dashboard.",
        href="/balances",
        icon_color="green",
        icon_svg=(
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<path d="M1 12L5 6L9 9L15 3" stroke="currentColor" stroke-width="1.5"'
            ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
        ),
    ),
    ModuleSpec(
        name="monitor",
        label="Hardware Monitor",
        description="CPU load, clock speed, and temperature over time.",
        href="/monitor",
        icon_color="blue",
        icon_svg=(
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<rect x="1" y="3" width="14" height="10" rx="1.5" stroke="currentColor" stroke-width="1.3"/>'
            '<path d="M4 9L6 7L8 8.5L12 5.5" stroke="currentColor" stroke-width="1.2"'
            ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
        ),
        container=False,  # served from inside autolab-web
    ),
    ModuleSpec(
        name="discord",
        label="CS2 Custom (Discord)",
        description="Closed-server 5v5 boost_bot: ELO, balanced teams, match history.",
        href="/boost",
        icon_color="orange",
        icon_svg=(
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<path d="M8 1L10 6H15L11 9.5L12.5 15L8 11.5L3.5 15L5 9.5L1 6H6L8 1Z"'
            ' stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>'
        ),
    ),
    ModuleSpec(
        name="wallapop",
        label="Wallapop Tracker",
        description="Polls Wallapop search terms and pushes new listings to Telegram.",
        href="/wallapop",
        icon_color="purple",
        icon_svg=(
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.3"/>'
            '<path d="M11 11L14 14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>'
        ),
        default_enabled=False,
    ),
)


def _by_name() -> dict[str, ModuleSpec]:
    return {m.name: m for m in MODULES}


# ---------------------------------------------------------------------------
# Persisted on/off state
# ---------------------------------------------------------------------------

_STATE_LOCK = threading.Lock()


def _defaults() -> dict[str, bool]:
    return {m.name: m.default_enabled for m in MODULES}


def load_state() -> dict[str, bool]:
    """Read modules.json, applying defaults for missing/new entries."""
    with _STATE_LOCK:
        data = _defaults()
        try:
            with open(MODULES_STATE_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for k, v in stored.items():
                    if k in data:
                        data[k] = bool(v)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return data


def save_state(state: dict[str, bool]) -> None:
    """Persist `state` (only known module keys are written)."""
    known = _by_name()
    cleaned = {k: bool(v) for k, v in state.items() if k in known}
    with _STATE_LOCK:
        os.makedirs(os.path.dirname(MODULES_STATE_FILE), exist_ok=True)
        with open(MODULES_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2)
            f.write("\n")


def is_enabled(name: str) -> bool:
    if name not in _by_name():
        return False
    return bool(load_state()[name])


def set_enabled(name: str, enabled: bool) -> dict[str, bool]:
    if name not in _by_name():
        raise KeyError(f"Unknown module: {name!r}")
    state = load_state()
    state[name] = bool(enabled)
    save_state(state)
    return state


def enabled_names() -> list[str]:
    state = load_state()
    return [m.name for m in MODULES if state.get(m.name)]


def container_profiles() -> list[str]:
    """Names of currently-enabled modules that map to a docker-compose profile."""
    state = load_state()
    return [m.name for m in MODULES if m.container and state.get(m.name)]


def modules_for_home() -> list[dict]:
    """Render-ready list for the home template."""
    state = load_state()
    return [
        {
            "name": m.name,
            "label": m.label,
            "description": m.description,
            "href": m.href,
            "icon_color": m.icon_color,
            "icon_svg": m.icon_svg,
            "enabled": state.get(m.name, m.default_enabled),
        }
        for m in MODULES
    ]


def known_names() -> Iterable[str]:
    return _by_name().keys()
