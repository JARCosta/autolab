"""StreamElements / Twitch betting package.

Cross-package API (import these from here; they load lazily to avoid cycles with storage)::

    from app.backend.stream_elements import Bettor, fetch_balance

Inside this package, prefer importing concrete modules
(``bettor``, ``se_helpers``, ``twitch_chat``, …) directly.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["Bettor", "fetch_balance"]


def __getattr__(name: str) -> Any:
    if name == "fetch_balance":
        return importlib.import_module(".se_helpers", __name__).fetch_balance
    if name == "Bettor":
        return importlib.import_module(".bettor", __name__).Bettor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
