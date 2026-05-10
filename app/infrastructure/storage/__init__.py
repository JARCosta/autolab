"""Storage / persistence helpers shared across modules.

Subpackages include SQLite stores (``balances_db``, ``hardware_db``, ``continente_db``) and
file-backed stores (``discord_db``, ``modules_state``, ``wallapop_store``,
``telegram_log``, ``twitch_oauth``) for documents under ``data/``.

This package should not import Flask or any UI/web layer modules.
"""

