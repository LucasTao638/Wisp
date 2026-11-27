"""The side widget: a small holographic panel that appears beside the orb while you talk to Wisp.

Unlike the full-screen HUD it doesn't dim the screen or take over the middle of it. It shows:
  - what Wisp is doing: listening (live waveform), thinking (scanning bar + the current step), speaking
  - what it heard you say, and its reply
  - a Stop button that interrupts everything (same as F10, Esc, or saying "stop")
It tucks itself away a few seconds after Wisp has finished (not while your mouse is over it).
Everything is drawn on one canvas, so it can have cut corners, glowing edges and scan lines.
"""
import math
import re
import time
import tkinter as tk

import holo
from context import hide_from_screenshots
from hud_draw import KEY, make_see_through
from i18n import L

SOFT = "#bfe6f7"


class TalkWidget:
    WIDTH = 360

    STATES = {
        "listening": (("Listening", "正在听"), "#38d6ff"),
        "thinking": (("Thinking", "正在思考"), holo.AMBER),
        "speaking": (("Speaking", "正在说话"), holo.GREEN),
        "ready": (("Standing by", "待命"), holo.DIM),
    }

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
        self.you_text = self.step_text = self.reply_text = self.hint_text = ""
        self.reply_colour = holo.TEXT
        self._level = 0.0
        self.H = 120

    @property
    def is_open(self):
        return self.win is not None

    # ---------- building ----------
    def _build(self):
        a = self.app
        self.win = win = tk.Toplevel(a.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=KEY)
        try:
            win.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.f = holo.fonts(a.root)
        self.c = c = tk.Canvas(win, width=int(self.WIDTH * self.s), height=self.H, bg=KEY, highlightthickness=0)
        c.pack(fill="both", expand=True)
        make_see_through(win, c)
        c.tag_bind("close", "<ButtonRelease-1>", lambda e: self.hide())
        c.tag_bind("stop", "<ButtonRelease-1>", lambda e: self.stop())
        c.tag_bind("stop", "<Enter>", lambda e: self._stop_hover(True))
        c.tag_bind("stop", "<Leave>", lambda e: self._stop_hover(False))
        c.bind("<Enter>", lambda e: self._hover(True))
        c.bind("<Leave>", lambda e: self._hover(False))
        try:
            hide_from_screenshots(win)  # Claude's screenshots should show your screen, not Wisp
        except Exception:
            pass
        self._stop_hot = False
        self._render()
        self._tick()

    # ---------- showing / hiding ----------
    def show(self):
        self._cancel_hide()
        if self.win is None:
            self._build()
        self._place()
        self._fade_to(0.96)

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

    def _stop_hover(self, on):
        self._stop_hot = on
        self._render()

    def _place(self):
        """Bottom-right, just to the left of the orb (or in the corner if the orb is hidden)."""
        if self.win is None:
            return
        a, s = self.app, self.s
        w, h = int(self.WIDTH * s), self.H
        _, _, right, bottom = a._work_area()
        if not a.hidden and a.corner_visible:
            x = a.root.winfo_x() + int(a.W / 2 - 70 * s) - w   # beside the orb itself, not its whole window
        else:
            x = right - w - int(16 * s)
        x = max(int(8 * s), x)
        y = bottom - h - int(16 * s)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    # ---------- drawing ----------
    def _render(self):
        """Lay everything out top to bottom, then draw the panel to fit behind it."""
        if self.win is None:
            return
        c, s, f = self.c, self.s, self.f
        c.delete("all")
        W = int(self.WIDTH * s)
        pad = 18 * s
        inner = W - 2 * pad
        (en, zh), colour = self.STATES.get(self.state, self.STATES["ready"])
        if self.compact and self.state == "thinking":
            en, zh = "Working in your apps", "正在操作你的应用"
        self._colour = colour

        y = 16 * s
        # header: ◆ STATUS ............ WISP  ✕
        self._dot_xy = (pad + 5 * s, y + 8 * s)
        c.create_text(pad + 18 * s, y + 8 * s, text=holo.spaced(L(en, zh)), anchor="w", font=f["label"],
                      fill=colour, tags="text")
        c.create_text(W - pad - 22 * s, y + 8 * s, text="WISP", anchor="e", font=f["label"], fill=holo.MUTED,
                      tags="text")
        c.create_text(W - pad, y + 8 * s, text="✕", anchor="e", font=f["small"], fill=holo.DIM,
                      tags=("text", "close"))
        y += 24 * s
        self._rule_y = y
        y += 10 * s

        if self.state in ("listening", "thinking", "speaking"):
            self._meter_box = (pad, y, W - pad, y + 30 * s)   # waveform / scanning bar, drawn every frame
            y += 38 * s
        else:
            self._meter_box = None

        def block(text, font, fill, gap=8):
            nonlocal y
            if not text:
                return
            item = c.create_text(pad, y, text=text, anchor="nw", font=font, fill=fill, width=inner, tags="text")
            box = c.bbox(item)
            y = (box[3] if box else y) + gap * s

        if self.you_text and not self.compact:
            c.create_text(pad - 2 * s, y, text="▸", anchor="nw", font=f["small"], fill=holo.mix(holo.BG, colour, 0.7),
                          tags="text")
            y0 = y
            item = c.create_text(pad + 12 * s, y, text=f"“{self.you_text}”", anchor="nw", font=f["body"],
                                 fill=SOFT, width=inner - 12 * s, tags="text")
            box = c.bbox(item)
            y = (box[3] if box else y0) + 8 * s
        if self.step_text and self.state == "thinking":
            block("› " + self.step_text, f["mono"], holo.mix(holo.DIM, holo.AMBER, 0.35))
        if self.reply_text and not self.compact:
            text = self.reply_text if len(self.reply_text) < 420 else self.reply_text[:417] + "…"
            block(text, f["body"], self.reply_colour, gap=10)
        if self.state == "listening" and self.hint_text:
            block("◇  " + self.hint_text, f["small"], holo.mix(holo.DIM, self._colour, 0.3))

        if self.state in ("listening", "thinking", "speaking"):
            y += 4 * s
            label = L("CANCEL", "取消") if self.state == "listening" else L("STOP", "停止")
            bw, bh = f["label"].measure("■  " + label) + 28 * s, 26 * s
            red = holo.RED
            fill = holo.mix(holo.PANEL, red, 0.35 if self._stop_hot else 0.14)
            c.create_polygon(holo.chamfer(pad, y, pad + bw, y + bh, 6 * s), fill=fill,
                             outline=red if self._stop_hot else holo.mix(holo.PANEL, red, 0.6), tags="stop")
            c.create_text(pad + bw / 2, y + bh / 2, text="■  " + label, font=f["label"],
                          fill=holo.mix(red, "#ffffff", 0.5), tags="stop")
            import hotkeys
            key = hotkeys.label(self.cfg.get("stop_key", "f10"))
            if not self.compact:
                c.create_text(pad + bw + 12 * s, y + bh / 2, text=L(f"{key}  ·  or say “stop”", f"{key}  ·  或说“停”"),
                              anchor="w", font=f["small"], fill=holo.MUTED, tags="text")
            y += bh
        y += 16 * s
        H = int(y)
        self.H = H

        # the panel behind it all
        cut = 14 * s
        pts = holo.chamfer(1, 1, W - 2, H - 2, cut)
        c.create_polygon(pts, fill=holo.PANEL, outline=holo.LINE, tags="panel")
        line = holo.mix(holo.PANEL, colour, 0.035)
        for sy in range(4, H - 3, 4):   # scan lines, kept inside the cut corners
            left = 2 + max(0, cut - sy)
            right = W - 3 - max(0, cut - (H - 2 - sy))
            c.create_line(left, sy, right, sy, fill=line, tags="panel")
        # glowing top edge (beside the cut) and left edge
        holo.glow_line(c, (1 + cut, 1, W * 0.55, 1), colour, holo.PANEL, tag="panel")
        holo.glow_line(c, (1, 1 + cut, 1, H * 0.5), colour, holo.PANEL, tag="panel")
        holo.brackets(c, 5, 5, W - 6, H - 6, holo.mix(holo.PANEL, colour, 0.7), size=9 * s, width=2,
                      tag="panel", corners="tr bl")
        c.create_line(pad, self._rule_y, W - pad, self._rule_y, fill=holo.LINE, tags="panel")
        c.create_line(pad, self._rule_y, pad + 36 * s, self._rule_y, fill=colour, width=2, tags="panel")
        c.tag_lower("panel")
        c.configure(height=H)
        self._place()
        self._draw_dynamic()

    def _draw_dynamic(self):
        """The parts that move: the status diamond and the waveform / scanning bar."""
        c, s, now = self.c, self.s, time.time()
        c.delete("dyn")
        colour = self._colour
        x, y = self._dot_xy
        pulse = 0.6 + 0.4 * abs(((now * 1.4) % 2) - 1) if self.state != "ready" else 1.0
        r = 5 * s
        c.create_polygon(x, y - r - 2 * s * pulse, x + r + 2 * s * pulse, y, x, y + r + 2 * s * pulse,
                         x - r - 2 * s * pulse, y, fill=holo.mix(holo.PANEL, colour, 0.25), outline="", tags="dyn")
        c.create_polygon(x, y - r, x + r, y, x, y + r, x - r, y, fill=colour, outline="", tags="dyn")
        if not self._meter_box:
            return
        x1, y1, x2, y2 = self._meter_box
        mid = (y1 + y2) / 2
        if self.state == "listening":
            self._level += (self.app.assistant.mic_level - self._level) * 0.35
            amp = (3 + min(1.0, self._level * 1.8) * 12) * s
            for k, (alpha, phase, scale) in enumerate(((0.25, 1.7, 0.6), (0.5, 0.9, 0.85), (1.0, 0.0, 1.0))):
                pts = []
                n = 48
                for i in range(n + 1):
                    px = x1 + (x2 - x1) * i / n
                    env = math.sin(math.pi * i / n)   # fade out at both ends
                    py = mid + math.sin(i * 0.55 + now * 7 + phase) * amp * scale * env \
                        * (0.6 + 0.4 * math.sin(i * 0.17 + now * 3))
                    pts += [px, py]
                c.create_line(*pts, fill=holo.mix(holo.PANEL, colour, alpha), width=2 if k == 2 else 1,
                              smooth=True, tags="dyn")
        elif self.state == "thinking":
            segs, gap = 24, 3 * s
            sw = (x2 - x1 - gap * (segs - 1)) / segs
            head = (now * 14) % (segs + 8) - 4
            for i in range(segs):
                sx = x1 + i * (sw + gap)
                d = abs(i - head)
                strength = max(0.12, 1 - d / 5)
                c.create_polygon(holo.chamfer(sx, mid - 4 * s, sx + sw, mid + 4 * s, 2 * s, "tr bl"),
                                 fill=holo.mix(holo.PANEL, colour, strength), outline="", tags="dyn")
        else:  # speaking: equaliser bars
            bars = 32
            bw = (x2 - x1) / bars
            for i in range(bars):
                h = (2 + abs(math.sin(i * 0.9 + now * 9) * math.sin(i * 0.3 + now * 2.3)) * 12) * s
                bx = x1 + i * bw + bw / 2
                c.create_line(bx, mid - h, bx, mid + h, fill=holo.mix(holo.PANEL, colour, 0.85),
                              width=max(2, int(bw * 0.45)), tags="dyn")

    def _tick(self):
        if self.win is None:
            return
        self._draw_dynamic()
        self.win.after(40, self._tick)

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
                # start fresh; if this turns out to be a conversation follow-up, the hint brings the reply back
                self._last = (self.you_text, self.reply_text, self.reply_colour)
                self.you_text = self.reply_text = self.step_text = self.hint_text = ""
        elif kind == "hint":
            self.hint_text = text
            self.you_text, self.reply_text, self.reply_colour = getattr(self, "_last", ("", "", holo.TEXT))
        elif kind == "hearing":
            self.you_text = text + " …"
        elif kind == "user":
            self.you_text, self.reply_text, self.step_text, self.hint_text = text, "", "", ""
            self.reply_colour = holo.TEXT
        elif kind == "tool":
            if not text.startswith("took "):
                self.step_text = self.app._friendly_step(text)
                self.compact = "windows-mcp" in text or "computer" in text.lower()
        elif kind == "say":
            self.reply_text, self.reply_colour, self.compact = text, holo.TEXT, False
        elif kind == "error":
            self.reply_text, self.reply_colour = text, holo.RED
        elif kind == "alert":
            self.reply_text, self.reply_colour = text, holo.TEXT
        elif kind == "info" and re.match(r"^(Stopped|已停止)", text or ""):
            self.reply_text, self.reply_colour, self.step_text = text, holo.DIM, ""
        else:
            return
        self._render()

    def stop(self):
        self.app.assistant.stop()
