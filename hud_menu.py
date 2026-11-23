"""A dark, rounded right-click menu that matches the HUD (Windows' own menus can't be styled properly).

items: a list of dicts
  {"label": "New chat", "command": fn}                      a normal item
  {"label": "Hide", "command": fn, "hint": "Ctrl+Shift+Space"}  with a shortcut shown on the right
  {"label": "Mute voice", "toggle": (get_fn, set_fn)}        an on/off switch (menu stays open)
  {"label": "Quit", "command": fn, "danger": True}          shown in red
  {"sep": True}                                             a divider line
"""
import tkinter as tk

KEY = "#010203"  # see-through colour (gives the menu rounded corners)


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    (ra, ga, ba), (rb, gb, bb) = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class HudMenu:
    def __init__(self, root, items, x, y, accent, font, small_font, scale=1.0,
                 panel="#0a0e13", text="#dfe7ef", dim="#6b7785", danger="#ff6b6b"):
        self.items, self.accent, self.s = items, accent, scale
        self.panel, self.text, self.dim, self.danger = panel, text, dim, danger
        self.font, self.small = font, small_font
        s = scale
        self.row_h, self.sep_h, self.pad = int(34 * s), int(11 * s), int(8 * s)
        self.w = int(250 * s)
        self.h = self.pad * 2 + sum(self.sep_h if it.get("sep") else self.row_h for it in items)

        self.win = win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=KEY)

        # keep it on screen: open up/left from the mouse if there isn't room
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        if x + self.w > sw - 4:
            x -= self.w
        if y + self.h > sh - 4:
            y -= self.h
        win.geometry(f"{self.w}x{self.h}+{max(0, x)}+{max(0, y)}")
        try:
            from context import hide_from_screenshots
            hide_from_screenshots(win)
        except Exception:
            pass

        self.c = c = tk.Canvas(win, width=self.w, height=self.h, bg=KEY, highlightthickness=0)
        from hud_draw import make_see_through
        make_see_through(win, c)
        c.pack()
        rounded_rect(c, 1, 1, self.w - 2, self.h - 2, 14 * s, fill=panel,
                     outline=_mix(panel, accent, 0.45), width=1)
        self.hover_id = rounded_rect(c, 0, 0, 0, 0, 8 * s, fill=_mix(panel, accent, 0.16), outline="", state="hidden")
        self.rows = []  # (top, bottom, item)
        self._draw_rows()

        c.bind("<Motion>", self._motion)
        c.bind("<Leave>", lambda e: c.itemconfig(self.hover_id, state="hidden"))
        c.bind("<ButtonRelease-1>", self._click)
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<FocusOut>", lambda e: win.after(50, self._close_if_unfocused))
        win.after(10, win.focus_force)

    def _draw_rows(self):
        c, s = self.c, self.s
        c.delete("row")
        y = self.pad
        self.rows = []
        for it in self.items:
            if it.get("sep"):
                mid = y + self.sep_h / 2
                c.create_line(16 * s, mid, self.w - 16 * s, mid, fill=_mix(self.panel, self.dim, 0.35), tags="row")
                y += self.sep_h
                continue
            top, bottom = y, y + self.row_h
            mid = (top + bottom) / 2
            colour = self.danger if it.get("danger") else self.text
            c.create_text(20 * s, mid, text=it["label"], anchor="w", font=self.font, fill=colour, tags="row")
            if it.get("hint"):
                c.create_text(self.w - 18 * s, mid, text=it["hint"], anchor="e", font=self.small,
                              fill=self.dim, tags="row")
            if it.get("toggle"):
                self._draw_switch(self.w - 22 * s, mid, bool(it["toggle"][0]()))
            self.rows.append((top, bottom, it))
            y = bottom

    def _draw_switch(self, right, mid, on):
        """An on/off pill switch, lit up in the accent colour when on."""
        s, c = self.s, self.c
        w, h = 32 * s, 18 * s
        x1, y1, x2, y2 = right - w, mid - h / 2, right, mid + h / 2
        track = self.accent if on else _mix(self.panel, self.dim, 0.45)
        rounded_rect(c, x1, y1, x2, y2, h / 2, fill=track, outline="", tags="row")
        k = h - 6 * s
        kx = x2 - 3 * s - k if on else x1 + 3 * s
        c.create_oval(kx, y1 + 3 * s, kx + k, y1 + 3 * s + k,
                      fill="#0a0e13" if on else "#c9d1da", outline="", tags="row")

    def _row_at(self, y):
        for top, bottom, it in self.rows:
            if top <= y < bottom:
                return top, bottom, it
        return None

    def _motion(self, e):
        row = self._row_at(e.y)
        if not row:
            self.c.itemconfig(self.hover_id, state="hidden")
            return
        top, bottom, _ = row
        s = self.s
        x1, y1, x2, y2 = 6 * s, top + 2 * s, self.w - 6 * s, bottom - 2 * s
        r = 8 * s
        self.c.coords(self.hover_id, x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                      x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1)
        self.c.itemconfig(self.hover_id, state="normal")
        self.c.tag_lower(self.hover_id, "row")

    def _click(self, e):
        row = self._row_at(e.y)
        if not row:
            return
        it = row[2]
        if it.get("toggle"):
            get, set_ = it["toggle"]
            set_(not get())
            self._draw_rows()
            self.c.tag_lower(self.hover_id, "row")
            return
        self.close()
        if it.get("command"):
            self.win.master.after(20, it["command"])

    def _close_if_unfocused(self):
        try:
            focus = self.win.focus_get()
            if focus is None or not str(focus).startswith(str(self.win)):
                self.close()
        except (tk.TclError, KeyError):
            self.close()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
