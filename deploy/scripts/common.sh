#!/usr/bin/env bash
#
# common.sh — Shared variables and helper functions for all scripts
#
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

LOG_FILE="${LOG_FILE:-/var/log/autolab-setup.log}"

log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[!]${NC} $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "${RED}[✗]${NC} $*" | tee -a "$LOG_FILE"; }

export SETUP_USER="${SETUP_USER:-$(whoami)}"
export SETUP_HOME="${SETUP_HOME:-$(eval echo ~$SETUP_USER)}"
export APP_DIR="${APP_DIR:-${SETUP_HOME}/autolab}"
export VENV_DIR="${VENV_DIR:-${APP_DIR}/.venv}"
export REPO_URL="${REPO_URL:-git@github.com:JARCosta/autolab.git}"
