"""
Centralized filesystem paths for AutoLab. All runtime data and module-specific
resources live under DATA_DIR or under package-named dirs; no magic strings elsewhere.
"""
import os

# Base data directory (gitignored); OAuth, Wallapop, and log buffer live here
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Balance cache for instant dashboard load (SQLite)
BALANCE_CACHE_DB = os.path.join(DATA_DIR, "balance_cache.db")

# OAuth (Twitch tokens, auto-refreshed)
OAUTH_FILE = os.path.join(DATA_DIR, "oauth.json")

# Telegram log buffer (accumulated lines sent as one message)
TELEGRAM_LOG_FILE = os.path.join(DATA_DIR, "telegram_message.txt")

# Wallapop tracker
WALLAPOP_DIR = os.path.join(DATA_DIR, "wallapop")
WALLAPOP_SEARCH_TERMS_FILE = os.path.join(WALLAPOP_DIR, "search_terms.csv")
WALLAPOP_DATA_FILE = os.path.join(WALLAPOP_DIR, "data.csv")

# StreamElements betting (per-channel state, variable delay, message logs)
STREAMELEMENTS_RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "stream_elements", "resources")
STREAMELEMENTS_LAST_BET_FILE = os.path.join(STREAMELEMENTS_RESOURCES_DIR, "last_bet.json")
STREAMELEMENTS_VARIABLE_DELAY_FILE = os.path.join(STREAMELEMENTS_RESOURCES_DIR, "variable_delay.txt")
STREAMELEMENTS_MESSAGE_LOGS_FILE = os.path.join(STREAMELEMENTS_RESOURCES_DIR, "message_logs.json")
