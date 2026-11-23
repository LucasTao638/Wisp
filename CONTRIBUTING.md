# Contributing to Wisp

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Finding your way around

| File | What it does |
|---|---|
| `app.py` | Starts Wisp (setup screen on first run, then the UI) |
| `core.py` | The engine: handles every request, voice, timers, routines, briefing |
| `brain.py` | Talks to Claude Code (`claude -p`, kept running between requests) |
| `orb_ui.py`, `overlay.py`, `hud_draw.py`, `hud_menu.py` | The floating orb, full-screen HUD and menu |
| `voice.py` | Microphone, Whisper speech-to-text, wake phrase, text-to-speech |
| `timers.py`, `focus.py`, `routines.py`, `shortcuts.py` | Instant commands that don't need Claude |
| `context.py` | Screenshots / clipboard for "what's on my screen?" |
| `background.py` | Background jobs |
| `remote.py`, `remote_page.html` | Phone remote |
| `settings_ui.py`, `setup_wizard.py`, `ui_kit.py` | Settings and first-run screens |
| `updates.py`, `updater.py` | Update checks and safe installs |
| `telemetry.py` | Anonymous usage stats (read PRIVACY.md before changing) |
| `workspace/CLAUDE.md` | Claude's instructions: personality, safety rules, how to use Wisp's tools |

## Running from source
1. Windows 10/11, Python 3.13: `py -V:3.13 -m pip install -r requirements.txt`
2. Run `py -V:3.13 app.py` (or `text_mode.py` for a console version that shows errors).

## Guidelines
- Keep it friendly for non-technical users: plain-English messages, sensible defaults.
- Never log or send what people say, and never add new analytics without updating PRIVACY.md.
- Anything that could damage a user's PC or data must ask first.
- Test on Windows before opening a pull request, and describe what you tested.
