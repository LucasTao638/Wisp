"""Anonymous usage stats - helps the developer see whether people keep using Wisp and which features matter.

ON by default; turn it off any time: right-click the orb > "Share anonymous usage stats", in Settings,
or set "share_usage_stats": false in config.json. Full details: PRIVACY.md.

What's sent (and ONLY this):
  - a random ID made on your PC (not linked to you, your name, account or hardware)
  - Wisp's version, your Windows version, and the look you use (orb / classic)
  - "Wisp was opened" and "Wisp was used today" (this is how retention is measured)
  - which kind of feature was used, e.g. "timer", "routine", "ask Claude" - a feature name and nothing else
What's NEVER sent: anything you say or type, Claude's replies, file names, screenshots, clipboard, your
location, IP-derived location (disabled below), or your API key.
"""
import json
import platform
import queue
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import app_info

ROOT = Path(__file__).resolve().parent
FILE = ROOT / "telemetry.json"

FEATURES = {"ask_claude", "background_job", "timer", "routine", "routine_created", "focus_session", "screen",
            "clipboard", "briefing", "wake_word", "push_to_talk", "typed", "phone_remote", "full_hud",
            "shortcut", "update_installed"}

_queue = queue.Queue()
_started = False
_cfg = {}


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data):
    FILE.write_text(json.dumps(data), encoding="utf-8")


def install_id():
    data = _load()
    if not data.get("id"):
        data["id"] = str(uuid.uuid4())
        data["first_seen"] = time.strftime("%Y-%m-%d")
        _save(data)
    return data["id"]


def enabled():
    return app_info.analytics_configured() and _cfg.get("share_usage_stats", True)


def start(cfg):
    """Call once when Wisp starts."""
    global _started, _cfg
    _cfg = cfg
    if _started:
        return
    _started = True
    threading.Thread(target=_sender, daemon=True).start()
    track("app_opened", {"ui": cfg.get("ui", "orb")})
    data = _load()
    if data.get("last_version") != app_info.VERSION:  # first run, or just updated
        if data.get("last_version"):
            track("app_updated", {"from_version": data["last_version"]})
        else:
            track("app_installed")
        data["last_version"] = app_info.VERSION
        _save(data)
    _daily()


def _daily():
    """One 'active today' event per day - this is what retention charts are built from."""
    data = _load()
    today = time.strftime("%Y-%m-%d")
    if data.get("last_active") != today:
        data["last_active"] = today
        _save(data)
        track("daily_active")
    timer = threading.Timer(3600, _daily)  # check again in an hour (Wisp often runs for days)
    timer.daemon = True  # never keeps Wisp running after you quit
    timer.start()


def feature(name):
    if name in FEATURES:
        track("feature_used", {"feature": name})


def track(event, props=None):
    if not enabled():
        return
    properties = {
        "app_version": app_info.VERSION,
        "os": f"{platform.system()} {platform.release()}",
        "$process_person_profile": False,  # anonymous: no user profiles
        "$ip": None,                        # don't record or geolocate the IP address
        "$geoip_disable": True,
    }
    properties.update(props or {})
    _queue.put({"event": event, "distinct_id": install_id(), "properties": properties,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


def _sender():
    """Sends in the background, in small batches. Never slows Wisp down; failures are silently dropped."""
    while True:
        batch = [_queue.get()]
        time.sleep(2)
        while not _queue.empty() and len(batch) < 50:
            batch.append(_queue.get_nowait())
        if not enabled():
            continue
        body = json.dumps({"api_key": app_info.POSTHOG_KEY, "batch": batch}).encode()
        req = urllib.request.Request(f"{app_info.POSTHOG_HOST}/batch/", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass


def set_enabled(cfg, on):
    """Turn sharing on/off (saved to config.json)."""
    cfg["share_usage_stats"] = bool(on)
    path = ROOT / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["share_usage_stats"] = bool(on)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass
    if not on:
        while not _queue.empty():  # drop anything not yet sent
            try:
                _queue.get_nowait()
            except queue.Empty:
                break
