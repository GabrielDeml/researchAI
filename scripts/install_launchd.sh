#!/usr/bin/env bash
# Installs the researchAI launchd agents (supervisor + dashboard).
#
# This script only copies the plists into ~/Library/LaunchAgents and prints
# the launchctl commands to start/stop them -- it never invokes launchctl
# itself. Continuous 24/7 operation is a deliberate switch you flip by
# running the printed `launchctl bootstrap` commands yourself when ready.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHD_SRC="$REPO_ROOT/launchd"
LAUNCHD_DST="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

PLISTS=(
    com.gdeml.researchai.supervisor.plist
    com.gdeml.researchai.dashboard.plist
)

mkdir -p "$REPO_ROOT/logs"
mkdir -p "$LAUNCHD_DST"

for plist in "${PLISTS[@]}"; do
    cp "$LAUNCHD_SRC/$plist" "$LAUNCHD_DST/$plist"
    echo "Installed $LAUNCHD_DST/$plist"
done

echo
echo "Plists copied to ~/Library/LaunchAgents. Nothing has been started."
echo
echo "To start continuous operation, run:"
echo
for plist in "${PLISTS[@]}"; do
    label="${plist%.plist}"
    echo "  launchctl bootstrap gui/$UID_NUM \"$LAUNCHD_DST/$plist\""
    echo "  launchctl enable gui/$UID_NUM/$label"
done
echo
echo "To stop and uninstall:"
echo
for plist in "${PLISTS[@]}"; do
    label="${plist%.plist}"
    echo "  launchctl bootout gui/$UID_NUM/$label"
    echo "  rm \"$LAUNCHD_DST/$plist\""
done
