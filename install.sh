#!/bin/bash
# Wisp installer for macOS (12 Monterey or newer; Apple Silicon or Intel).
#
# One-line install (Terminal):
#   curl -fsSL https://raw.githubusercontent.com/LucasTao638/Wisp/main/install.sh | bash
#
# Or, from an unzipped download: double-click "Install Wisp.command" (which runs this with --local).
#
# What it does: installs uv (which brings its own Python 3.13 - your system Python isn't touched),
# Wisp's packages, Claude Code (Wisp's brain), then creates ~/Applications/Wisp.app and opens it.
set -euo pipefail

REPO="LucasTao638/Wisp"
INSTALL_DIR="$HOME/Library/Application Support/Wisp"
APP="$HOME/Applications/Wisp.app"
LOCAL=0
[ "${1:-}" = "--local" ] && LOCAL=1

say()  { printf "\n\033[36m%s\033[0m\n" "$1"; }
ok()   { printf "\033[32m%s\033[0m\n" "$1"; }
fail() { printf "\n\033[31m%s\033[0m\n" "$1"; exit 1; }

[ "$(uname)" = "Darwin" ] || fail "This installer is for macOS. On Windows use install.ps1."

say "=== Installing Wisp ==="

# ---------- 1. Get the files ----------
if [ "$LOCAL" = 1 ]; then
    SRC="$(cd "$(dirname "$0")" && pwd)"
    say "[1/5] Using the files in $SRC"
else
    say "[1/5] Downloading the latest Wisp..."
    API="https://api.github.com/repos/$REPO/releases/latest"
    URL=$(curl -fsSL "$API" | grep -o '"browser_download_url": *"[^"]*mac[^"]*\.zip"' | head -1 | sed 's/.*"\(http[^"]*\)"/\1/')
    [ -n "$URL" ] || fail "Couldn't find a Mac download in the latest release."
    TMP="$(mktemp -d)"
    curl -fsSL "$URL" -o "$TMP/wisp.zip"
    (cd "$TMP" && ditto -x -k wisp.zip unpacked)
    SRC="$(dirname "$(find "$TMP/unpacked" -maxdepth 3 -name core.py | head -1)")"
    [ -f "$SRC/core.py" ] || fail "The download didn't look right."
fi

mkdir -p "$INSTALL_DIR"
if [ -f "$INSTALL_DIR/core.py" ] && [ "$SRC" != "$INSTALL_DIR" ]; then
    say "Wisp is already installed - updating it (your settings and memory are kept)."
    if [ "$LOCAL" = 1 ]; then
        TMPZ="$(mktemp -d)/wisp.zip"; (cd "$(dirname "$SRC")" && ditto -c -k --keepParent "$(basename "$SRC")" "$TMPZ")
    else
        TMPZ="$TMP/wisp.zip"
    fi
    "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/updater.py" "$TMPZ" || true
elif [ "$SRC" != "$INSTALL_DIR" ]; then
    rsync -a "$SRC/" "$INSTALL_DIR/"
fi
xattr -dr com.apple.quarantine "$INSTALL_DIR" 2>/dev/null || true
chmod +x "$INSTALL_DIR"/*.command "$INSTALL_DIR"/*.sh 2>/dev/null || true
ok "Files are in: $INSTALL_DIR"

# ---------- 2. uv + Python 3.13 ----------
say "[2/5] Setting up Python 3.13 (private to Wisp)..."
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
uv python install 3.13
if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
    uv venv --python 3.13 "$INSTALL_DIR/.venv"
fi
PY="$INSTALL_DIR/.venv/bin/python"

# ---------- 3. Packages ----------
say "[3/5] Installing Wisp's packages (voice, hotkeys)..."
uv pip install --python "$PY" -r "$INSTALL_DIR/requirements-mac.txt"

# ---------- 4. Claude Code ----------
say "[4/5] Installing Claude Code (Wisp's brain)..."
if ! command -v claude >/dev/null 2>&1; then
    curl -fsSL https://claude.ai/install.sh | bash
fi

# ---------- 5. Wisp.app ----------
say "[5/5] Creating Wisp.app..."
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/Wisp" <<LAUNCH
#!/bin/bash
export PATH="\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "$INSTALL_DIR"
exec "$PY" "$INSTALL_DIR/app.py" "\$@"
LAUNCH
chmod +x "$APP/Contents/MacOS/Wisp"
VERSION=$("$PY" -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); import app_info; print(app_info.VERSION)")
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Wisp</string>
  <key>CFBundleDisplayName</key><string>Wisp</string>
  <key>CFBundleIdentifier</key><string>com.wisp.assistant</string>
  <key>CFBundleExecutable</key><string>Wisp</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Wisp listens when you hold the talk key or say the wake phrase. Speech is turned into text on your Mac.</string>
  <key>NSAppleEventsUsageDescription</key><string>Wisp controls apps for you when you ask it to (for example playing music or opening files).</string>
</dict></plist>
PLIST
# app icon (a glowing ring, drawn with Pillow)
"$PY" - "$APP/Contents/Resources" <<'ICON' || true
import os, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter
out = sys.argv[1]
iconset = os.path.join(tempfile.mkdtemp(), "AppIcon.iconset")
os.makedirs(iconset)
def draw(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.06
    d.rounded_rectangle((pad, pad, size - pad, size - pad), radius=size * 0.22, fill=(7, 11, 16, 255))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    c, r = size / 2, size * 0.28
    g.ellipse((c - r, c - r, c + r, c + r), outline=(56, 214, 255, 255), width=max(2, int(size * 0.05)))
    g.ellipse((c - r * 0.45, c - r * 0.45, c + r * 0.45, c + r * 0.45), fill=(170, 238, 255, 255))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size * 0.03)))
    img.alpha_composite(glow)
    return img
for s in (16, 32, 64, 128, 256, 512):
    draw(s).save(os.path.join(iconset, f"icon_{s}x{s}.png"))
    draw(s * 2).save(os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(out, "AppIcon.icns")], check=True)
ICON
touch "$APP"
ok "Created $APP"

say "Done! Opening Wisp - the setup screen will ask for your Anthropic API key."
cat <<'NOTE'

macOS will ask for a few permissions the first time - please allow them:
  * Microphone            - so Wisp can hear you
  * Accessibility / Input Monitoring  - for the talk key and shortcuts
    (System Settings > Privacy & Security; turn on "Wisp", then reopen Wisp)
  * Automation            - when Wisp controls an app for you the first time
NOTE
open "$APP"
