# AutoLab

Production monorepo for autonomous services running on a home server.

## Services

| Service | Location | Description |
|---------|----------|-------------|
| **stream_elements** | `app/backend/stream_elements/` | Twitch IRC clients that watch StreamElements chat, optional auto-betting on contests (Faceit probabilities, etc.) |
| **webapp** | `webapp/` | Flask app (Blueprints) — balances UI, hardware monitor, Discord bot dashboard, Continente tracker |
| **boost_bot** | `app/backend/boost_bot/` | Discord bot for game queue / Elo (git submodule) |
| **wallapop_tracker** | `app/backend/wallapop_tracker/` | Optional Wallapop search notifications via Telegram |
| **autolab-node** | `autolab-node/` | Separate Node tooling (submodule); optional |

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

# Per-service (matches docker-compose layout):
python -m app.runtime.entrypoint web        # webapp + toggle UI
python -m app.runtime.entrypoint bettors    # StreamElements bettors
python -m app.runtime.entrypoint discord    # boost_bot
python -m app.runtime.entrypoint wallapop   # wallapop tracker
python -m app.runtime.entrypoint continente # Continente tracker
python -m app.runtime.entrypoint inbound    # Telegram webhook ingress (+ ngrok optional)
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
| `continente` | `autolab-continente` | `continente` |
| `monitor` | (UI inside `autolab-web`) | — |

## Credentials

Secrets live in `.env` (never committed). See `.env.example` for variables: Telegram, Discord, ngrok, optional hardware monitor, optional Continente tracker, optional `FACEIT_API_KEY`.

- **Ngrok** is **off by default** (`WEBAPP_ENABLE_NGROK=0`). The dashboard works over LAN or Tailscale without it. For **Telegram inbound webhooks**, set **`TELEGRAM_WEBHOOK_PUBLIC_URL`** to any HTTPS URL Telegram can reach (Cloudflare Tunnel, a real domain, etc.), or set **`WEBAPP_ENABLE_NGROK=1`** with **`NGROK_AUTH_TOKEN`** if you still want pyngrok.
- Twitch OAuth (device flow) is handled by `app/infrastructure/storage/twitch_oauth/service.py` and stored in `data/oauth.json` (gitignored).

## Project structure

```
autolab/
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
│   │   └── entrypoint.py   # `python -m app.runtime.entrypoint {web|bettors|discord|wallapop|inbound}`
│   ├── backend/            # Domain-oriented Python (not “infrastructure”)
│   │   ├── notifications/  # Notification channel API; Telegram implementation
│   │   ├── stream_elements/  # Bettor, betting runner, contests, odds, Twitch chat helpers
│   │   ├── boost_bot/
│   │   ├── wallapop_tracker/
│   │   └── continente_tracker/
│   │
│   └── infrastructure/     # Adapters: persistence + outbound HTTP
│       ├── storage/        # SQLite + JSON/CSV stores (discord_db, twitch_oauth, wallapop, ...)
│       ├── http/           # streamelements, faceit, twitch (outbound APIs)
│
├── webapp/                 # Flask: UI + module APIs + dedicated inbound service app
│   ├── templates/        # module_layout.html — shared Jinja base for module pages
│   ├── shared/MODULE_PAGE.md  # Required blocks/CSS contract for new module UIs
│   ├── home/ shared/ telegram/
│   └── modules/            # Feature UIs: streamelements, monitor, discord_bot, wallapop, system
│
├── stream_elements/        # Resources only (variable delay, logs JSON) — paths point here
├── data/                   # Runtime DBs, oauth.json, wallapop, boost JSON, modules.json (gitignored)
├── autolab-node/           # Submodule (optional)
└── docker-compose.yml Dockerfile entrypoint.sh
```

**Imports:** Outside callers may use the small public API on the package, e.g. `from app.backend.stream_elements import Bettor, fetch_balance`. Inside `stream_elements`, import concrete modules (`bettor`, `se_helpers`, `twitch_chat`, …) directly.

