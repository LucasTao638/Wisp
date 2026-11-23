"""The full-screen HUD. Opens when you talk to Wisp (or press Ctrl+Shift+J), closes when it's done.

Two windows stacked on top of everything:
  - a dim layer that darkens the screen (click it to close the HUD)
  - the HUD itself: big orb, clock, system stats, activity, conversation and background jobs.
    Its empty areas are see-through.
It gets out of the way automatically when Claude needs to click around in your apps.
"""
import math
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

import background
import focus
import timers
from context import hide_from_screenshots
from hud_draw import KEY, bracket_panel, draw_orb, gauge, make_see_through, mix, orb_state, pick_fonts

PANEL = "#070b10"
TEXT = "#dfe7ef"
DIM = "#6b7785"
STATUS_WORDS = {"starting": "INITIALISING", "ready": "ONLINE", "listening": "LISTENING",
                "thinking": "PROCESSING", "speaking": "SPEAKING"}


# ---------- system stats (Windows, no extra installs) ----------
class SystemStats:
    def __init__(self):
        self.cpu = self.mem = self.battery = None
        self.charging = False
        self._last_times = None

    def _update_mac(self):
        _mac_stats(self)

    def update(self):
        if time.time() - getattr(self, "_at", 0) < 2:
            return
        self._at = time.time()
        if sys.platform == "darwin":
            self._update_mac()
            return
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        try:  # CPU: compare busy vs idle time since the last reading
            idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
            to_int = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            now = (to_int(idle), to_int(kern), to_int(user))
            if self._last_times:
                d_idle, d_kern, d_user = (a - b for a, b in zip(now, self._last_times, strict=True))
                total = d_kern + d_user
                if total > 0:
                    self.cpu = max(0.0, min(100.0, (total - d_idle) * 100 / total))
            self._last_times = now
        except Exception:
            pass
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD)] + \
                           [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f", "g")]
            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(m)
            k32.GlobalMemoryStatusEx(ctypes.byref(m))
            self.mem = float(m.dwMemoryLoad)
        except Exception:
            pass
        try:
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                            ("BatteryLifePercent", ctypes.c_ubyte), ("Reserved1", ctypes.c_byte),
                            ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]
            p = SYSTEM_POWER_STATUS()
            k32.GetSystemPowerStatus(ctypes.byref(p))
            self.battery = None if p.BatteryLifePercent == 255 or p.BatteryFlag & 128 else float(p.BatteryLifePercent)
            self.charging = p.ACLineStatus == 1
        except Exception:
            pass


def _run(cmd):
    import subprocess
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""


