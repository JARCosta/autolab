"""Read/write helpers for Tailscale dashboard settings."""

from __future__ import annotations

import json
import os
import shlex
from typing import Any

import paths

_DEFAULTS: dict[str, Any] = {
    "auth_key": "",
    "hostname": "autolab",
    "advertise_routes": "",
    "advertise_exit_node": False,
    "accept_routes": True,
    "accept_dns": True,
    "enable_ssh": True,
    "extra_args": "",
    "userspace": False,
}

# Path inside the official Tailscale container; matches the compose volume mount.
_TS_STATE_DIR = "/var/lib/tailscale"


def default_settings() -> dict[str, Any]:
    return dict(_DEFAULTS)


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    data["auth_key"] = str(data.get("auth_key") or "").strip()
    data["hostname"] = str(data.get("hostname") or "").strip() or _DEFAULTS["hostname"]
    data["advertise_routes"] = str(data.get("advertise_routes") or "").strip()
    data["extra_args"] = str(data.get("extra_args") or "").strip()
    data["advertise_exit_node"] = bool(data.get("advertise_exit_node"))
    data["accept_routes"] = bool(data.get("accept_routes"))
    data["accept_dns"] = bool(data.get("accept_dns"))
    data["enable_ssh"] = bool(data.get("enable_ssh"))
    data["userspace"] = bool(data.get("userspace"))
    return data


def load_settings() -> dict[str, Any]:
    data = default_settings()
    try:
        with open(paths.TAILSCALE_SETTINGS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for key in data:
                if key in raw:
                    data[key] = raw[key]
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return _normalize(data)


def build_extra_args(settings: dict[str, Any]) -> str:
    args: list[str] = []

    hostname = str(settings.get("hostname") or "").strip()
    if hostname:
        args.append(f"--hostname={hostname}")

    routes = str(settings.get("advertise_routes") or "").strip()
    if routes:
        args.append(f"--advertise-routes={routes}")

    if bool(settings.get("advertise_exit_node")):
        args.append("--advertise-exit-node")
    if bool(settings.get("accept_routes")):
        args.append("--accept-routes")
    if not bool(settings.get("accept_dns")):
        args.append("--accept-dns=false")
    if bool(settings.get("enable_ssh")):
        args.append("--ssh")

    extra = str(settings.get("extra_args") or "").strip()
    if extra:
        try:
            args.extend(shlex.split(extra))
        except ValueError as exc:
            raise ValueError("extra_args must be valid shell-style tokens") from exc

    return " ".join(args)


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = load_settings()
    for key, value in settings.items():
        if key not in merged:
            continue
        if key == "auth_key":
            new_key = str(value or "").strip()
            if new_key:
                merged["auth_key"] = new_key
            continue
        merged[key] = value

    merged = _normalize(merged)

    os.makedirs(os.path.dirname(paths.TAILSCALE_SETTINGS_FILE), exist_ok=True)
    with open(paths.TAILSCALE_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")

    ts_extra_args = build_extra_args(merged)
    env_lines = [
        f"TS_AUTHKEY={merged['auth_key']}",
        f"TS_EXTRA_ARGS={ts_extra_args}",
        f"TS_STATE_DIR={_TS_STATE_DIR}",
        f"TS_USERSPACE={'true' if merged['userspace'] else 'false'}",
    ]
    with open(paths.TAILSCALE_ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(env_lines) + "\n")

    return merged
