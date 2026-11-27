"""Small shared pieces for Wisp's windows: colours, switches, buttons, and saving settings."""
import json
import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont

import holo

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"

# colours come from the holographic design system (holo.py)
BG = holo.BG
CARD = holo.PANEL
TEXT = holo.TEXT
DIM = holo.DIM
RED = holo.RED
GREEN = holo.GREEN

VOICES = [
    ("en-GB-RyanNeural", "Ryan - British male"),
    ("en-GB-ThomasNeural", "Thomas - British male, deeper"),
    ("en-GB-SoniaNeural", "Sonia - British female"),
    ("en-AU-WilliamNeural", "William - Australian male"),
    ("en-AU-NatashaNeural", "Natasha - Australian female"),
    ("en-US-GuyNeural", "Guy - American male"),
    ("en-US-AriaNeural", "Aria - American female"),
]
VOICES_ZH = [
    ("zh-CN-YunxiNeural", "云希 - 男声，沉稳"),
    ("zh-CN-YunyangNeural", "云扬 - 男声，播音腔"),
    ("zh-CN-XiaoxiaoNeural", "晓晓 - 女声，温暖"),
    ("zh-CN-XiaoyiNeural", "晓伊 - 女声，活泼"),
    ("zh-TW-YunJheNeural", "雲哲 - 男声，台湾口音"),
]
WAKE_WORDS = [("hey_jarvis", "“Hey Jarvis”"), ("hey_mycroft", "“Hey Mycroft”"), ("alexa", "“Alexa”"),
              ("", "Off (use the hotkey or click the orb)")]
ACCENTS = ["#38d6ff", "#7c8cff", "#b48cff", "#ff6bb5", "#ff8a3d", "#3fd68c", "#e8eaed"]


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(changes):
    """Write only the given settings, keeping everything else in config.json as it is."""
    data = load_config()
    data.update(changes)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG)
    return data


def fonts(root, scale=1.0):
    return holo.fonts(root, scale)


def FlatButton(parent, text, command=None, bg=None, fg=None, hover=None, font=None, **kw):
    """A button in the holographic style. Accent-coloured buttons (dark text) become 'primary'."""
    kind = "primary" if fg in ("#031018", "#021016", holo.ON_ACCENT) else ("danger" if fg == "#ffb4b4" else "ghost")
    accent = bg if kind == "primary" and bg else holo.ACCENT
    try:
        parent_bg = parent.cget("bg")
    except Exception:
        parent_bg = BG
    return holo.Button(parent, text, command, kind=kind, font=font, accent=accent,
                       bg=parent_bg if kind != "primary" or not bg else parent_bg)


def Switch(parent, value=False, command=None, accent="#38d6ff", bg=None):
    return holo.Switch(parent, value, command, accent, bg)


def entry(parent, value="", show=None, width=30, f=None):
    return holo.entry(parent, value, show=show, width=width, font=f)


def open_url(url):
    webbrowser.open(url)


def open_file(path):
    import sysplat
    try:
        sysplat.open_target(str(path))  # opens in the default app
    except Exception as exc:
        print(f"(couldn't open {path}: {exc})")


def restart_wisp(root=None):
    """Start a fresh copy of Wisp, then close this one."""
    import sysplat
    sysplat.launch_wisp(ROOT)
    if root is not None:
        root.after(200, root.destroy)
