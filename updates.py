"""Checks GitHub for new versions of Wisp, and installs them with one click.

A release is a GitHub Release tagged like v1.2.0 with a wisp-*.zip attached (the GitHub Action in
.github/workflows/release.yml builds that zip automatically when you push a tag).
Installing an update closes Wisp, runs updater.py (which never touches your data), and restarts Wisp.
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import app_info

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com/repos/{repo}/releases/latest"


def check():
    """Returns {"version", "notes", "url", "page"} if a newer release exists, else None."""
    if not app_info.repo_configured():
        return None
    req = urllib.request.Request(API.format(repo=app_info.GITHUB_REPO),
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": f"Wisp/{app_info.VERSION}"})
    with urllib.request.urlopen(req, timeout=15) as res:
        rel = json.loads(res.read())
    if rel.get("draft") or rel.get("prerelease"):
        return None
    latest = rel.get("tag_name", "")
    if app_info.parse_version(latest) <= app_info.parse_version(app_info.VERSION):
        return None
    zips = [a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".zip")]
    mine = "mac" if sys.platform == "darwin" else "windows"
    asset = next((a for a in zips if mine in a["name"].lower()), None) \
        or next((a for a in zips if "mac" not in a["name"].lower() and "windows" not in a["name"].lower()), None)
    return {"version": latest.lstrip("vV"), "notes": (rel.get("body") or "").strip()[:1500],
            "url": asset["browser_download_url"] if asset else None, "page": rel.get("html_url")}


class UpdateChecker:
    """Checks shortly after start, then twice a day. Calls on_found(info) once per new version."""

    def __init__(self, on_found):
        self.on_found = on_found
        self.found = None
        self._announced = None

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def check_now(self):
        try:
            info = check()
        except Exception as exc:
            print(f"(update check failed: {exc})")
            return None
        self.found = info
        if info and info["version"] != self._announced:
            self._announced = info["version"]
            self.on_found(info)
        return info

    def _loop(self):
        time.sleep(20)
        while True:
            self.check_now()
            time.sleep(12 * 3600)


def install(info, on_progress=print):
    """Download the release zip and hand over to updater.py, which waits for Wisp to close,
    updates, then starts Wisp again. Returns True if the handover started (the caller should then quit)."""
    if not info or not info.get("url"):
        on_progress("This release has no download attached.")
        return False
    on_progress(f"Downloading Wisp {info['version']}…")
    target = Path(tempfile.gettempdir()) / f"wisp-{info['version']}.zip"
    req = urllib.request.Request(info["url"], headers={"User-Agent": f"Wisp/{app_info.VERSION}"})
    with urllib.request.urlopen(req, timeout=120) as res, open(target, "wb") as f:
        while chunk := res.read(65536):
            f.write(chunk)
    on_progress("Installing… Wisp will restart in a moment.")
    import sysplat
    cmd = [sysplat.python_gui_exe(), str(ROOT / "updater.py"), str(target), "--wait-pid", str(os.getpid()), "--restart"]
    sysplat.popen_detached(cmd, cwd=ROOT)  # detached, so it outlives Wisp
    return True
