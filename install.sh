#!/usr/bin/env bash
# Installs a systemd USER timer that runs snapshot.py now and then every INTERVAL.
#
# Usage:
#   bash install.sh                      # refresh every 30 minutes, Dubai
#   bash install.sh 1h                   # refresh every hour
#   bash install.sh 2h --location london --size 2560x1440
#
# Remove with:
#   systemctl --user disable --now flight-radar.timer
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTERVAL="${1:-30min}"
shift || true
EXTRA_ARGS="$*"
UNIT_DIR="$HOME/.config/systemd/user"
PYTHON="$(command -v python3)"

mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/flight-radar.service" <<EOF
[Unit]
Description=Render the flight radar wallpaper

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_DIR
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%U/bus
ExecStart=$PYTHON $PROJECT_DIR/snapshot.py $EXTRA_ARGS
Nice=10
EOF

cat > "$UNIT_DIR/flight-radar.timer" <<EOF
[Unit]
Description=Refresh the flight radar wallpaper

[Timer]
OnBootSec=2min
OnUnitActiveSec=$INTERVAL

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now flight-radar.timer
systemctl --user start --no-block flight-radar.service

echo "Installed. Refreshing every $INTERVAL."
echo "Check the last run with: systemctl --user status flight-radar.service"
echo "Logs:                    journalctl --user -u flight-radar.service -n 30"
