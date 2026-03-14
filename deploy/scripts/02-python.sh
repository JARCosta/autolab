#!/usr/bin/env bash
#
# 02-python.sh — Install Python 3.12, pip, and system-level Python dependencies
#
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/common.sh"

# ── Install Python ──────────────────────────────────────────
log "Installing Python 3.12..."
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -qq
apt-get install -y -qq \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip

update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
update-alternatives --set python3 /usr/bin/python3.12

log "Python version: $(python3 --version)"

# ── System-level libs needed by Python packages ─────────────
log "Installing system libraries for Python packages..."
apt-get install -y -qq \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    libfreetype6-dev \
    pkg-config

ok "Python environment ready"
