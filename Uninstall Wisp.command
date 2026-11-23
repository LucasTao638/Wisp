#!/bin/bash
# Removes Wisp from your Mac. Asks before deleting your settings and memory.
pkill -f "Library/Application Support/Wisp/app.py" 2>/dev/null
rm -rf "$HOME/Applications/Wisp.app"
rm -f "$HOME/Library/LaunchAgents/com.wisp.assistant.plist"
security delete-generic-password -s "Wisp - Anthropic API key" >/dev/null 2>&1
echo "Wisp.app, start-at-login and your saved API key are removed."
read -r -p "Also delete your Wisp settings, memory and files? (y/N) " answer
if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    rm -rf "$HOME/Library/Application Support/Wisp"
    echo "Deleted."
else
    echo "Kept in: $HOME/Library/Application Support/Wisp"
fi
read -n 1 -s -r -p "Press any key to close this window."
