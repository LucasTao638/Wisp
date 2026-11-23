"""Everything about this copy of Wisp that the maintainer sets when publishing a release."""

APP_NAME = "Wisp"
VERSION = "1.0.0"

# Where updates come from: "<github-username>/<repo-name>". Change this before your first release.
GITHUB_REPO = "LucasTao638/Wisp"

# Anonymous usage stats (PostHog). Paste your PostHog *project* API key here (it starts with "phc_").
# It's safe to publish: it can only send events, not read them. Leave it as-is to send nothing.
POSTHOG_KEY = "phc_REPLACE_ME"
POSTHOG_HOST = "https://us.i.posthog.com"   # or https://eu.i.posthog.com if your PostHog project is in the EU


def repo_configured():
    return "YOUR-GITHUB" + "-USERNAME" not in GITHUB_REPO


def analytics_configured():
    return POSTHOG_KEY.startswith("phc_") and "REPLACE" not in POSTHOG_KEY


def parse_version(text):
    """'v1.2.3' -> (1, 2, 3)."""
    parts = []
    for piece in str(text).lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple((parts + [0, 0, 0])[:3])


MAC_DEFAULTS = {
    "talk_key": "alt_r",               # hold Right Option to talk
    "stop_key": "ctrl+alt+x",
    "show_hide_key": "ctrl+alt+space",
    "hud_key": "ctrl+alt+j",
    "auto_hide_fullscreen": False,     # (Windows-only feature)
}

MEMORY_TEMPLATE = """# Wisp memory
Things the user has asked me to remember, or lasting facts and preferences they've told me.
(You can edit this file yourself. Delete a line to make Wisp forget it.)

"""


def ensure_files():
    """Create this PC's own config.json and memory file from the defaults if they don't exist yet.
    (Your real ones are never part of the download, so updates and the public repo never contain your data.)"""
    import shutil
    from pathlib import Path
    root = Path(__file__).resolve().parent
    if not (root / "config.json").exists() and (root / "config.default.json").exists():
        shutil.copy2(root / "config.default.json", root / "config.json")
        import sys
        if sys.platform == "darwin":  # Mac keyboards: F-keys need Fn, and Ctrl+Shift combos clash less as Ctrl+Option
            import json
            cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
            cfg.update(MAC_DEFAULTS)
            (root / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    memory = root / "workspace" / "MEMORY.md"
    if not memory.exists():
        memory.parent.mkdir(parents=True, exist_ok=True)
        memory.write_text(MEMORY_TEMPLATE, encoding="utf-8")
