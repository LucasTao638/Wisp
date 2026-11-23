"""Small shared pieces for Wisp's windows: colours, switches, buttons, and saving settings."""
import json
import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont

from classic_ui import FlatButton  # noqa: F401  (re-exported)

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"

BG = "#0a0e13"
CARD = "#121820"
TEXT = "#dfe7ef"
DIM = "#6b7785"
RED = "#ff6b6b"
GREEN = "#3fb950"

VOICES = [
    ("en-GB-RyanNeural", "Ryan - British male"),
    ("en-GB-ThomasNeural", "Thomas - British male, deeper"),
    ("en-GB-SoniaNeural", "Sonia - British female"),
    ("en-AU-WilliamNeural", "William - Australian male"),
    ("en-AU-NatashaNeural", "Natasha - Australian female"),
    ("en-US-GuyNeural", "Guy - American male"),
    ("en-US-AriaNeural", "Aria - American female"),
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
    fam = set(tkfont.families(root))
    hud = "Bahnschrift" if "Bahnschrift" in fam else ("Segoe UI" if "Segoe UI" in fam else "Helvetica")
    body = "Segoe UI" if "Segoe UI" in fam else "Helvetica"
    return {
        "title": tkfont.Font(root, family=hud, size=18, weight="bold"),
        "head": tkfont.Font(root, family=hud, size=11, weight="bold"),
        "body": tkfont.Font(root, family=body, size=11),
        "small": tkfont.Font(root, family=body, size=9),
        "big": tkfont.Font(root, family=hud, size=26, weight="bold"),
    }


class Switch(tk.Canvas):
    """An on/off switch that lights up in the accent colour."""

    def __init__(self, parent, value=False, command=None, accent="#38d6ff", bg=CARD):
        super().__init__(parent, width=46, height=26, bg=bg, highlightthickness=0, cursor="hand2")
        self.value, self.command, self.accent = bool(value), command, accent
        self.bind("<ButtonRelease-1>", lambda e: self.set(not self.value, notify=True))
        self._draw()

    def _draw(self):
        self.delete("all")
        track = self.accent if self.value else "#2a3340"
        self.create_oval(1, 1, 25, 25, fill=track, outline="")
        self.create_oval(21, 1, 45, 25, fill=track, outline="")
        self.create_rectangle(13, 1, 33, 25, fill=track, outline="")
        x = 23 if self.value else 3
        self.create_oval(x, 3, x + 20, 23, fill="#0a0e13" if self.value else "#c9d1da", outline="")

    def set(self, value, notify=False):
        self.value = bool(value)
        self._draw()
        if notify and self.command:
            self.command(self.value)

    def get(self):
        return self.value


def entry(parent, value="", show=None, width=30, f=None):
    e = tk.Entry(parent, bg="#1a222c", fg=TEXT, insertbackground=TEXT, bd=0, highlightthickness=1,
                 highlightbackground="#26303c", highlightcolor="#38d6ff", width=width, show=show, font=f)
    e.insert(0, value)
    return e


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
