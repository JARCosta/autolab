#!/usr/bin/env python3
"""Send hardware metrics from this machine to your AutoLab server.

Requires: pip install psutil requests python-dotenv (optional)

Environment:
  HARDWARE_PUSH_URL   Full URL to POST, e.g. https://xxx.ngrok.io/api/monitor/push
  HARDWARE_PUSH_TOKEN Same value as server HARDWARE_PUSH_TOKEN
  HARDWARE_DEVICE_NAME  Optional; if unset, uses Windows COMPUTERNAME (e.g. DESKTOP-…) or hostname
  HARDWARE_PUSH_INTERVAL  Wall-clock seconds between uploads; one sample per second is taken over that window (default: 60 → 60 points per POST).

This script uses the same sampling and push loop as the AutoLab server process
(``hardware_client.run_push_loop``) so every machine shares one code path.

Run: python hardware_push_agent.py
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    url = os.getenv("HARDWARE_PUSH_URL", "").strip()
    token = os.getenv("HARDWARE_PUSH_TOKEN", "").strip()
    raw = os.getenv("HARDWARE_DEVICE_NAME", "").strip()
    from hardware_client import get_local_device_name, normalize_device_name, run_push_loop

    if raw:
        device = normalize_device_name(raw) or get_local_device_name()
    else:
        device = get_local_device_name()
    interval = float(os.getenv("HARDWARE_PUSH_INTERVAL", "60"))

    if not url or not token or not device:
        print(
            "Set HARDWARE_PUSH_URL, HARDWARE_PUSH_TOKEN, and HARDWARE_DEVICE_NAME "
            "(or run from repo root so device can default from hostname).",
            file=sys.stderr,
        )
        sys.exit(1)

    run_push_loop(url, token, device, interval, kill_event=None, verbose=True)


if __name__ == "__main__":
    main()
