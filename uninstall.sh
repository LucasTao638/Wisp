#!/bin/bash
# Removes Wisp from this Mac. (Also: Wisp's Settings > System > Uninstall Wisp.)
# Claude Code and uv stay installed - other apps may use them.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/Applications/Wisp.app"
PLIST="$HOME/Library/LaunchAgents/com.wisp.assistant.plist"

echo ""
echo "=== Uninstalling Wisp ==="
echo "This removes Wisp.app, stops Wisp starting at login, and deletes Wisp's files in:"
echo "  $DIR"
echo ""
read -r -p "Also delete your settings and Wisp's memory? (y = delete everything / n = keep them) [n]: " ALL

pkill -f "$DIR/app.py" 2>/dev/null || true
if [ -f "$PLIST" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
fi
rm -rf "$APP"

case "$ALL" in
  [Yy]*)
    rm -rf "$DIR"
    echo "Wisp has been removed completely."
    ;;
  *)
    # keep only your own files: settings, memory, saved jobs and projects
    KEEP="config.json telemetry.json state.json timers.json focus.json phone.json routines.json feedback_outbox.json workspace jobs backups"
    TMP="$(mktemp -d)"
    for f in $KEEP; do [ -e "$DIR/$f" ] && mv "$DIR/$f" "$TMP/"; done
    rm -rf "$DIR"
    mkdir -p "$DIR"
    for f in "$TMP"/*; do [ -e "$f" ] && mv "$f" "$DIR/"; done
    rm -rf "$TMP"
    find "$DIR/workspace" -maxdepth 1 -type f ! -name "MEMORY.md" -delete 2>/dev/null || true
    echo "Wisp has been removed. Your settings and memory are kept in:"
    echo "  $DIR"
    echo "(Reinstalling Wisp there picks them up again. Delete the folder to remove them too.)"
    ;;
esac
echo ""
