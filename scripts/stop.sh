#!/usr/bin/env bash
# Stop every autolab compose service (regardless of which profiles are active).
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose down --remove-orphans
