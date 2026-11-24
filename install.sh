#!/bin/bash
# Wisp installer for macOS 12+ (beta).
#
# Easiest: unzip wisp-v…-mac.zip and double-click "Install Wisp.command".
# Or in Terminal:  curl -fsSL https://raw.githubusercontent.com/LucasTao638/Wisp/main/install.sh | bash
#
# What it does (no admin password, nothing system-wide):
#   1. asks where to put Wisp (suggested: ~/Library/Application Support/Wisp)
#   2. gets Python 3.13 + Wisp's packages in a private folder (using uv)
#   3. installs Claude Code (Wisp's brain) with Anthropic's official installer
#   4. makes ~/Applications/Wisp.app and opens it - the setup screen does the rest.
set -euo pipefail

REPO="LucasTao638/Wisp"
INSTALL_DIR="$HOME/Library/Application Support/Wisp"   # suggested; you can pick another (or set WISP_DIR)
APP="$HOME/Applications/Wisp.app"
LOCAL_BIN="$HOME/.local/bin"
export PATH="$LOCAL_BIN:$PATH"

say()  { printf "\033[36m%s\033[0m\n" "$*"; }
good() { printf "\033[32m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }
fail() { printf "\033[31m%s\033[0m\n" "$*"; exit 1; }

say ""
say "=== Installing Wisp ==="
say ""

# ---------- choosing where Wisp goes ----------
ask() {  # read an answer from the keyboard, even when this script is piped in from curl
  ANSWER=""
  if [ -r /dev/tty ]; then read -r -p "$1" ANSWER </dev/tty || true; fi
}
writable() { mkdir -p "$1" 2>/dev/null && touch "$1/.wisp-write-test" 2>/dev/null && rm -f "$1/.wisp-write-test"; }
pick_folder() {
  osascript -e 'POSIX path of (choose folder with prompt "Choose where to install Wisp. A \"Wisp\" folder will be made inside the one you pick.")' 2>/dev/null | sed 's#/$##'
}
saved_dir() {  # where an earlier install put Wisp (read from Wisp.app's launcher)
  [ -f "$APP/Contents/MacOS/Wisp" ] && sed -n 's/^DIR="\(.*\)"$/\1/p' "$APP/Contents/MacOS/Wisp" | head -1
}
choose_dir() {  # $1 = folder the installer is running from (offered as "keep it here"), may be empty
  if [ -n "${WISP_DIR:-}" ]; then INSTALL_DIR="$WISP_DIR"; return; fi
  local saved; saved="$(saved_dir || true)"
  if [ -n "$saved" ] && [ -f "$saved/core.py" ]; then
    say "Wisp is already installed in $saved - updating it there (your settings and memory are kept)."
    INSTALL_DIR="$saved"; return
  fi
  while true; do
    printf "Wisp will be installed to:  %s\n" "$INSTALL_DIR"
    local prompt="Press Enter to accept, or type C to choose another folder"
    [ -n "$1" ] && prompt="$prompt (or K to keep it in $1)"
    ask "$prompt: "
    local dir="$INSTALL_DIR"
    case "$ANSWER" in
      [Kk]*) [ -n "$1" ] && dir="$1" ;;
      [Cc]*) local picked; picked="$(pick_folder)"
             if [ -z "$picked" ]; then warn "No folder chosen."; continue; fi
             if [ "$(basename "$picked")" = "Wisp" ]; then dir="$picked"; else dir="$picked/Wisp"; fi ;;
    esac
    if writable "$dir"; then INSTALL_DIR="$dir"; return; fi
    warn "Can't save files in $dir. Please pick another folder."
  done
}

# ---------- 1. Wisp's files ----------
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/core.py" ]; then
  SOURCE="$SCRIPT_DIR"
  say "[1/4] Choosing where to install Wisp..."
  choose_dir "$SOURCE"
