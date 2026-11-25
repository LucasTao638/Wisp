"""The side widget: a small panel that appears beside the orb while you talk to Wisp.

Unlike the full-screen HUD it doesn't dim the screen or take over the middle of it. It shows:
  - what Wisp is doing (listening / thinking / speaking), with a live mic meter while listening
  - what it heard you say, the step it's on, and its reply
  - a Stop button that interrupts everything (same as F10, Esc, or saying "stop")
It tucks itself away a few seconds after Wisp has finished (not while your mouse is over it).
"""
import re
import sys
import time
import tkinter as tk

import ui_kit as ui
from context import hide_from_screenshots
from i18n import L

PANEL = "#0d1319"
LINE = "#1f2a35"
SOFT = "#cfe2ee"


class TalkWidget:
    WIDTH = 340

    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.accent = app.accent
        self.s = app.s
        self.win = None
        self.state = "ready"
        self.compact = False         # Claude is clicking around in your apps: keep out of the way
        self.hovered = False
        self._hide_job = None
        self._fade = 0.0

    @property
    def is_open(self):
        return self.win is not None

    # ---------- building ----------
    def _build(self):
        s, a = self.s, self.app
        self.win = win = tk.Toplevel(a.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=LINE)
        try:
            win.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        card = tk.Frame(win, bg=PANEL, padx=int(16 * s), pady=int(12 * s))
        card.pack(fill="both", expand=True, padx=1, pady=1)   # the 1px gap shows LINE as a thin border
        self.card = card

        head = tk.Frame(card, bg=PANEL)
        head.pack(fill="x")
        self.dot = tk.Canvas(head, width=int(10 * s), height=int(10 * s), bg=PANEL, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, int(8 * s)))
        self.state_label = tk.Label(head, bg=PANEL, fg=self.accent, font=a.f_status, anchor="w")
        self.state_label.pack(side="left")
        close = tk.Label(head, text="✕", bg=PANEL, fg=ui.DIM, font=a.f_small, cursor="hand2")
        close.pack(side="right")
        close.bind("<ButtonRelease-1>", lambda e: self.hide())

        self.meter = tk.Canvas(card, height=int(22 * s), bg=PANEL, highlightthickness=0)
        wrap = int((self.WIDTH - 34) * s)
        self.you = tk.Label(card, bg=PANEL, fg=SOFT, font=a.f_caption, anchor="w", justify="left", wraplength=wrap)
        self.step = tk.Label(card, bg=PANEL, fg=ui.DIM, font=a.f_small, anchor="w", justify="left", wraplength=wrap)
        self.reply = tk.Label(card, bg=PANEL, fg=ui.TEXT, font=a.f_body, anchor="w", justify="left", wraplength=wrap)

        self.bottom = tk.Frame(card, bg=PANEL)
        self.stop_btn = ui.FlatButton(self.bottom, L("■  Stop", "■  停止"), self.stop, bg="#3a1d22",
                                      fg="#ffb4b4", hover="#552830", font=a.f_small)
        import hotkeys
        stop_key = hotkeys.label(self.cfg.get("stop_key", "f10"))
        self.hint = tk.Label(self.bottom, text=L(f"or press {stop_key}, or say “stop”", f"或按 {stop_key}，或说“停”"),
                             bg=PANEL, fg=ui.DIM, font=a.f_small)

        for w in (win, card):
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))
        try:
            hide_from_screenshots(win)  # Claude's screenshots should show your screen, not Wisp
        except Exception:
            pass
        if sys.platform == "win32":
            self._round_corners()
        self.you_text = self.step_text = self.reply_text = ""
        self.reply_colour = ui.TEXT
        self._render()
        self._tick()

    def _round_corners(self):
        try:  # Windows 11: rounded corners on a borderless window
            import ctypes
            from overlay import _hwnd
            self.win.update_idletasks()
            value = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(_hwnd(self.win), 33, ctypes.byref(value), 4)
        except Exception:
            pass

    # ---------- showing / hiding ----------
    def show(self):
        self._cancel_hide()
        if self.win is None:
            self._build()
        self._place()
        self._fade_to(0.97)

    def hide(self):
        self._cancel_hide()
        if self.win is not None:
            self._fade_to(0.0, then=self._destroy)

    def _destroy(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None
        self.compact = False

    def _fade_to(self, target, then=None):
        def step():
            if self.win is None:
                return
            self._fade += 0.2 if target > self._fade else -0.2
            done = (target > 0 and self._fade >= target) or (target == 0 and self._fade <= 0)
            self._fade = max(0.0, min(target if target > 0 else 1.0, self._fade))
            try:
                self.win.attributes("-alpha", self._fade)
            except tk.TclError:
                return
            if done:
                if then:
                    then()
            else:
                self.win.after(16, step)
        step()

    def _schedule_hide(self):
        self._cancel_hide()
        if self.win is not None and not self.hovered:
            self._hide_job = self.win.after(int(self.cfg.get("widget_hide_seconds", 8) * 1000), self._auto_hide)

    def _auto_hide(self):
        a = self.app.assistant
        if self.hovered or a.busy.is_set() or a.is_listening or a.is_speaking:
            return
        self.hide()

    def _cancel_hide(self):
        if self._hide_job and self.win is not None:
            try:
                self.win.after_cancel(self._hide_job)
            except tk.TclError:
                pass
        self._hide_job = None

    def _hover(self, inside):
        self.hovered = inside
        if inside:
            self._cancel_hide()
        elif self.state == "ready":
            self._schedule_hide()

    def _place(self):
        """Bottom-right, just to the left of the orb (or in the corner if the orb is hidden)."""
        if self.win is None:
            return
        a, s = self.app, self.s
        self.win.update_idletasks()
        w = int(self.WIDTH * s)
        h = self.win.winfo_reqheight()
        _, _, right, bottom = a._work_area()
        if not a.hidden and a.corner_visible:
            x = a.root.winfo_x() + int(a.W / 2 - 70 * s) - w   # beside the orb itself, not its whole window
        else:
            x = right - w - int(16 * s)
        x = max(int(8 * s), x)
        y = bottom - h - int(16 * s)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    # ---------- what's shown ----------
    STATES = {
        "listening": (("Listening…", "正在听……"), "#38d6ff"),
        "thinking": (("Thinking…", "正在思考……"), "#f2c94c"),
        "speaking": (("Speaking", "正在说话"), "#7ee787"),
        "ready": (("Done", "完成"), "#6b7785"),
    }

    def _render(self):
        if self.win is None:
            return
        (en, zh), colour = self.STATES.get(self.state, self.STATES["ready"])
        if self.compact and self.state == "thinking":
            en, zh = "Working in your apps…", "正在操作你的应用……"
        self.state_label.config(text=L(en, zh).upper(), fg=colour)
        self._dot_colour = colour

        for w in (self.meter, self.you, self.step, self.reply, self.bottom):
            w.pack_forget()
        pad = (int(8 * self.s), 0)
        if self.state == "listening":
            self.meter.pack(fill="x", pady=pad)
        if self.you_text and not self.compact:
            self.you.config(text=f"“{self.you_text}”")
            self.you.pack(fill="x", pady=pad)
        if self.step_text and self.state == "thinking":
            self.step.config(text="› " + self.step_text)
            self.step.pack(fill="x", pady=pad)
        if self.reply_text and not self.compact:
            text = self.reply_text if len(self.reply_text) < 420 else self.reply_text[:417] + "…"
            self.reply.config(text=text, fg=self.reply_colour)
            self.reply.pack(fill="x", pady=pad)
        if self.state in ("listening", "thinking", "speaking"):
            self.stop_btn.config(text=L("■  Cancel", "■  取消") if self.state == "listening"
                                 else L("■  Stop", "■  停止"))
            self.stop_btn.pack(side="left")
            if not self.compact:
                self.hint.pack(side="left", padx=(int(10 * self.s), 0))
            self.bottom.pack(fill="x", pady=(int(12 * self.s), 0))
        self._place()

    def _tick(self):
        """Animates the status dot and the mic meter."""
        if self.win is None:
            return
        s, now = self.s, time.time()
        d = self.dot
        d.delete("all")
        size = int(10 * s)
        pulse = 0.65 + 0.35 * abs(((now * 1.6) % 2) - 1) if self.state != "ready" else 1.0
        r = size / 2 * pulse
        d.create_oval(size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r, fill=self._dot_colour, outline="")
        if self.state == "listening":
            m = self.meter
            m.delete("all")
            width = max(m.winfo_width(), int((self.WIDTH - 34) * s))
            height = int(22 * s)
            self._level = getattr(self, "_level", 0.0)
            self._level += (self.app.assistant.mic_level - self._level) * 0.35   # smoothed
            level = self._level
            bars = 28
            gap = width / bars
            for i in range(bars):
                wave = 0.35 + 0.65 * abs(((now * 3 + i * 0.37) % 2) - 1)
                h = max(2 * s, height * min(1.0, level * 1.6) * wave)
                x = i * gap + gap / 2
                m.create_line(x, height / 2 - h / 2, x, height / 2 + h / 2, fill=self.accent,
                              width=max(2, int(gap * 0.45)), capstyle="round")
        self.win.after(50, self._tick)

    # ---------- events from Wisp ----------
    def on_event(self, kind, text):
        if self.win is None:
            return
        if kind == "status":
            self.state = text if text in self.STATES else "ready"
            if text == "ready":
                self.compact = False
                self._schedule_hide()
            else:
                self._cancel_hide()
            if text == "listening":
                self.you_text = self.reply_text = self.step_text = ""
        elif kind == "hearing":
            self.you_text = text + " …"
        elif kind == "user":
            self.you_text, self.reply_text, self.step_text = text, "", ""
            self.reply_colour = ui.TEXT
        elif kind == "tool":
            if not text.startswith("took "):
                self.step_text = self.app._friendly_step(text)
                self.compact = "windows-mcp" in text or "computer" in text.lower()
        elif kind == "say":
            self.reply_text, self.reply_colour, self.compact = text, ui.TEXT, False
        elif kind == "error":
            self.reply_text, self.reply_colour = text, ui.RED
        elif kind == "alert":
            self.reply_text, self.reply_colour = text, ui.TEXT
        elif kind == "info" and re.match(r"^(Stopped|已停止)", text or ""):
            self.reply_text, self.reply_colour, self.step_text = text, ui.DIM, ""
        else:
            return
        self._render()

    def stop(self):
        self.app.assistant.stop()
