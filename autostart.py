"""Start Wisp automatically when you log in to Windows (it starts hidden in the tray).

Works by putting a shortcut in your Startup folder. Also usable from Command Prompt:
    py -V:3.13 autostart.py on     |     py -V:3.13 autostart.py off
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _startup_folder():
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


SHORTCUT = _startup_folder() / "Wisp.lnk"
OLD_SHORTCUT = _startup_folder() / "Sidekick.lnk"  # from before the rename


def is_enabled():
    return SHORTCUT.exists() or OLD_SHORTCUT.exists()


def migrate():
    """Replace the old Sidekick startup shortcut with a Wisp one."""
    if OLD_SHORTCUT.exists():
        try:
            OLD_SHORTCUT.unlink()
        except OSError:
            return
        enable()


def _pythonw():
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def enable():
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SK_LINK);"
        "$s.TargetPath = $env:SK_TARGET; $s.Arguments = $env:SK_ARGS;"
        "$s.WorkingDirectory = $env:SK_DIR; $s.Description = 'Wisp AI assistant'; $s.Save()"
    )
    env = dict(os.environ, SK_LINK=str(SHORTCUT), SK_TARGET=_pythonw(),
               SK_ARGS=f'"{ROOT / "app.py"}" --startup', SK_DIR=str(ROOT))
    SHORTCUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=False,
                   creationflags=0x08000000 if sys.platform == "win32" else 0)
    return is_enabled()


def disable():
    for shortcut in (SHORTCUT, OLD_SHORTCUT):
        try:
            shortcut.unlink()
        except FileNotFoundError:
            pass
    return not is_enabled()


def set_enabled(on):
    return enable() if on else disable()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("on", "off"):
        set_enabled(sys.argv[1] == "on")
    print("Start with Windows is", "ON" if is_enabled() else "OFF")
