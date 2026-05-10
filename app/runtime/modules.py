"""
Module registry + on/off state.

Toggles from the home-page UI are persisted to ``data/modules.json``. The
``autolab`` CLI reads this file on ``autolab restart`` and starts only the
docker-compose services whose profile is enabled. Inside the webapp container,
the ``monitor`` blueprint is registered conditionally on ``modules.json["monitor"]``.
The ``/cloud`` route checks ``nextcloud`` the same way (redirect vs disabled page).

Adding a new module:
    1. Append an entry to ``MODULES`` below (name = compose-profile name).
    2. If it has a per-service container, add a service to ``docker-compose.yml``
       with a matching ``profiles: [<name>]`` entry.
    3. If it adds a UI card, render it via ``modules_for_home()``.
    4. If it adds a dashboard page, follow ``webapp/shared/MODULE_PAGE.md`` (extends
       ``webapp/templates/module_layout.html``).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

from app.infrastructure.storage.modules_state import (
    load_modules_state,
    save_modules_state,
)


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
        description="Queue and Elo in Discord; web dashboard shows shared stats and commands.",
        href="/discord",
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
    ModuleSpec(
        name="continente",
        label="Continente Tracker",
        description="Tracks products you rate and alerts when price is below your baseline.",
        href="/continente",
        icon_color="green",
        icon_svg=(
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<path d="M3 4.5H13L11.8 9.5H5L3 2.5H1.5" stroke="currentColor" stroke-width="1.2"'
            ' stroke-linecap="round" stroke-linejoin="round"/>'
            '<circle cx="6" cy="12.5" r="1" fill="currentColor"/>'
            '<circle cx="11" cy="12.5" r="1" fill="currentColor"/></svg>'
        ),
        default_enabled=False,
    ),
    ModuleSpec(
        name="nextcloud",
        label="Nextcloud",
        description="Self-hosted files and sync; toggle starts MariaDB + Nextcloud containers.",
        href="/cloud",
        icon_color="blue",
        icon_svg=(
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<path d="M4 10.5C4 9.12 5.12 8 6.5 8c.58 0 1.12.17 1.58.45C8.65 7.17 9.77 6.5 11 6.5c2.21 0 4 1.79 4 4"'
            ' stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>'
            '<path d="M1 10.5C1 8.57 2.57 7 4.5 7c.83 0 1.58.28 2.18.75C7.35 6.65 8.6 6 10 6c2.76 0 5 2.24 5 5"'
            ' stroke="currentColor" stroke-width="1.3" stroke-linecap="round" opacity=".55"/></svg>'
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
        return load_modules_state(_defaults())


def save_state(state: dict[str, bool]) -> None:
    """Persist `state` (only known module keys are written)."""
    known_keys = set(_by_name().keys())
    with _STATE_LOCK:
        save_modules_state(state, known_keys)


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
