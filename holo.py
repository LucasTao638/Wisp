"""Wisp's holographic design system: colours, fonts and the building blocks every window uses.

The look: near-black glass, thin cyan lines, chamfered (cut) corners, small corner brackets, monospace
labels in capitals. Everything is drawn with plain Tk (Canvas + Frame), so it works on Windows and Mac.
"""
import sys
import tkinter as tk
from tkinter import font as tkfont

# ---------- colours ----------
BG = "#04080c"         # window background
PANEL = "#08121a"      # cards / panels
PANEL_HI = "#0c1b26"   # hovered or selected panel, input fields
LINE = "#16323f"       # thin borders
LINE_SOFT = "#0f2430"  # very faint lines (grids, dividers)
TEXT = "#dff6ff"
DIM = "#7293a3"
MUTED = "#3d5866"
AMBER = "#ffb547"
RED = "#ff5468"
GREEN = "#45e3a0"
ACCENT = "#38d6ff"
ON_ACCENT = "#021016"  # text on an accent-coloured button


def hex_to_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Blend colour a towards colour b (t = 0..1)."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = hex_to_rgb(a)
    rb, gb, bb = hex_to_rgb(b)
    return "#%02x%02x%02x" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


# ---------- fonts ----------
def _pick(fam, options, fallback):
    return next((f for f in options if f in fam), fallback)


def fonts(root, scale=1.0):
    """title / head / body / small / mono / label / big - picked from what this computer has."""
    fam = set(tkfont.families(root))
    display = _pick(fam, ("Bahnschrift", "Avenir Next Condensed", "DIN Alternate", "Segoe UI", "Helvetica Neue"),
                    "Helvetica")
    body = _pick(fam, ("Segoe UI", "SF Pro Text", "Helvetica Neue"), "Helvetica")
    mono = _pick(fam, ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "Courier New"), "Courier")
    if sys.platform == "darwin":
        scale *= 1.25  # Mac points are smaller
    z = lambda n: int(round(n * scale))
    return {
        "big": tkfont.Font(root, family=display, size=z(26), weight="bold"),
        "title": tkfont.Font(root, family=display, size=z(19), weight="bold"),
        "head": tkfont.Font(root, family=display, size=z(11), weight="bold"),
        "body": tkfont.Font(root, family=body, size=z(10)),
        "small": tkfont.Font(root, family=body, size=z(9)),
        "mono": tkfont.Font(root, family=mono, size=z(9)),
        "label": tkfont.Font(root, family=mono, size=z(8), weight="bold"),
    }


def spaced(text):
    """'LISTENING' -> 'L I S T E N I N G' style caps for labels (left alone for Chinese)."""
    if any("一" <= ch <= "鿿" for ch in text):
        return text
    return text.upper()


# ---------- shapes ----------
def chamfer(x1, y1, x2, y2, c, corners="tl br"):
    """Points of a rectangle with cut corners (c = size of the cut)."""
    pts = []
    pts += [x1, y1 + c, x1 + c, y1] if "tl" in corners else [x1, y1]
    pts += [x2 - c, y1, x2, y1 + c] if "tr" in corners else [x2, y1]
    pts += [x2, y2 - c, x2 - c, y2] if "br" in corners else [x2, y2]
    pts += [x1 + c, y2, x1, y2 - c] if "bl" in corners else [x1, y2]
    return pts


def brackets(c, x1, y1, x2, y2, colour, size=10, width=2, tag=None, corners="tl tr bl br"):
    """Glowing corner brackets around a box."""
    kw = {"fill": colour, "width": width}
    if tag:
        kw["tags"] = tag
    for corner, (x, y, dx, dy) in (("tl", (x1, y1, 1, 1)), ("tr", (x2, y1, -1, 1)),
                                   ("bl", (x1, y2, 1, -1)), ("br", (x2, y2, -1, -1))):
        if corner in corners:
            c.create_line(x, y + dy * size, x, y, x + dx * size, y, **kw)


def glow_line(c, pts, colour, bg, width=1, tag=None):
    """A line with a soft glow (two wider, fainter strokes underneath)."""
    kw = {"tags": tag} if tag else {}
    c.create_line(*pts, fill=mix(bg, colour, 0.12), width=width + 4, **kw)
    c.create_line(*pts, fill=mix(bg, colour, 0.3), width=width + 2, **kw)
    c.create_line(*pts, fill=colour, width=width, **kw)


def grid_texture(c, w, h, colour, step=24, tag="grid"):
    """Faint blueprint grid with small crosses at the intersections."""
    for x in range(0, int(w) + step, step):
        c.create_line(x, 0, x, h, fill=colour, tags=tag)
    for y in range(0, int(h) + step, step):
        c.create_line(0, y, w, y, fill=colour, tags=tag)


