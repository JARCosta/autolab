#!/usr/bin/env bash
#
# Start the autolab stack with only the docker-compose profiles whose
# corresponding module is enabled in data/modules.json.
#
# - The web service has no profile and always runs.
# - bettors / discord / wallapop are profile-gated; their flags come from
#   data/modules.json (managed by the home page toggle UI).
#
# This script is the ExecStart of the systemd `autolab` unit; it is also
# safe to invoke manually from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)"

# Single source of truth with app/runtime/modules.py (same as the webapp toggles).
readarray -t PROFILES < <(python3 -c "from app.runtime.modules import container_profiles; print('\\n'.join(container_profiles()))")

PROFILE_FLAGS=()
for p in "${PROFILES[@]}"; do
    [[ -n "$p" ]] && PROFILE_FLAGS+=(--profile "$p")
done

echo "[autolab] data dir: $(pwd)/data"
python3 - <<'PY'
from app.runtime.modules import load_state
print("[autolab] persisted module state:", load_state())
PY

echo "[autolab] starting compose with profiles: ${PROFILES[*]:-<none>}"
# Stop and remove containers for any container-backed modules that are
# currently disabled so they don't keep running after a restart.
# This prints service names like: autolab-discord autolab-bettors
PYOUT=$(python3 - <<'PY'
from app.runtime.modules import MODULES, container_profiles
enabled = set(container_profiles())
servs = []
for m in MODULES:
    if m.container and m.name not in enabled:
        servs.append(f"autolab-{m.name}")
print(' '.join(servs))
PY
) || PYOUT=""
STOP_SERVICES=( $PYOUT )
if [ ${#STOP_SERVICES[@]} -gt 0 ]; then
    echo "[autolab] stopping disabled services: ${STOP_SERVICES[*]}"
    docker compose stop "${STOP_SERVICES[@]}" || true
    docker compose rm -f "${STOP_SERVICES[@]}" || true
fi

# Detached: journal captures pull/build and container start only. Runtime logs are
# not streamed into systemd; use `autolab logs` or `docker compose logs -f`.
exec docker compose "${PROFILE_FLAGS[@]}" up --build -d