else
  say "[1/4] Downloading the latest Wisp..."
  TMP="$(mktemp -d)"
  URL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
        | grep -o '"browser_download_url": *"[^"]*mac[^"]*\.zip"' | head -1 | sed 's/.*"\(http[^"]*\)"/\1/')"
  [ -n "$URL" ] || fail "Couldn't find a Mac download in the latest release."
  curl -fsSL "$URL" -o "$TMP/wisp.zip"
  unzip -q "$TMP/wisp.zip" -d "$TMP/unpacked"
  SOURCE="$(dirname "$(find "$TMP/unpacked" -maxdepth 3 -name core.py | head -1)")"
  choose_dir ""
fi

mkdir -p "$INSTALL_DIR"
if [ "$(cd "$SOURCE" && pwd -P)" != "$(cd "$INSTALL_DIR" && pwd -P)" ]; then
  # Copies the program files only. Personal files (settings, memory) are never overwritten.
  (cd "$SOURCE" && tar cf - --exclude ".venv" --exclude "__pycache__" --exclude "config.json" \
     --exclude "*.log" --exclude "workspace/MEMORY.md" --exclude "jobs" .) | (cd "$INSTALL_DIR" && tar xf -)
fi
xattr -dr com.apple.quarantine "$INSTALL_DIR" 2>/dev/null || true
good "Wisp's files are in $INSTALL_DIR"

# ---------- 2. Python 3.13 + packages (private to Wisp) ----------
say "[2/4] Setting up Python 3.13 and Wisp's packages (a few minutes the first time)..."
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
command -v uv >/dev/null 2>&1 || fail "Couldn't install uv (the Python helper). Check your internet and try again."
VENV="$INSTALL_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  uv venv --quiet --python 3.13 "$VENV"
fi
uv pip install --quiet --python "$VENV/bin/python" -r "$INSTALL_DIR/requirements.txt"
"$VENV/bin/python" -c "import tkinter" 2>/dev/null || fail "Python's window toolkit (tkinter) is missing."
good "Python and packages are ready."

# ---------- 3. Claude Code ----------
say "[3/4] Installing Claude Code (Wisp's brain)..."
if [ -x "$LOCAL_BIN/claude" ] || command -v claude >/dev/null 2>&1; then
  good "Claude Code is already installed."
else
  if curl -fsSL https://claude.ai/install.sh | bash; then :; fi
  if [ -x "$LOCAL_BIN/claude" ] || command -v claude >/dev/null 2>&1; then
    good "Claude Code is installed."
  else
    warn "Claude Code didn't install here - no problem, Wisp's setup screen has an 'Install it for me' button."
  fi
fi
# so the 'claude' command also works when you open Terminal yourself
for RC in "$HOME/.zshrc" "$HOME/.bash_profile"; do
  if ! grep -qs '.local/bin' "$RC"; then
    printf '\n# Added by Wisp so the claude command works\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$RC"
  fi
done

# ---------- 4. Wisp.app ----------
say "[4/4] Making Wisp.app..."
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
{
  echo '#!/bin/bash'
  echo '# Starts Wisp. Going through this app keeps macOS permissions (microphone etc.) attached to "Wisp".'
  printf 'DIR="%s"\n' "$INSTALL_DIR"
  echo 'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"'
  echo 'cd "$DIR" && exec "$DIR/.venv/bin/python" "$DIR/app.py" "$@"'
} > "$APP/Contents/MacOS/Wisp"
chmod +x "$APP/Contents/MacOS/Wisp"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Wisp</string>
  <key>CFBundleDisplayName</key><string>Wisp</string>
  <key>CFBundleIdentifier</key><string>com.wisp.assistant</string>
  <key>CFBundleExecutable</key><string>Wisp</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSMicrophoneUsageDescription</key><string>Wisp listens when you hold the talk key or say the wake phrase.</string>
  <key>NSAppleEventsUsageDescription</key><string>Wisp controls apps when you ask it to.</string>
</dict></plist>
PLIST
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
good "Wisp is in your Applications folder (in your home folder)."

say ""
good "Done! Opening Wisp - its setup screen connects Claude. No more typing commands."
say "macOS will ask to allow the Microphone, Accessibility and Automation for Wisp: allow them, then reopen Wisp."
open "$APP"
