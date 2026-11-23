"""Safely update Wisp from a new wisp.zip - without touching your stuff.

Use it: drag the new wisp.zip onto update.bat (or run update.bat and it finds the newest
wisp*.zip in this folder or your Downloads).

What it does:
  - backs up every file it's about to replace into backups/<date-time>/
  - updates the program files
  - NEVER overwrites your data: memory, timers, scroll guard stats, paired phones, routines, jobs,
    projects, outputs, conversation state, log
  - config.json: keeps all YOUR settings, and only adds any new settings from the update
"""
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Your data - never replaced by an update
PROTECTED_FILES = {"config.json", "state.json", "timers.json", "focus.json", "phone.json", "routines.json",
                   "wisp.log", "sidekick.log", "workspace/MEMORY.md", "telemetry.json", "secrets.bin"}
PROTECTED_DIRS = {"jobs", "backups", "workspace/projects", "workspace/output", ".venv"}
# Files from older versions that aren't used any more
REMOVED_FILES = ["focus_card.py", "jarvis_ui.py", "sidekick.py"]


def migrate(backup):
    """Small fixes to your data when a feature changes."""
    for rel in REMOVED_FILES:
        f = ROOT / rel
        if f.exists():
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), backup / rel)
            print(f"  removed {rel} (no longer used)")
    routines_file = ROOT / "routines.json"
    if routines_file.exists():  # the scroll guard was removed: drop its steps from your routines
        try:
            data = json.loads(routines_file.read_text(encoding="utf-8"))
            changed = False
            for r in data.values():
                steps = r.get("steps", [])
                kept = [s for s in steps if not (isinstance(s, dict) and "scroll_guard" in s)]
                for s in kept:
                    if isinstance(s, dict) and isinstance(s.get("say"), str) and "croll guard" in s["say"]:
                        s["say"] = (s["say"].replace(" Scroll guard off, launching", " Launching")
                                    .replace(" Scroll guard is locked on.", "").strip())
                        changed = True
                if len(kept) != len(steps):
                    r["steps"] = kept
                    changed = True
            if changed:
                routines_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                print("  routines.json: removed scroll guard steps")
        except (OSError, json.JSONDecodeError, AttributeError):
            pass


def find_zip(arg=None):
    if arg:
        p = Path(arg.strip('"'))
        return p if p.exists() else None
    candidates = [z for folder in (ROOT, Path.home() / "Downloads") for pattern in ("wisp*.zip", "sidekick*.zip")
                  for z in folder.glob(pattern)]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _is_protected(rel):
    rel = rel.replace("\\", "/")
    return rel in PROTECTED_FILES or any(rel == d or rel.startswith(d + "/") for d in PROTECTED_DIRS)


def merge_config(new_cfg_path):
    """Add settings that are new in the update; keep every value you've set."""
    mine_path = ROOT / "config.json"
    try:
        mine = json.loads(mine_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        mine = {}
    new = json.loads(Path(new_cfg_path).read_text(encoding="utf-8"))
    added = [k for k in new if k not in mine]
    merged = dict(mine)
    for k in added:
        merged[k] = new[k]
    mine_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return added


def update(zip_path):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = ROOT / "backups" / stamp
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        src = Path(tmp)
        # the zip may contain a top-level "wisp" folder
        inner = [p for p in src.iterdir() if p.is_dir()]
        if not (src / "core.py").exists() and len(inner) == 1 and (inner[0] / "core.py").exists():
            src = inner[0]
        if not (src / "core.py").exists():
            print("That zip doesn't look like Wisp (no core.py inside).")
            return False

        updated, skipped = [], []
        for f in src.rglob("*"):
            if f.is_dir() or "__pycache__" in f.parts:
                continue
            rel = f.relative_to(src).as_posix()
            dest = ROOT / rel
            if rel == "config.default.json":  # new settings from the update get added to your config.json
                added = merge_config(f)
                if added:
                    print(f"  config.json: added new settings {', '.join(added)}")
            if _is_protected(rel):
                if rel == "config.json":
                    added = merge_config(f)
                    if added:
                        print(f"  config.json: added new settings {', '.join(added)}")
                elif rel == "workspace/MEMORY.md" and not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)  # first install: create the empty memory file
                else:
                    skipped.append(rel)
                continue
            if dest.exists():
                if dest.read_bytes() == f.read_bytes():
                    continue
                (backup / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup / rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            updated.append(rel)

    migrate(backup)
    _fix_permissions()
    try:
        import importlib
        import app_info
        importlib.reload(app_info).ensure_files()
    except Exception:
        pass
    print(f"\nUpdated {len(updated)} file{'s' if len(updated) != 1 else ''}" + (":" if updated else "."))
    for rel in updated:
        print(f"  {rel}")
    if updated and backup.exists():
        print(f"\nOld versions are saved in backups\\{stamp} in case you need them.")
    print("Your memory, settings, timers, routines, phones and projects were left alone.")
    return True


def _wait_for_exit(pid, timeout=60):
    """Wait for Wisp to close before replacing its files."""
    if sys.platform != "win32":
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)  # still running?
            except OSError:
                break
            time.sleep(0.5)
        time.sleep(1)
        return
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle:
        ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000))
        ctypes.windll.kernel32.CloseHandle(handle)
    time.sleep(1)


def _restart():
    import sysplat
    sysplat.launch_wisp(ROOT)


def _fix_permissions():
    """Zip files lose the 'executable' flag; put it back on the Mac/Linux scripts."""
    if sys.platform == "win32":
        return
    for pattern in ("*.command", "*.sh"):
        for f in ROOT.glob(pattern):
            f.chmod(0o755)


def _install_requirements():
    """Install any new packages the update needs."""
    import shutil
    import subprocess
    mac = sys.platform == "darwin"
    reqs = ROOT / ("requirements-mac.txt" if mac else "requirements.txt")
    python = sys.executable.replace("pythonw.exe", "python.exe")
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if mac and Path(uv).exists():  # the Mac install uses uv (its Python has no pip)
        cmd = [uv, "pip", "install", "--python", python, "-q", "-r", str(reqs)]
    else:
        cmd = [python, "-m", "pip", "install", "-q", "-r", str(reqs)]
    try:
        subprocess.run(cmd, timeout=600, capture_output=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
    except Exception as exc:
        print(f"(couldn't install new packages: {exc})")


if __name__ == "__main__":
    args = sys.argv[1:]
    wait_pid = int(args[args.index("--wait-pid") + 1]) if "--wait-pid" in args else None
    restart = "--restart" in args
    zip_arg = next((a for a in args if not a.startswith("--") and not a.isdigit()), None)
    if restart and (sys.stdout is None or sys.stderr is None):  # started in the background: log instead
        log = open(ROOT / "wisp.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    z = find_zip(zip_arg)
    if not z:
        print("Couldn't find a wisp zip. Drag the new wisp.zip onto update.bat,")
        print("or put it in this folder or your Downloads folder.")
        sys.exit(1)
    if wait_pid:
        _wait_for_exit(wait_pid)
    print(f"Updating from {z}\n")
    ok = update(z)
    if ok and restart:
        _install_requirements()
        _restart()
    sys.exit(0 if ok else 1)
