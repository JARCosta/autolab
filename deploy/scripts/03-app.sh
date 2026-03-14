#!/usr/bin/env bash
#
# 03-app.sh — Clone the repository, set up submodules, create venv, install deps
#
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/common.sh"

# ── Clone repository ────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
    log "Repository already exists at $APP_DIR, pulling latest..."
    sudo -u "$SETUP_USER" bash -c "cd $APP_DIR && git fetch origin && git pull --ff-only"
else
    log "Cloning repository to $APP_DIR..."
    sudo -u "$SETUP_USER" git clone "$REPO_URL" "$APP_DIR"
fi

# ── Submodules ──────────────────────────────────────────────
log "Initializing submodules..."
cd "$APP_DIR"

KEY_FILE="${SETUP_HOME}/.ssh/id_ed25519"
if [ -f "$KEY_FILE" ]; then
    log "Testing GitHub SSH access using $KEY_FILE..."
    if sudo -u "$SETUP_USER" env HOME="$SETUP_HOME" ssh -i "$KEY_FILE" \
           -o BatchMode=yes \
           -o StrictHostKeyChecking=accept-new \
           -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
        log "GitHub SSH access confirmed, initializing all submodules..."
        sudo -u "$SETUP_USER" git submodule update --init --recursive
    else
        warn "GitHub SSH test failed — trying public submodules only"
        sudo -u "$SETUP_USER" git submodule update --init boost_bot || warn "boost_bot submodule failed (may need SSH key)"
    fi
else
    warn "No SSH key found at $KEY_FILE — trying public submodules only"
    sudo -u "$SETUP_USER" git submodule update --init boost_bot || warn "boost_bot submodule failed (may need SSH key)"
fi

# ── Create virtual environment ──────────────────────────────
log "Creating Python virtual environment..."
sudo -u "$SETUP_USER" python3 -m venv "$VENV_DIR"

# ── Install pip dependencies ────────────────────────────────
log "Installing Python dependencies..."
sudo -u "$SETUP_USER" "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u "$SETUP_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

# Install submodule-specific requirements
for subdir in boost_bot; do
    if [ -f "$APP_DIR/$subdir/requirements.txt" ]; then
        log "Installing $subdir dependencies..."
        sudo -u "$SETUP_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/$subdir/requirements.txt" || warn "$subdir deps install had issues"
    fi
done

# ── Create runtime directories ──────────────────────────────
log "Creating runtime directories..."
sudo -u "$SETUP_USER" mkdir -p "$APP_DIR/data/wallapop"
sudo -u "$SETUP_USER" mkdir -p "$APP_DIR/stream_elements/resources"

ok "Application deployed to $APP_DIR"