**Notifications:** Domain code calls `app.backend.notifications` (implementation set by runtime startup to Telegram). Inbound Telegram ingress runs in `webapp/inbound.py` (service `autolab-inbound`) and reuses `webapp/telegram/webhook.py` handler logic.

## Docker

```bash
cp .env.example .env

# Webapp + every enabled module (reads data/modules.json):
bash scripts/start.sh

# Or pick profiles manually:
docker compose --profile bettors --profile discord up --build -d
```

- `autolab-web`, `autolab-inbound`, and `autolab-tailscale` always run; `bettors`, `discord`, `wallapop`, and `continente` are profile-gated.
- Mounts `./data` → `/app/data`; process UID/GID match the host where configured.

**Only `autolab-web` in `docker ps`?** Optional workers (StreamElements / Discord / Wallapop) run in separate profile-gated services (`autolab-bettors`, `autolab-discord`, `autolab-wallapop`). The stack should be started with `scripts/start.sh` (or explicit `--profile` flags) so compose enables the selected workers. `autolab-inbound` and `autolab-tailscale` are always-on infra services. After changing `server-setup`, run `sudo systemctl daemon-reload` if you edited the `autolab` unit so `ExecStart` points at `scripts/start.sh`. Remove leftover one-off containers: `docker compose down --remove-orphans`.

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

## Tailscale VPN

`autolab-tailscale` is an always-on infra service (not a dashboard module). It uses `network_mode: host`, `CAP_NET_ADMIN`, and `/dev/net/tun` with persisted state at `data/tailscale-state/var/lib/tailscale`. Manage device login, routes, and exit-node settings in the Tailscale admin/client tools.

## Wallapop background polling

Telegram commands work on demand. For background polling, enable the
**Wallapop Tracker** toggle on the home page (or set `"wallapop": true` in
`data/modules.json`) and restart.

## Nextcloud

Enable **Nextcloud** on the home page, save, then run `autolab restart`. That starts `autolab-nextcloud` (Apache) and `autolab-nextcloud-db` (MariaDB) under the `nextcloud` compose profile. Open **`http://<host>:5000/cloud`** — when the module is on, that redirects to the Nextcloud UI.

Set **`NEXTCLOUD_PUBLIC_URL`** (in `.env` or the environment) to the URL browsers should use — for example `http://192.168.1.10:8080` or your Tailscale IP if not using localhost. It must match **`NEXTCLOUD_HTTP_PORT`** (mapped host port, default `8080`). Override database passwords with **`NEXTCLOUD_DB_ROOT_PASSWORD`** and **`NEXTCLOUD_DB_PASSWORD`** before exposing this host.

Nextcloud is an external Docker image; there is no `app.runtime.entrypoint` handler — only the compose profile and `profiles: ["nextcloud"]` services.

Autolab uses a **fixed Docker bridge subnet** (`AUTOLAB_DOCKER_SUBNET`, default `172.30.0.0/16`) so this stack does not fight CasaOS or other compose projects for auto-allocated ranges. If Docker reports **`failed to set up container networking`**, stop leftover CasaOS stacks if possible, then try `docker compose down` in this repo and `docker network rm autolab_default` if the network still exists (only when no containers use it). CasaOS often binds **port 8080** — set **`NEXTCLOUD_HTTP_PORT`** to another host port if needed.

## Adding a Flask blueprint

1. For a feature page, add `webapp/modules/<name>/__init__.py` with a `Blueprint` (see `streamelements`, `monitor`, `discord_bot`, `wallapop`). Top-level shells use `webapp/home/` or `webapp/telegram/`.
2. Register it in `webapp/__init__.py` → `create_app()`.

## Adding a toggleable module

1. Append a `ModuleSpec` to `MODULES` in `app/runtime/modules.py` (the `name`
   becomes both the JSON key and the docker-compose profile).
2. If it needs its own container, add a service to `docker-compose.yml` with
   `profiles: ["<name>"]`. Python workers call
   `python -m app.runtime.entrypoint <name>` plus a `cmd_<name>` handler in
   `app/runtime/entrypoint.py`. External images (e.g. Nextcloud) only need the
   matching compose profile — no entrypoint handler.
3. The home page picks up the new card automatically.
