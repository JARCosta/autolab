#!/usr/bin/env python3
"""Development helper: merge hardware DB rows from old device ids into one label.

Default: move ``local`` and ``e2bd4e70a8ed`` into ``h0m3l4b``.

Run from the repo root:

  python merge_hardware_devices.py
  python merge_hardware_devices.py --target myserver --from local --from abc123
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--target",
        default="h0m3l4b",
        help="Device label to assign (must match server validation rules)",
    )
    p.add_argument(
        "--from",
        dest="sources",
        action="append",
        default=[],
        metavar="DEVICE",
        help="Source device id (repeat for multiple; defaults to local and e2bd4e70a8ed)",
    )
    args = p.parse_args()
    sources = args.sources if args.sources else ["local", "e2bd4e70a8ed"]

    from storage.hardware import reassign_hardware_device_history

    try:
        n = reassign_hardware_device_history(sources, args.target)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"Updated {n} row(s) to device {args.target!r} (sources: {sources})")


if __name__ == "__main__":
    main()