def _mac_stats(stats):
    import os
    import re
    try:  # CPU: load average vs number of cores (a good, cheap approximation)
        stats.cpu = min(100.0, os.getloadavg()[0] / (os.cpu_count() or 1) * 100)
    except OSError:
        pass
    vm = _run(["vm_stat"])
    total = _run(["sysctl", "-n", "hw.memsize"]).strip()
    page = re.search(r"page size of (\d+)", vm)
    if vm and total.isdigit() and page:
        pages = {k.strip().lower(): int(v.strip().rstrip(".")) for k, v in
                 (line.split(":", 1) for line in vm.splitlines()[1:] if ":" in line) if v.strip().rstrip(".").isdigit()}
        used = (pages.get("pages active", 0) + pages.get("pages wired down", 0)
                + pages.get("pages occupied by compressor", 0)) * int(page.group(1))
        stats.mem = min(100.0, used * 100 / int(total))
    batt = _run(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%", batt)
    stats.battery = float(m.group(1)) if m else None
    stats.charging = "AC Power" in batt or bool(re.search(r"(?<!dis)charging", batt))


def _hwnd(win):
    """The real Windows handle of a Tk window."""
    import ctypes
    return ctypes.windll.user32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()  # GA_ROOT


class FullHud:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.is_open = False
        self.dim = self.hud = None
        self.opened_at = 0.0
        self.last_activity = 0.0
        self.activity = []        # (time, text) of steps Claude took
        self.stats = SystemStats()
        self._jobs, self._jobs_at = [], 0.0
        self._fade = 0.0

    # ---------- open / close ----------
    def handles(self):
        """Windows handles of the HUD, so the 'fullscreen game' detector ignores them."""
        out = set()
        if self.is_open and sys.platform == "win32":
            for w in (self.dim, self.hud):
                try:
                    out.add(_hwnd(w))
                    out.add(w.winfo_id())
                except Exception:
                    pass
        return out

    def toggle(self):
        self.close() if self.is_open else self.open()

    def open(self):
        self.last_activity = time.time()
        if self.is_open:
            return
        root = self.app.root
        W, H = root.winfo_screenwidth(), root.winfo_screenheight()
        self.W, self.H = W, H
        self.u = u = H / 1080
        self.accent = self.app.accent

        self.dim = dim = tk.Toplevel(root)
        dim.overrideredirect(True)
        dim.configure(bg="#000000")
        dim.geometry(f"{W}x{H}+0+0")
        dim.attributes("-topmost", True)
        dim.attributes("-alpha", 0.0)
        dim.bind("<Button-1>", lambda e: self.close())

        self.hud = hud = tk.Toplevel(root)
        hud.overrideredirect(True)
        hud.configure(bg=KEY)
        hud.geometry(f"{W}x{H}+0+0")
        hud.attributes("-topmost", True)
        hud.attributes("-alpha", 0.0)
        for w in (dim, hud):
            hide_from_screenshots(w)  # so "what's on my screen?" sees your screen, not the HUD

        hudf, body = pick_fonts(tkfont)
        px = lambda n: -max(8, int(n * u))  # negative size = pixels, so it scales with the screen
        self.f_clock = tkfont.Font(family=hudf, size=px(64), weight="bold")
        self.f_status = tkfont.Font(family=hudf, size=px(20), weight="bold")
        self.f_title = tkfont.Font(family=hudf, size=px(13), weight="bold")
        self.f_caption = tkfont.Font(family=body, size=px(24))
        self.f_body = tkfont.Font(family=body, size=px(15))
        self.f_small = tkfont.Font(family=body, size=px(13))
        self.f_value = tkfont.Font(family=hudf, size=px(15), weight="bold")

        self.c = c = tk.Canvas(hud, width=W, height=H, bg=KEY, highlightthickness=0)
        make_see_through(hud, c)
        c.pack(fill="both", expand=True)
        self._layout()

        c.bind("<ButtonRelease-1>", self._click)
        for w in (dim, hud):
            w.bind("<Escape>", lambda e: self.close())
        self.is_open = True
        self.opened_at = time.time()
        import telemetry
        telemetry.feature("full_hud")
        self._fade = 0.0
        self.app.set_corner_visible(False)
        self._fade_in()
        hud.after(80, lambda: (hud.focus_force(), self.entry.focus_set()))
        self._tick()

    def close(self, reason=None):
        if not self.is_open:
            return
        self.is_open = False
        for w in (self.hud, self.dim):
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.dim = self.hud = None
        self.app.set_corner_visible(True)
        if reason:
            self.app.caption = reason

    def _fade_in(self):
        if not self.is_open:
            return
        self._fade = min(1.0, self._fade + 0.2)
        try:
            self.dim.attributes("-alpha", self.cfg.get("hud_dim", 0.55) * self._fade)
            self.hud.attributes("-alpha", self._fade)
        except tk.TclError:
            return
        if self._fade < 1:
            self.hud.after(25, self._fade_in)

    # ---------- layout ----------
    def _layout(self):
        c, W, H, u, A = self.c, self.W, self.H, self.u, self.accent
        self.cx, self.cy = W / 2, H * 0.40
        self.orb_s = 1.7 * u
        pw = 430 * u
        m = 40 * u
        self.panels = {
            "time": (m, m, m + pw, m + 190 * u),
            "system": (W - m - pw, m, W - m, m + 220 * u),
            "activity": (m, m + 220 * u, m + pw, H * 0.68),
            "chat": (W - m - pw, m + 250 * u, W - m, H * 0.74),
            "jobs": (m, H * 0.68 + 30 * u, m + pw, H - m - 30 * u),
        }
        for name, title in (("system", "System"), ("activity", "Activity"),
                            ("chat", "Conversation"), ("jobs", "Timers & jobs")):
            bracket_panel(c, *self.panels[name], A, PANEL, u, title, self.f_title)
        bracket_panel(c, *self.panels["time"], A, PANEL, u)

        # centre text + input
        cy_text = self.cy + 300 * u
        self.status_id = c.create_text(W / 2, cy_text, text="", font=self.f_status, fill=A, tags="static")
        self.step_id = c.create_text(W / 2, cy_text + 34 * u, text="", font=self.f_body, fill=DIM, tags="static")
        bw = 900 * u
        self.caption_bg = c.create_rectangle(W / 2 - bw / 2, cy_text + 58 * u, W / 2 + bw / 2,
                                             cy_text + 190 * u, fill=PANEL, outline="", tags="static")
        self.caption_id = c.create_text(W / 2, cy_text + 66 * u, text="", font=self.f_caption, fill=TEXT,
                                        width=bw - 40 * u, justify="center", anchor="n", tags="static")
        ew = 620 * u
        ey = cy_text + 222 * u
        c.create_rectangle(W / 2 - ew / 2 - 14 * u, ey - 22 * u, W / 2 + ew / 2 + 14 * u, ey + 22 * u,
                           fill=PANEL, outline=mix(PANEL, A, 0.45), tags="static")
        self.entry = tk.Entry(self.hud, bg=PANEL, fg=TEXT, bd=0, highlightthickness=0, insertbackground=A,
                              font=self.f_body, justify="center")
        c.create_window(W / 2, ey, window=self.entry, width=ew, height=32 * u)
        self.entry.bind("<Return>", lambda e: self._send())
        self.entry.bind("<Escape>", lambda e: self.close())
        self.entry.bind("<Key>", lambda e: setattr(self, "last_activity", time.time()))
        c.create_text(W / 2, ey + 40 * u, text="Type here, or just talk  ·  Esc to close",
                      font=self.f_small, fill=DIM, tags="static")

        # bottom-right hint + close button
        import hotkeys
        key = hotkeys.label(self.cfg.get("hud_key", "ctrl+shift+j"))
        wake = (self.cfg.get("wake_word") or "").replace("_", " ").title()
        hint = f"{key}  open / close" + (f"      Say “{wake}” to talk" if wake else "")
        c.create_text(W - m, H - m, text=hint, anchor="se", font=self.f_small, fill=DIM, tags="static")
        self.close_id = c.create_text(W / 2, m, text="✕", font=self.f_status, fill=DIM, tags="static")

    # ---------- interaction ----------
    def _click(self, e):
        self.last_activity = time.time()
        x1, y1, x2, y2 = self.c.bbox(self.close_id) or (0, 0, 0, 0)
        if x1 - 10 <= e.x <= x2 + 10 and y1 - 10 <= e.y <= y2 + 10:
            self.close()
            return
        if math.hypot(e.x - self.cx, e.y - self.cy) < 150 * self.orb_s and self.app.voice_on:
            self.app.assistant.toggle_listening()

    def _send(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.last_activity = time.time()
            self.app.assistant.submit(text)

    def on_event(self, kind, text):
        """Called by the app for every event while the HUD exists."""
        self.last_activity = time.time()
        if kind == "tool" and not text.startswith("took "):
            self.activity.append((time.strftime("%H:%M:%S"), self.app._friendly_step(text)))
            self.activity = self.activity[-30:]

    # ---------- every frame ----------
    def _tick(self):
        if not self.is_open:
            return
        t = time.time()
        c, u, A, app = self.c, self.u, self.accent, self.app
        c.delete("orb")
        status, colour, pulse, spin = orb_state(app, t)
        draw_orb(c, self.cx, self.cy, self.orb_s, colour, pulse, spin, t, app.ripples, tag="orb", detail=2)

        # scanning line sweeping down the screen
        sy = (t * 140 * u) % self.H
        c.create_line(0, sy, self.W, sy, fill=mix(KEY, A, 0.12), tags="orb")

        word = STATUS_WORDS.get(status, "ONLINE")
        if status in ("thinking", "starting"):
            word += "." * (int(t * 2.5) % 4)
        c.itemconfig(self.status_id, text="   ".join(word), fill=colour)
        c.itemconfig(self.step_id, text=app.step[:110])
        from classic_ui import clean_markdown
        caption = clean_markdown(app.caption)
        c.itemconfig(self.caption_id, text=caption if len(caption) < 320 else caption[:317] + "…")
        c.tag_lower("orb")

        if not hasattr(self, "_panels_at") or t - self._panels_at > 0.25:
            self._panels_at = t
            self._draw_panels(t)

        # close automatically once things have been quiet for a while
        idle_for = self.cfg.get("hud_auto_close_seconds", 8)
        a = app.assistant
        quiet = status == "ready" and not a.busy.is_set() and not a.is_listening and not a.is_speaking
        if idle_for and quiet and t - self.last_activity > idle_for and t - self.opened_at > 2:
            self.close()
            return
        if not quiet:
            self.last_activity = t
        self.hud.after(33, self._tick)

    def _draw_panels(self, t):
        c, u, A = self.c, self.u, self.accent
        c.delete("dyn")
        light = mix(PANEL, TEXT, 0.9)

        # time
        x1, y1, x2, y2 = self.panels["time"]
        c.create_text(x1 + 24 * u, y1 + 70 * u, text=time.strftime("%H:%M"), anchor="w",
                      font=self.f_clock, fill=A, tags="dyn")
        c.create_text(x1 + 24 * u, y1 + 125 * u, text=time.strftime("%A %d %B").upper(), anchor="w",
                      font=self.f_title, fill=light, tags="dyn")
        hour = time.localtime().tm_hour
        greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
        name = self.cfg.get("user_name")
        c.create_text(x1 + 24 * u, y1 + 155 * u, text=greet + (f", {name}" if name else "") + ".",
                      anchor="w", font=self.f_body, fill=DIM, tags="dyn")
        minutes = int(focus.focus_minutes_today())
        if minutes:
            c.create_text(x2 - 20 * u, y1 + 155 * u, text=f"{minutes} MIN FOCUS TODAY", anchor="e",
                          font=self.f_small, fill=A, tags="dyn")

        # system
        self.stats.update()
        x1, y1, x2, y2 = self.panels["system"]
        gx, gw = x1 + 20 * u, (x2 - x1) - 40 * u
        battery_label = "BATTERY" + (" (CHARGING)" if self.stats.charging and self.stats.battery is not None else "")
        for i, (label, val) in enumerate((("CPU", self.stats.cpu), ("MEMORY", self.stats.mem),
                                          (battery_label, self.stats.battery))):
            gauge(c, gx, y1 + (62 + i * 50) * u, gw, u, label, val, A, PANEL, self.f_value, self.f_small)

        # activity
        x1, y1, x2, y2 = self.panels["activity"]
        y = y1 + 52 * u
        lines = self.activity[-int((y2 - y1 - 60 * u) // (24 * u)):] or [("", "Nothing yet - ask me something.")]
        for when, what in lines:
            c.create_text(x1 + 18 * u, y, text=when, anchor="nw", font=self.f_small, fill=DIM, tags="dyn")
            c.create_text(x1 + 100 * u, y, text=what[:46], anchor="nw", font=self.f_small, fill=light, tags="dyn")
            y += 24 * u

        # conversation (newest at the bottom)
        x1, y1, x2, y2 = self.panels["chat"]
        from classic_ui import clean_markdown
        items = [(k, v) for k, v in self.app.log if k in ("user", "say", "alert")][-8:]
        y = y2 - 16 * u
        for kind, text in reversed(items):
            text = clean_markdown(text)
            text = text if len(text) < 160 else text[:157] + "…"
            tid = c.create_text(x1 + 18 * u, y, text=("YOU   " if kind == "user" else "") + text, anchor="sw",
                                width=x2 - x1 - 36 * u, font=self.f_small,
                                fill=mix(A, "#ffffff", 0.35) if kind == "user" else light, tags="dyn")
            bx1, by1, bx2, by2 = c.bbox(tid) or (0, y, 0, y)
            y = by1 - 10 * u
            if y < y1 + 50 * u:
                c.delete(tid)
                break

        # background jobs
        if t - self._jobs_at > 3:
            self._jobs_at = t
            try:
                self._jobs = background.list_jobs(limit=5)
            except Exception:
                self._jobs = []
        x1, y1, x2, y2 = self.panels["jobs"]
        y = y1 + 52 * u
        session = focus.session_text()
        if session:
            c.create_text(x1 + 18 * u, y, text="\u25c9", anchor="nw", font=self.f_value, fill=A, tags="dyn")
            c.create_text(x1 + 46 * u, y, text=session, anchor="nw", font=self.f_small, fill=light, tags="dyn")
            y += 28 * u
        for item in timers.upcoming()[:3]:  # timers first, with a live countdown
            left = item["due"] - time.time()
            name = item["label"] or item["kind"].title()
            when = timers.clock(left) if item["kind"] == "timer" or left < 3600 else timers.say_time(item["due"])
            c.create_text(x1 + 18 * u, y, text="\u23f1", anchor="nw", font=self.f_value, fill=A, tags="dyn")
            c.create_text(x1 + 46 * u, y, text=name[:30], anchor="nw", font=self.f_small, fill=light, tags="dyn")
            c.create_text(x2 - 18 * u, y, text=when, anchor="ne", font=self.f_value, fill=A, tags="dyn")
            y += 28 * u
        icons = {"done": ("✓", A), "failed": ("✗", "#ff6b6b"), "running": ("◌", "#ffb547"),
                 "queued": ("◌", "#ffb547")}
        if not self._jobs and not timers.upcoming():
            c.create_text(x1 + 18 * u, y, text='None. Try "set a timer for 10 minutes"', anchor="nw",
                          font=self.f_small, fill=DIM, tags="dyn")
        for job in self._jobs:
            if y > y2 - 24 * u:
                break
            icon, col = icons.get(job.get("status"), ("?", DIM))
            c.create_text(x1 + 18 * u, y, text=icon, anchor="nw", font=self.f_value, fill=col, tags="dyn")
            c.create_text(x1 + 46 * u, y, text=job["task"][:44], anchor="nw", font=self.f_small, fill=light, tags="dyn")
            y += 28 * u
