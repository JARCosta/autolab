# AutoLab

Production monorepo for autonomous services running on a home server.

## Services

| Service | Location | Description |
|---------|----------|-------------|
| **stream_elements** | `app/backend/stream_elements/` | Twitch IRC clients that watch StreamElements chat, optional auto-betting on contests (Faceit probabilities, etc.) |
| **webapp** | `webapp/` | Flask app (Blueprints) — balances UI, hardware monitor, boost queue UI, Telegram webhook |
| **boost_bot** | `app/backend/boost_bot/` | Discord bot for game queue / Elo (git submodule) |
| **wallapop_tracker** | `app/backend/wallapop_tracker/` | Optional Wallapop search notifications via Telegram |
| **autolab-node** | `autolab-node/` | Separate Node tooling (submodule); not required for `python main.py` |

## Quick start

```bash
git clone --recurse-submodules git@github.com:JARCosta/autolab.git
cd autolab

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your tokens

# Repo root must be on PYTHONPATH so `app.backend.*` and `webapp` resolve
export PYTHONPATH="$(pwd)"
python main.py
```

Docker sets `PYTHONPATH=/app` for you; for local runs, keep `PYTHONPATH` pointing at the repository root (or configure the same in your IDE).

## Credentials

Secrets live in `.env` (never committed). See `.env.example` for variables: Telegram, Discord, ngrok, optional hardware monitor, optional `FACEIT_API_KEY`.

- Twitch OAuth (device flow) is handled by `app/infrastructure/twitch/oauth.py` and stored in `data/oauth.json` (gitignored).

## Project structure

```
autolab/
├── main.py                 # Orchestrator: threads for Bettors, webapp, Discord; optional Wallapop
├── paths.py                # Data paths under data/ + repo-root stream_elements/resources/
├── logging_config.py
├── requirements.txt
├── .env / .env.example
│
├── app/
│   ├── backend/            # Domain-oriented Python (not “infrastructure”)
│   │   ├── notifications/  # Notification channel API; Telegram implementation
│   │   ├── stream_elements/  # Bettor, betting runner, contests, odds, Twitch chat helpers
│   │   ├── boost_bot/
│   │   └── wallapop_tracker/
│   │
│   └── infrastructure/     # Adapters: persistence + outbound HTTP + Twitch OAuth
│       ├── storage/        # SQLite (balances, hardware metrics, …)
│       ├── http/           # streamelements, faceit, twitch (outbound APIs)
│       └── twitch/         # OAuth device flow + token file
│
├── webapp/                 # Flask: inbound HTTP (UI + APIs + Telegram webhook)
│   ├── home/ shared/ telegram/
│   └── modules/            # Feature UIs: streamelements, monitor, boost
│
├── stream_elements/        # Resources only (variable delay, logs JSON) — paths point here
├── data/                   # Runtime DBs, oauth.json, wallapop, boost JSON (gitignored)
├── autolab-node/           # Submodule (optional)
└── docker-compose.yml Dockerfile entrypoint.sh
```

**Imports:** Outside callers may use the small public API on the package, e.g. `from app.backend.stream_elements import Bettor, fetch_balance`. Inside `stream_elements`, import concrete modules (`bettor`, `se_helpers`, `twitch_chat`, …) directly.

**Notifications:** Domain code calls `app.backend.notifications` (implementation set in `main.py` to Telegram). Inbound Telegram HTTP lives under `webapp/telegram/`.

## Docker

```bash
cp .env.example .env
docker compose up --build -d
```

- Runs `python main.py`, exposes port **5000**.
- Mounts `./data` → `/app/data`; process UID/GID match the host where configured.

## Telegram bot commands

| Command | Description |
|---------|-------------|
| `/balance` | StreamElements balance overview |
| `/wallapop` | Wallapop tracker overview |
| `/search_term …` | Add a Wallapop search term |
| `/reboot` | Reboot host |
| `/restart` | Restart the autolab unit |

## Logs

Single process, multiple threads; shared `logging_config`. In Docker, logs go to stderr for `docker compose logs -f`.

## Wallapop background polling

Telegram commands work on demand. For a background poller thread, set `WALLAPOP_POLL_ENABLED = True` in **`main.py`** (default `False`).

## Adding a Flask blueprint

1. For a feature page, add `webapp/modules/<name>/__init__.py` with a `Blueprint` (see `streamelements`, `monitor`, `boost`). Top-level shells use `webapp/home/` or `webapp/telegram/`.
2. Register it in `webapp/__init__.py` → `create_app()`.
