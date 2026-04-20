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

# Local dev: single process, every enabled module on a thread
python main.py

# Per-service (matches docker-compose layout):
python -m app.runtime.entrypoint web        # webapp + toggle UI
python -m app.runtime.entrypoint bettors    # StreamElements bettors
python -m app.runtime.entrypoint discord    # boost_bot
python -m app.runtime.entrypoint wallapop   # wallapop tracker
```

Docker sets `PYTHONPATH=/app` for you; for local runs, keep `PYTHONPATH` pointing at the repository root (or configure the same in your IDE).

## Module on/off

Each module on the home page (`/`) has a toggle in its top-right corner. Toggle
changes stay local in the page until you press **Save modules**; then one API
request writes `data/modules.json`. `scripts/start.sh` reads that file to decide
which docker-compose profiles to bring up. After saving, run **`autolab restart`**
on the server (the dashboard cannot restart Docker from inside the container;
the banner reminds you and offers a copyable command).

| Module | Compose service | Profile |
|--------|-----------------|---------|
| `bettors` | `autolab-bettors` | `bettors` |
| `discord` | `autolab-discord` | `discord` |
| `wallapop` | `autolab-wallapop` | `wallapop` |
| `monitor` | (UI inside `autolab-web`) | — |

## Credentials

Secrets live in `.env` (never committed). See `.env.example` for variables: Telegram, Discord, ngrok, optional hardware monitor, optional `FACEIT_API_KEY`.

- Twitch OAuth (device flow) is handled by `app/infrastructure/twitch/oauth.py` and stored in `data/oauth.json` (gitignored).

## Project structure

```
autolab/
├── main.py                 # Local-dev shim → app.runtime.entrypoint all
├── paths.py                # Data paths under data/ + repo-root stream_elements/resources/
├── logging_config.py
├── requirements.txt
├── .env / .env.example
├── scripts/
│   ├── start.sh            # systemd ExecStart: reads modules.json, runs `docker compose … up --build -d` (detached)
│   └── stop.sh             # systemd ExecStop: `docker compose down`
│
├── app/
│   ├── runtime/            # Process orchestration
│   │   ├── modules.py      # Module registry + data/modules.json state
│   │   └── entrypoint.py   # `python -m app.runtime.entrypoint {web|bettors|discord|wallapop|all}`
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
│   └── modules/            # Feature UIs: streamelements, monitor, boost, wallapop, system
│
├── stream_elements/        # Resources only (variable delay, logs JSON) — paths point here
├── data/                   # Runtime DBs, oauth.json, wallapop, boost JSON, modules.json (gitignored)
├── autolab-node/           # Submodule (optional)
└── docker-compose.yml Dockerfile entrypoint.sh
```

**Imports:** Outside callers may use the small public API on the package, e.g. `from app.backend.stream_elements import Bettor, fetch_balance`. Inside `stream_elements`, import concrete modules (`bettor`, `se_helpers`, `twitch_chat`, …) directly.

**Notifications:** Domain code calls `app.backend.notifications` (implementation set in `main.py` to Telegram). Inbound Telegram HTTP lives under `webapp/telegram/`.

## Docker

```bash
cp .env.example .env

# Webapp + every enabled module (reads data/modules.json):
bash scripts/start.sh

# Or pick profiles manually:
docker compose --profile bettors --profile discord up --build -d
```

- `autolab-web` always runs (port **5000**); `bettors`, `discord`, `wallapop` are profile-gated.
- Mounts `./data` → `/app/data`; process UID/GID match the host where configured.

**Only `autolab-web` in `docker ps`?** StreamElements bettors and Discord do **not** run inside the web container; they are separate services (`autolab-bettors`, `autolab-discord`). The stack must be started with `scripts/start.sh` (or `docker compose --profile bettors … up`) so compose enables those profiles. Plain `docker compose up` without profiles starts **only** `autolab-web`. After changing `server-setup`, run `sudo systemctl daemon-reload` if you edited the `autolab` unit so `ExecStart` points at `scripts/start.sh`. Remove leftover one-off containers: `docker compose down --remove-orphans`.

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

Telegram commands work on demand. For background polling, enable the
**Wallapop Tracker** toggle on the home page (or set `"wallapop": true` in
`data/modules.json`) and restart.

## Adding a Flask blueprint

1. For a feature page, add `webapp/modules/<name>/__init__.py` with a `Blueprint` (see `streamelements`, `monitor`, `boost`, `wallapop`). Top-level shells use `webapp/home/` or `webapp/telegram/`.
2. Register it in `webapp/__init__.py` → `create_app()`.

## Adding a toggleable module

1. Append a `ModuleSpec` to `MODULES` in `app/runtime/modules.py` (the `name`
   becomes both the JSON key and the docker-compose profile).
2. If it needs its own container, add a service to `docker-compose.yml` with
   `profiles: ["<name>"]` and a command that calls
   `python -m app.runtime.entrypoint <name>`. Then add a `cmd_<name>` handler
   in `app/runtime/entrypoint.py`.
3. The home page picks up the new card automatically.
