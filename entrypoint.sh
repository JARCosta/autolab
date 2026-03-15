#!/bin/sh
# Run the app as the host user so created files (e.g. in ./data) are owned by you, not root.
set -e
UID="${AUTOLAB_UID:-1000}"
GID="${AUTOLAB_GID:-1000}"
if [ "$UID" != "0" ]; then
  # Ensure HOME points to a writable directory for things like pyngrok and matplotlib
  export HOME="/app"
  mkdir -p "${HOME}/.config"
  chown -R "${UID}:${GID}" /app
  exec setpriv --reuid="$UID" --regid="$GID" --clear-groups -- "$@"
fi
exec "$@"
