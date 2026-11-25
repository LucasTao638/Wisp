"""Starts Wisp with the look chosen in config.json: "ui": "orb" (floating orb) or "classic" (chat window)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import app_info  # noqa: E402

app_info.ensure_files()

# The app runs without a console window, so there's nowhere for messages to go - and some packages
# (e.g. download progress bars) crash when they try to print. Send everything to a log file instead.
if sys.stdout is None or sys.stderr is None:
    log = open(ROOT / "wisp.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log
    print("\n===== Wisp started =====")

# Any crash, anywhere, gets written to wisp.log with the full details - so problems can be fixed.
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402


def _log_crash(kind, exc_type, exc, tb):
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {kind} crash:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))


sys.excepthook = lambda t, e, tb: _log_crash("main", t, e, tb)
threading.excepthook = lambda a: _log_crash(f"thread {a.thread.name if a.thread else ''}", a.exc_type, a.exc_value,
                                            a.exc_traceback)

cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

# The setup screen: on the first run, after installing (the installers pass --setup), or from the menu.
if (not cfg.get("setup_done") or "--setup" in sys.argv) and "--startup" not in sys.argv:
    try:
        from setup_wizard import SetupWizard
        SetupWizard().run()
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except Exception as exc:
        _log_crash("setup screen", type(exc), exc, exc.__traceback__)

if cfg.get("ui", "orb") == "classic":
    from classic_ui import WispApp
    WispApp().run()
else:
    from orb_ui import OrbApp
    OrbApp().run()
