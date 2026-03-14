#!/usr/bin/env bash
#
# setup-github-ssh.sh — Generate an SSH key and configure GitHub access
# Run as the application user (not root):
#   bash deploy/scripts/setup-github-ssh.sh
#
set -euo pipefail

SSH_DIR="$HOME/.ssh"
KEY_FILE="$SSH_DIR/id_ed25519"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

if [ -f "$KEY_FILE" ]; then
    echo "SSH key already exists at $KEY_FILE"
else
    echo "Generating SSH key..."
    ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -C "$(whoami)@$(hostname)"
    echo ""
    echo "SSH key generated."
fi

chmod 600 "$KEY_FILE"
[ -f "$KEY_FILE.pub" ] && chmod 644 "$KEY_FILE.pub"

echo ""
echo "Testing GitHub SSH connection using $KEY_FILE..."
if ssh -i "$KEY_FILE" \
       -o BatchMode=yes \
       -o StrictHostKeyChecking=accept-new \
       -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo "GitHub SSH access confirmed!"
    echo ""
    echo "Now initialize all submodules:"
    echo "  cd ~/autolab && git submodule update --init --recursive"
    exit 0
fi

echo ""
echo "GitHub SSH test failed."
echo ""
echo "═══════════════════════════════════════════════════"
echo "  Add this public key to GitHub:"
echo "  https://github.com/settings/ssh/new"
echo "═══════════════════════════════════════════════════"
echo ""
cat "$KEY_FILE.pub"
echo ""
echo "═══════════════════════════════════════════════════"
echo ""
echo "After adding the key, re-run this script:"
echo "  bash deploy/scripts/setup-github-ssh.sh"
exit 1
