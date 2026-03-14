#!/usr/bin/env bash
#
# 04-services.sh — Create systemd services for the application
#
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/common.sh"

# ── Main application service ────────────────────────────────
log "Creating systemd service for autolab..."

cat > /etc/systemd/system/autolab.service << EOF
[Unit]
Description=AutoLab - StreamElements Bettors, Telegram Bot, Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SETUP_USER}
Group=${SETUP_USER}
WorkingDirectory=${APP_DIR}

ExecStartPre=/usr/bin/bash -c 'cd ${APP_DIR} && git fetch origin && git pull --ff-only || true'
ExecStartPre=/usr/bin/bash -c 'cd ${APP_DIR} && git submodule update --remote boost_bot || true'
ExecStart=${VENV_DIR}/bin/python main.py

Restart=on-failure
RestartSec=30
StartLimitBurst=5
StartLimitIntervalSec=300

StandardOutput=journal
StandardError=journal
SyslogIdentifier=autolab

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${APP_DIR}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# ── Daily system reboot (06:10) ──────────────────────────────
log "Creating daily reboot timer (06:10)..."

cat > /etc/systemd/system/daily-reboot.service << EOF
[Unit]
Description=Daily system reboot

[Service]
Type=oneshot
ExecStart=/usr/sbin/reboot
EOF

cat > /etc/systemd/system/daily-reboot.timer << EOF
[Unit]
Description=Run daily system reboot at 06:10

[Timer]
OnCalendar=*-*-* 06:10:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# ── Enable services ─────────────────────────────────────────
log "Enabling services..."
systemctl daemon-reload
systemctl enable autolab.service
systemctl enable --now daily-reboot.timer

warn "Service 'autolab' is enabled but NOT started (.env may not be ready)"
warn "Start it manually:  sudo systemctl start autolab"

# ── Management script ──────────────────────────────────────
log "Creating management helper..."
cat > /usr/local/bin/autolab << 'MGMT'
#!/usr/bin/env bash
case "${1:-}" in
    start)   sudo systemctl start autolab ;;
    stop)    sudo systemctl stop autolab ;;
    restart) sudo systemctl restart autolab ;;
    status)  sudo systemctl status autolab ;;
    logs)    sudo journalctl -u autolab -f --no-hostname ;;
    *)
        echo "Usage: autolab {start|stop|restart|status|logs}"
        echo ""
        echo "  start    Start the application"
        echo "  stop     Stop the application"
        echo "  restart  Restart the application"
        echo "  status   Show service status"
        echo "  logs     Follow live logs"
        ;;
esac
MGMT
chmod +x /usr/local/bin/autolab

ok "Systemd services configured"
ok "Use 'autolab' command for quick management (autolab start/stop/restart/status/logs)"
