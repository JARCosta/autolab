# AutoLab

Production monorepo for autonomous services running on a home server.

## Services

| Service | Description |
|---------|-------------|
| **stream_elements** | Twitch IRC bots that auto-bet on StreamElements contests using Faceit win probability |
| **webapp** | Flask app exposed via ngrok tunnel — hosts the Telegram bot webhook and is extensible for future UIs/APIs |
| **boost_bot** | Discord bot for game queue management with Elo ranking (git submodule) |
| **wallapop_tracker** | Polls Wallapop for new listings matching search terms and sends Telegram notifications |

## Quick Start

```bash
# Clone with submodules
git clone --recurse-submodules git@github.com:JARCosta/autolab.git
cd autolab

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set up credentials
cp .env.example .env
# Edit .env with your actual tokens

# Run
python main.py
```

## Credentials

All secrets live in a single `.env` file (never committed). See `.env.example` for the full list:

| Variable | Used by |
|----------|---------|
| `TELEGRAM_NOTIFICATION_TOKEN` | Telegram bot (user-facing messages) |
| `TELEGRAM_LOGS_TOKEN` | Telegram bot (log channel) |
| `TELEGRAM_USER_ID` | Telegram bot (recipient chat ID) |
| `DISCORD_TOKEN` | BoostBot (Discord bot) |
| `NGROK_AUTH_TOKEN` | Webapp (ngrok tunnel for webhook) |
| `FACEIT_API_KEY` | StreamElements (win probability from Faceit) |

Twitch OAuth tokens are auto-refreshed and stored in `data/oauth.json` (gitignored).

## Project Structure

```
autolab/
├── main.py                   # Process orchestrator
├── config.py                 # Non-secret configuration (channels, bettors, WALLAPOP_POLL_ENABLED)
├── paths.py                  # Centralized data/resource paths (no magic strings elsewhere)
├── .env                      # Secrets (gitignored)
├── .env.example              # Template
├── requirements.txt          # Python dependencies (pinned)
│
├── notifications/            # User-facing channel (frontend); domain services push here
│   ├── __init__.py           # API: send_message, send_image, log buffer, set_channel()
│   └── telegram.py           # Telegram channel (your frontend)
│
├── webapp/                   # Flask app (extensible with Blueprints)
│   ├── __init__.py           # App factory + ngrok
│   ├── balance_data.py       # Shared on-demand data (balance table for Telegram + web)
│   ├── dashboard/            # Web UI Blueprint (e.g. / = balance table)
│   │   ├── __init__.py
│   │   └── templates/
│   └── telegram/             # Telegram bot Blueprint
│       ├── webhook.py        # /webhook route
│       └── commands.py       # Bot commands (/balance, /wallapop, etc.)
│
├── stream_elements/          # Twitch StreamElements betting
│   ├── bettor.py             # IRC connection + bet handling
│   ├── betting.py            # Optimal bet calculation + analysis
│   ├── oauth.py              # Twitch OAuth token management
│   └── utils.py              # Twitch message parsing, Faceit API
│
├── boost_bot/                # Discord bot (git submodule)
│
├── wallapop_tracker/         # Wallapop listing notifications
│   └── tracker.py            # Search, track, notify
│
└── data/                     # Runtime data (gitignored)
    ├── oauth.json            # Auto-refreshed Twitch tokens
    └── wallapop/             # Search terms + listing data
```

## Running with Docker

The repo includes a simple Docker setup:

```bash
cp .env.example .env      # fill in your tokens
docker compose up --build -d
```

- The container runs `python main.py` and exposes port `5000` (Flask webapp / ngrok entry).
- `./data` on the host is mounted as `/app/data` in the container, so OAuth tokens and Wallapop data persist across rebuilds.
- The process runs as your user (UID/GID from the host), so files created in `./data` are owned by you, not root.

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/balance` | Show StreamElements balance across all channels |
| `/wallapop` | Show active Wallapop search terms |
| `/search_term <term>` | Add a new Wallapop search term |
| `/reboot` | Reboot the server |
| `/restart` | Restart the autolab service |

## Logs (Docker)

All components use the shared `logging_config` module: logs go to stderr with a `[level] [name]` format so `docker compose logs -f` prefixes every line with `autolab  |`. The app runs in a **single process** with **threads** (Bettors, webapp, Discord bot), which keeps memory low and log output consistent.

## Notifications and paths

- **notifications**: The notification *channel* is your user-facing side (frontend). Domain services (stream_elements betting, wallapop_tracker, webapp commands) send messages via `notifications.send_message()` and related helpers. In `main.py` the channel is set to the Telegram implementation, so domain code does not depend on the webapp.
- **paths**: All data and resource paths live in `paths.py` (`data/`, OAuth, Wallapop, StreamElements resources, log buffer). Other modules import from `paths` instead of hardcoding paths.

## Wallapop background polling

The Wallapop tracker can run in two ways: (1) **On demand** — Telegram commands `/wallapop` and `/search_term` work anytime; (2) **Background polling** — set `WALLAPOP_POLL_ENABLED = True` in `config.py` to start a thread that runs one process per search term and notifies via the notification abstraction. Default is `False`.

## Adding New Webapp Modules

The webapp uses Flask Blueprints. To add a new module (e.g. a dashboard):

1. Create `webapp/dashboard/__init__.py` with a `Blueprint`
2. Register it in `webapp/__init__.py` → `create_app()`
3. All modules share the same ngrok tunnel
