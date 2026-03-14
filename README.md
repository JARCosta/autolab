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
├── config.py                 # Non-secret configuration (channels, bettors)
├── .env                      # Secrets (gitignored)
├── .env.example              # Template
├── requirements.txt          # Python dependencies
│
├── webapp/                   # Flask app (extensible with Blueprints)
│   ├── __init__.py           # App factory + ngrok
│   └── telegram/             # Telegram bot Blueprint
│       ├── webhook.py        # /webhook route
│       ├── messaging.py      # sendMessage/sendImage helpers
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
├── deploy/                   # Server provisioning
│   ├── setup.sh              # Main entry point (run as root)
│   └── scripts/              # Modular setup steps
│
└── data/                     # Runtime data (gitignored)
    ├── oauth.json            # Auto-refreshed Twitch tokens
    └── wallapop/             # Search terms + listing data
```

## Server Deployment

For a fresh Ubuntu server:

```bash
# 1. SSH key setup
ssh-copy-id user@server-ip

# 2. Clone and run setup
ssh user@server-ip
git clone git@github.com:JARCosta/autolab.git
cd autolab/deploy
sudo ./setup.sh

# 3. Configure credentials
cp ~/autolab/.env.example ~/autolab/.env
nano ~/autolab/.env

# 4. Start
autolab start
```

### Management Commands

```bash
autolab start     # Start the service
autolab stop      # Stop the service
autolab restart   # Restart the service
autolab status    # Show service status
autolab logs      # Follow live logs
```

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/balance` | Show StreamElements balance across all channels |
| `/wallapop` | Show active Wallapop search terms |
| `/search_term <term>` | Add a new Wallapop search term |
| `/reboot` | Reboot the server |
| `/restart` | Restart the autolab service |

## Adding New Webapp Modules

The webapp uses Flask Blueprints. To add a new module (e.g. a dashboard):

1. Create `webapp/dashboard/__init__.py` with a `Blueprint`
2. Register it in `webapp/__init__.py` → `create_app()`
3. All modules share the same ngrok tunnel
