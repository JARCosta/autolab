#!/usr/bin/env bash
#
# 05-optional.sh — Install optional components (run manually as needed)
#   Usage: sudo bash 05-optional.sh [component...]
#   Components: ngrok, tesseract, ollama, docker, all
#
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/common.sh"

install_ngrok() {
    log "Installing ngrok..."
    if command -v ngrok &>/dev/null; then
        ok "ngrok already installed"
        return
    fi
    curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
        | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
        | tee /etc/apt/sources.list.d/ngrok.list
    apt-get update -qq
    apt-get install -y -qq ngrok
    ok "ngrok installed (pyngrok in the venv handles auth automatically)"
}

install_docker() {
    log "Installing Docker..."
    if command -v docker &>/dev/null; then
        ok "Docker already installed"
        return
    fi
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "$SETUP_USER"
    systemctl enable docker
    systemctl start docker
    ok "Docker installed (user $SETUP_USER added to docker group)"
    log "Log out and back in for docker group to take effect"
}

# ── Parse arguments ─────────────────────────────────────────
if [[ $# -eq 0 ]]; then
    echo "Usage: sudo bash $0 [component...]"
    echo "Components: ngrok, docker, all"
    exit 0
fi

for component in "$@"; do
    case "$component" in
        ngrok)  install_ngrok ;;
        docker) install_docker ;;
        all)
            install_ngrok
            install_docker
            ;;
        *)
            err "Unknown component: $component"
            echo "Valid components: ngrok, docker, all"
            ;;
    esac
done
