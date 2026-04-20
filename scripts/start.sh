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

echo "[autolab] starting compose with profiles: ${PROFILES[*]:-<none>}"
# Detached: journal captures pull/build and container start only. Runtime logs are
# not streamed into systemd; use `autolab logs` or `docker compose logs -f`.
exec docker compose "${PROFILE_FLAGS[@]}" up --build -d