def scanlines(c, x1, y1, x2, y2, colour, step=3, tag=None):
    kw = {"tags": tag} if tag else {}
    y = y1 + 1
    while y < y2:
        c.create_line(x1, y, x2, y, fill=colour, **kw)
        y += step


# ---------- widgets ----------
class Button(tk.Canvas):
    """A chamfered, glowing button. kind: "ghost" (outline), "primary" (filled) or "danger"."""

    def __init__(self, parent, text, command=None, kind="ghost", font=None, accent=ACCENT, bg=None,
                 padx=14, pady=7, width=None, **_ignored):
        self._bg = bg or _bg(parent)
        self.text, self.command, self.kind, self.accent = text, command, kind, accent
        self.font = font or tkfont.Font(family="Segoe UI", size=9)
        self.padx, self.pady, self.fixed_w = padx, pady, width
        self.enabled, self.hover = True, False
        w, h = self._size()
        super().__init__(parent, width=w, height=h, bg=self._bg, highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self._draw()

    def _size(self):
        tw = self.font.measure(self.text)
        return (self.fixed_w or tw + 2 * self.padx), self.font.metrics("linespace") + 2 * self.pady

    def _set_hover(self, on):
        self.hover = on and self.enabled
        self._draw()

    def _click(self, e):
        if self.enabled and self.command and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def _draw(self):
        self.delete("all")
        w, h = self._size()
        a = {"danger": RED}.get(self.kind, self.accent)
        cut = 6
        pts = chamfer(0.5, 0.5, w - 1.5, h - 1.5, cut)
        if not self.enabled:
            fill, outline, fg = self._bg, LINE, MUTED
        elif self.kind == "primary":
            fill = mix(a, "#ffffff", 0.15) if self.hover else a
            outline, fg = fill, ON_ACCENT
        else:
            fill = mix(self._bg, a, 0.22 if self.hover else 0.08)
            outline = a if self.hover else mix(self._bg, a, 0.55)
            fg = mix(a, "#ffffff", 0.55) if self.kind == "danger" else (TEXT if self.hover else mix(TEXT, a, 0.25))
        self.create_polygon(pts, fill=fill, outline=outline, width=1)
        self.create_text(w / 2, h / 2, text=self.text, font=self.font, fill=fg)

    # FlatButton-compatible bits
    def configure(self, cnf=None, **kw):
        changed = False
        for key in ("text", "command"):
            if key in kw:
                setattr(self, key, kw.pop(key))
                changed = True
        if "bg" in kw and self.kind != "primary":
            pass
        if kw or cnf:
            super().configure(cnf, **kw)
        if changed:
            w, h = self._size()
            super().configure(width=w, height=h)
            self._draw()

    config = configure

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        super().configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_colour(self, bg):
        pass


class Switch(tk.Canvas):
    """An on/off toggle: a chamfered track with a glowing block that slides across."""

    def __init__(self, parent, value=False, command=None, accent=ACCENT, bg=None):
        self._bg = bg or _bg(parent)
        super().__init__(parent, width=48, height=22, bg=self._bg, highlightthickness=0, cursor="hand2")
        self.value, self.command, self.accent = bool(value), command, accent
        self.bind("<ButtonRelease-1>", lambda e: self.set(not self.value, notify=True))
        self._draw()

    def _draw(self):
        self.delete("all")
        a = self.accent
        on = self.value
        self.create_polygon(chamfer(0.5, 0.5, 46.5, 20.5, 5), fill=mix(self._bg, a, 0.2) if on else PANEL_HI,
                            outline=a if on else LINE)
        x = 26 if on else 4
        knob = a if on else "#4a6373"
        if on:
            self.create_rectangle(x - 2, 2, x + 18, 19, fill=mix(self._bg, a, 0.45), outline="")
        self.create_polygon(chamfer(x, 4, x + 16, 17, 3), fill=knob, outline="")
        if not on:
            for k in range(3):
                self.create_line(x + 5 + k * 3, 7, x + 5 + k * 3, 14, fill="#2b3d48")

    def set(self, value, notify=False):
        self.value = bool(value)
        self._draw()
        if notify and self.command:
            self.command(self.value)

    def get(self):
        return self.value


class Slider(tk.Canvas):
    """A thin track with a diamond handle and the value shown beside it."""

    def __init__(self, parent, value, lo, hi, step, command=None, accent=ACCENT, font=None, length=170, fmt=None,
                 bg=None):
        self._bg = bg or _bg(parent)
        self.lo, self.hi, self.step, self.command, self.accent = lo, hi, step, command, accent
        self.font = font or tkfont.Font(family="Consolas", size=9)
        self.fmt, self.length = fmt, length
        self.value = self._snap(value)
        super().__init__(parent, width=length + 54, height=24, bg=self._bg, highlightthickness=0, cursor="hand2")
        for ev in ("<Button-1>", "<B1-Motion>"):
            self.bind(ev, self._drag)
        self.bind("<ButtonRelease-1>", lambda e: self.command and self.command(self.value))
        self._draw()

    def _snap(self, v):
        v = max(self.lo, min(self.hi, float(v)))
        return round(round((v - self.lo) / self.step) * self.step + self.lo, 4)

    def _drag(self, e):
        x = max(8, min(self.length - 8, e.x))
        self.value = self._snap(self.lo + (x - 8) / (self.length - 16) * (self.hi - self.lo))
        self._draw()

    def _label(self):
        if self.fmt == "percent":
            return f"{int(self.value):+d}%"
        return f"{self.value:g}"

    def _draw(self):
        self.delete("all")
        a, L, y = self.accent, self.length, 12
        frac = (self.value - self.lo) / ((self.hi - self.lo) or 1)
        x = 8 + frac * (L - 16)
        self.create_line(8, y, L - 8, y, fill=LINE, width=2)
        for k in range(11):
            tx = 8 + k * (L - 16) / 10
            self.create_line(tx, y + 4, tx, y + (7 if k % 5 == 0 else 5), fill=LINE)
        self.create_line(8, y, x, y, fill=a, width=2)
        self.create_polygon(x, y - 7, x + 6, y, x, y + 7, x - 6, y, fill=a, outline=mix(a, "#ffffff", 0.4))
        self.create_text(L + 6, y, text=self._label(), anchor="w", font=self.font, fill=TEXT)

    def set(self, v):
        self.value = self._snap(v)
        self._draw()

    def get(self):
        return self.value


class Dropdown(Button):
    """A button showing the current choice; click for a menu of options."""

    def __init__(self, parent, options, value, command=None, font=None, accent=ACCENT, width=230, bg=None):
        self.options = options  # [(code, label)]
        self.choice = value
        self.on_pick = command
        super().__init__(parent, self._label(), self._open, kind="ghost", font=font, accent=accent, bg=bg,
                         width=width)

    def _label(self):
        label = dict(self.options).get(self.choice, self.options[0][1])
        return label + "  ▾"

    def _draw(self):
        super()._draw()
        # left-align the text, keep the arrow on the right
        self.delete("all")
        w, h = self._size()
        a = self.accent
        fill = mix(self._bg, a, 0.18 if self.hover else 0.06)
        self.create_polygon(chamfer(0.5, 0.5, w - 1.5, h - 1.5, 6), fill=fill,
                            outline=a if self.hover else mix(self._bg, a, 0.45))
        label = dict(self.options).get(self.choice, self.options[0][1])
        max_w = w - 34
        while self.font.measure(label) > max_w and len(label) > 4:
            label = label[:-2]
        if label != dict(self.options).get(self.choice, self.options[0][1]):
            label = label.rstrip() + "…"
        self.create_text(12, h / 2, text=label, anchor="w", font=self.font, fill=TEXT)
        self.create_text(w - 12, h / 2, text="▾", anchor="e", font=self.font, fill=a)

    def _open(self):
        menu = tk.Menu(self, tearoff=0, bg=PANEL_HI, fg=TEXT, activebackground=self.accent,
                       activeforeground=ON_ACCENT, bd=0, font=self.font)
        for code, label in self.options:
            menu.add_command(label=("●  " if code == self.choice else "    ") + label,
                             command=lambda c=code: self.pick(c))
        try:
            menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            menu.grab_release()

    def pick(self, code, notify=True):
        self.choice = code
        self._draw()
        if notify and self.on_pick:
            self.on_pick(code)


def entry(parent, value="", show=None, width=30, font=None, accent=ACCENT):
    e = tk.Entry(parent, bg=PANEL_HI, fg=TEXT, insertbackground=accent, bd=0, highlightthickness=1,
                 highlightbackground=LINE, highlightcolor=accent, width=width, show=show, font=font,
                 selectbackground=mix(PANEL_HI, accent, 0.5), selectforeground=TEXT)
    e.insert(0, value)
    return e


class Card(tk.Frame):
    """A panel with a thin border and small glowing corner brackets."""

    def __init__(self, parent, accent=ACCENT, padx=16, pady=12, bg=PANEL, selected=False, **kw):
        border = accent if selected else LINE
        super().__init__(parent, bg=bg, padx=padx, pady=pady, highlightthickness=1,
                         highlightbackground=border, highlightcolor=border, **kw)
        tick = mix(bg, accent, 0.9 if selected else 0.55)
        for relx, rely, anchor, pts in ((0, 0, "nw", (1, 8, 1, 1, 8, 1)), (1, 0, "ne", (0, 1, 7, 1, 7, 8)),
                                        (0, 1, "sw", (1, 0, 1, 7, 8, 7)), (1, 1, "se", (7, 0, 7, 7, 0, 7))):
            c = tk.Canvas(self, width=9, height=9, bg=bg, highlightthickness=0)
            c.create_line(*pts, fill=tick, width=2)
            c.place(relx=relx, rely=rely, anchor=anchor, x=-1 if relx == 0 else 1, y=-1 if rely == 0 else 1)


def section(parent, title, accent, font, bg=BG, padx=24, pady=(22, 8), number=None):
    """A section heading:  ◢ LISTENING ─────────────  02"""
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", padx=padx, pady=pady)
    tk.Label(row, text="◢ " + spaced(title), bg=bg, fg=accent, font=font).pack(side="left")
    if number is not None:
        tk.Label(row, text=f"{number:02d}", bg=bg, fg=MUTED, font=font).pack(side="right")
    line = tk.Canvas(row, height=9, bg=bg, highlightthickness=0, width=40)
    line.pack(side="left", fill="x", expand=True, padx=10)
    line.create_line(0, 5, 4000, 5, fill=LINE)
    line.create_line(0, 5, 26, 5, fill=mix(bg, accent, 0.6), width=2)
    return row


class Header(tk.Canvas):
    """The banner at the top of a window: faint grid, title, a line of small details."""

    def __init__(self, parent, title, subtitle, accent, f, width=600, height=78, right_text=""):
        super().__init__(parent, width=width, height=height, bg=BG, highlightthickness=0)
        self.accent, self.f = accent, f
        grid_texture(self, width, height, mix(BG, accent, 0.045), step=18)
        self.create_rectangle(0, height - 1, width, height, fill=LINE, outline="")
        glow_line(self, (24, height - 1, 140, height - 1), accent, BG)
        self.create_text(24, 26, text=spaced(subtitle), anchor="w", font=f["label"], fill=mix(BG, accent, 0.8))
        self.create_text(24, 52, text=title, anchor="w", font=f["title"], fill=TEXT)
        if right_text:
            self.create_text(width - 24, 26, text=right_text, anchor="e", font=f["label"], fill=MUTED)
        # small ornament: three ticks and a ring
        x = width - 24
        self.create_oval(x - 12, 40, x + 0, 52, outline=accent, width=2)
        self.create_oval(x - 8, 44, x - 4, 48, fill=accent, outline="")
        for k in range(3):
            self.create_line(x - 26 - k * 6, 46, x - 22 - k * 6, 46, fill=mix(BG, accent, 0.5), width=2)


class ScrollArea:
    """A scrolling column with a thin holographic scrollbar. Put things in .body."""

    def __init__(self, parent, width, bg=BG, accent=ACCENT):
        outer = tk.Frame(parent, bg=bg)
        outer.pack(fill="both", expand=True)
        self.canvas = c = tk.Canvas(outer, bg=bg, highlightthickness=0)
        self.bar = tk.Canvas(outer, width=6, bg=bg, highlightthickness=0)
        self.bar.pack(side="right", fill="y", padx=(0, 4))
        c.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(c, bg=bg)
        c.create_window((0, 0), window=self.body, anchor="nw", width=width)
        self.accent = accent
        self.body.bind("<Configure>", lambda e: (c.configure(scrollregion=c.bbox("all")), self._draw_bar()))
        c.configure(yscrollcommand=lambda lo, hi: self._draw_bar(float(lo), float(hi)))
        self.bar.bind("<B1-Motion>", self._drag)
        self.bar.bind("<Button-1>", self._drag)
        self._view = (0.0, 1.0)

    def _draw_bar(self, lo=None, hi=None):
        if lo is not None:
            self._view = (lo, hi)
        lo, hi = self._view
        b = self.bar
        b.delete("all")
        h = b.winfo_height() or 600
        b.create_line(3, 0, 3, h, fill=LINE_SOFT)
        if hi - lo < 0.999:
            b.create_rectangle(1, lo * h, 5, hi * h, fill=mix(BG, self.accent, 0.55), outline="")

    def _drag(self, e):
        h = self.bar.winfo_height() or 1
        lo, hi = self._view
        self.canvas.yview_moveto(max(0.0, e.y / h - (hi - lo) / 2))

    def scroll(self, units):
        self.canvas.yview_scroll(units, "units")


def dark_titlebar(win):
    """Windows 10/11: make the window's title bar dark to match."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, older builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), 4) == 0:
                break
    except Exception:
        pass


def _bg(widget):
    try:
        return widget.cget("bg")
    except Exception:
        return BG
