#!/usr/bin/env bash
#
# 01-system.sh — System packages, SSH hardening, firewall, fail2ban
#
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/common.sh"

# ── System update ───────────────────────────────────────────
log "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get dist-upgrade -y -qq

# ── Essential packages ──────────────────────────────────────
log "Installing essential packages..."
apt-get install -y -qq \
    build-essential \
    curl \
    wget \
    git \
    htop \
    tmux \
    unzip \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    jq \
    tree \
    ncdu \
    net-tools

# ── SSH hardening ───────────────────────────────────────────
log "Configuring SSH..."
SSHD_CONFIG="/etc/ssh/sshd_config"
SSHD_BACKUP="/etc/ssh/sshd_config.backup.$(date +%F-%H%M%S)"
cp "$SSHD_CONFIG" "$SSHD_BACKUP"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp "$SCRIPT_DIR/config/sshd_hardened.conf" /etc/ssh/sshd_config.d/99-hardened.conf

sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config.d/99-hardened.conf || true
echo "PasswordAuthentication no" >> /etc/ssh/sshd_config.d/99-hardened.conf
ok "Password authentication disabled (SSH key login only)"

systemctl restart ssh || systemctl restart sshd

# ── Firewall (UFW) ──────────────────────────────────────────
log "Configuring firewall..."
apt-get install -y -qq ufw

ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 5000/tcp comment "Flask webapp"
echo "y" | ufw enable
ok "Firewall enabled (SSH + port 5000)"

# ── Fail2Ban ────────────────────────────────────────────────
log "Installing and configuring fail2ban..."
apt-get install -y -qq fail2ban

cat > /etc/fail2ban/jail.local << 'JAIL'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled = true
port    = ssh
filter  = sshd
maxretry = 3
bantime  = 24h
JAIL

systemctl enable fail2ban
systemctl restart fail2ban
ok "Fail2ban configured"

# ── Timezone ────────────────────────────────────────────────
log "Setting timezone to Europe/Lisbon..."
timedatectl set-timezone Europe/Lisbon

# ── Swap (if not present and RAM < 4GB) ────────────────────
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
if [[ $TOTAL_RAM_KB -lt 4000000 ]] && ! swapon --show | grep -q "/swapfile"; then
    log "Low RAM detected, creating 2GB swap..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo "/swapfile none swap sw 0 0" >> /etc/fstab
    ok "Swap created"
fi

# ── Automatic security updates ──────────────────────────────
log "Enabling automatic security updates..."
apt-get install -y -qq unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

ok "System setup complete"
