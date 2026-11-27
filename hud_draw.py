"""Drawing helpers shared by the corner orb and the full-screen HUD."""
import math

KEY = "#010203"      # this colour becomes see-through
AMBER = "#ffb547"
GREY = "#5b6573"


def hex_to_rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Blend colour a towards colour b (t = 0..1)."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = hex_to_rgb(a)
    rb, gb, bb = hex_to_rgb(b)
    return "#%02x%02x%02x" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


def orb_state(app, t):
    """Work out the orb's look from what the assistant is doing. Updates app.level / app.ripples."""
    a = app.assistant
    status = "listening" if a.is_listening else app.status
    if a.is_speaking and status != "listening":
        status = "speaking"
    colour = {"thinking": AMBER, "starting": GREY,
              "listening": mix(app.accent, "#ffffff", 0.45)}.get(status, app.accent)
    app.level += (a.mic_level - app.level) * 0.35
    if status == "listening":
        pulse = 4 + app.level * 22
        if app.level > 0.15 and (not app.ripples or t - app.ripples[-1] > 0.25):
            app.ripples.append(t)
    elif status == "speaking":
        pulse = 5 + abs(math.sin(t * 8.5)) * 7 + math.sin(t * 3.3) * 3
    elif status == "thinking":
        pulse = 3 + math.sin(t * 4) * 3
    else:
        pulse = 2 + math.sin(t * 1.6) * 2.5
    spin = {"thinking": 150, "starting": 60, "listening": 45}.get(status, 22)
    app.ripples = [r for r in app.ripples if t - r < 1.2]
    return status, colour, pulse, spin


def draw_orb(c, cx, cy, s, colour, pulse, spin, t, ripples, tag="orb", bg=KEY, detail=1, status=None, level=0.0):
    """The animated orb: a holographic lens. s = size multiplier. detail=2 adds outer rings for the HUD.
    status / level (optional) make it react: audio bars while listening, a sweep while thinking,
    pulse rings while speaking."""
    see_through = bg == KEY

    def tone(frac):
        """A fainter version of the colour. On a see-through window, 'faint' can't mean 'darker'
        (that shows as black lines over your wallpaper), so it becomes a dimmer shade instead."""
        if see_through:
            return mix(colour, "#0a1c26", (1 - frac) * 0.55)
        return tone(frac)

    def ring(r, frac, width=1):
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=tone(frac), width=width, tags=tag)

    def arc(r, start, extent, frac=1.0, width=2):
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start, extent=extent, style="arc",
                     outline=tone(frac), width=width, tags=tag)

    def polar(r, deg):
        a = math.radians(deg)
        return cx + math.cos(a) * r, cy - math.sin(a) * r

    # listening ripples
    for r0 in ripples:
        age = (t - r0) / 1.2
        rr = (60 + age * 90 * (1.6 if detail > 1 else 1)) * s
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=tone((1 - age) * 0.55),
                      width=1, tags=tag)

    if detail > 1:
        # extra outer rings for the big HUD
        r = 176 * s
        ring(r, 0.14)
        for k in range(4):
            arc(r, (-t * 9) % 360 + k * 90, 26, 0.6, max(2, int(2 * s)))
        r = 192 * s
        for i in range(90):
            if i % 15 < 11:
                x1, y1 = polar(r, -t * 3 + i * 4)
                x2, y2 = polar(r + (7 if i % 15 == 0 else 3) * s, -t * 3 + i * 4)
                c.create_line(x1, y1, x2, y2, fill=tone(0.3 if i % 15 == 0 else 0.16), tags=tag)

    # outer tick ring, turning slowly
    r_out = 150 * s
    rot = t * 4
    for i in range(60):
        long = i % 5 == 0
        x1, y1 = polar(r_out - (10 if long else 4) * s, rot + i * 6)
        x2, y2 = polar(r_out, rot + i * 6)
        c.create_line(x1, y1, x2, y2, fill=tone(0.6 if long else 0.22), width=2 if long else 1, tags=tag)
    # four fixed markers pointing in
    for deg in (90, 0, 270, 180):
        tip = polar(r_out + 4 * s, deg)
        left = polar(r_out + 12 * s, deg + 2.4)
        right = polar(r_out + 12 * s, deg - 2.4)
        c.create_polygon(*tip, *left, *right, fill=tone(0.75), outline="", tags=tag)

    ring(134 * s, 0.2)

    # thinking: a radar sweep with a fading tail
    if status == "thinking":
        head = (-t * 220) % 360
        for k in range(8):   # a fan of fading lines
            x1, y1 = polar(74 * s, head + k * 4)
            x2, y2 = polar(128 * s, head + k * 4)
            c.create_line(x1, y1, x2, y2, fill=tone(0.9 - k * 0.1), width=max(1, int((2 if k == 0 else 1) * s)),
                          tags=tag)

    # segmented ring: becomes live audio bars while listening
    r = 120 * s
    seg_rot = t * spin * 0.25
    for i in range(48):
        deg = seg_rot + i * 7.5
        if status == "listening":
            wave = 0.35 + 0.65 * abs(math.sin(i * 0.7 + t * 6) * math.sin(i * 0.23 + t * 2.1))
            length = (3 + min(1.0, level * 1.6) * 20 * wave) * s
            x1, y1 = polar(r - 4 * s, deg)
            x2, y2 = polar(r - 4 * s + length, deg)
            c.create_line(x1, y1, x2, y2, fill=tone(0.45 + 0.5 * wave), width=max(2, int(2 * s)),
                          tags=tag)
        else:
            arc(r, deg, 4.5, 0.38, max(2, int(3 * s)))

    # main arcs with glowing end caps
    r = 104 * s
    base = (t * spin) % 360
    for k in range(3):
        start = base + k * 120
        arc(r, start, 48, 1.0, max(2, int(3 * s)))
        for edge in (start, start + 48):
            x, y = polar(r, edge)
            d = 2.6 * s
            c.create_oval(x - d, y - d, x + d, y + d, fill=mix(colour, "#ffffff", 0.4), outline="", tags=tag)
    r = 90 * s
    for k in range(2):
        arc(r, -base * 1.4 + k * 180, 110, 0.5, max(1, int(1.5 * s)))

    # dashed inner ring
    r = 70 * s
    for i in range(24):
        arc(r, -t * 12 + i * 15, 7, 0.3, 1)

    # speaking: soft rings pushing outwards from the core
    if status == "speaking":
        for k in range(3):
            phase = ((t * 1.6) + k / 3) % 1
            rr = (40 + phase * 30) * s
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=tone((1 - phase) * 0.7),
                          width=max(1, int(2 * s)), tags=tag)

    # the core: a small bright lens, not a blob
    core = (30 + pulse * 0.55) * s
    if not see_through:   # soft glow discs (on a see-through window they'd look like a dark halo)
        for step, strength in ((14, 0.05), (8, 0.1), (3, 0.18)):
            g = core + step * s
            c.create_oval(cx - g, cy - g, cx + g, cy + g, fill=tone(strength), outline="", tags=tag)
    else:
        g = core + 6 * s
        c.create_oval(cx - g, cy - g, cx + g, cy + g, outline=tone(0.35), width=1, tags=tag)
    c.create_oval(cx - core, cy - core, cx + core, cy + core, fill=tone(0.22), outline=colour,
                  width=max(2, int(2 * s)), tags=tag)
    lens = core * 0.68
    c.create_oval(cx - lens, cy - lens, cx + lens, cy + lens, fill=tone(0.55),
                  outline=mix(colour, "#ffffff", 0.35), tags=tag)
    rr = core * 0.86
    for k in range(3):   # small turning triangle of arcs inside the core
        c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=-t * 90 + k * 120, extent=38, style="arc",
                     outline=mix(colour, "#ffffff", 0.55), width=max(1, int(2 * s)), tags=tag)
    dot = (5 + pulse * 0.15) * s
    c.create_oval(cx - dot, cy - dot, cx + dot, cy + dot, fill=mix(colour, "#ffffff", 0.8), outline="", tags=tag)


def bracket_panel(c, x1, y1, x2, y2, accent, panel, u, title=None, title_font=None, tag="static"):
    """A dark glass panel with cut corners, a glowing top edge and corner brackets, HUD-style."""
    cut = 16 * u
    pts = [x1, y1 + cut, x1 + cut, y1, x2, y1, x2, y2 - cut, x2 - cut, y2, x1, y2]
    c.create_polygon(pts, fill=panel, outline=mix(panel, accent, 0.25), tags=tag)
    c.create_line(x1 + cut, y1, x1 + (x2 - x1) * 0.45, y1, fill=mix(panel, accent, 0.35), width=max(3, int(4 * u)),
                  tags=tag)
    c.create_line(x1 + cut, y1, x1 + (x2 - x1) * 0.45, y1, fill=accent, width=max(1, int(2 * u)), tags=tag)
    L = 12 * u
    w = max(2, int(2 * u))
    for (x, y, dx, dy) in ((x2 - 5 * u, y1 + 5 * u, -1, 1), (x1 + 5 * u, y2 - 5 * u, 1, -1)):
        c.create_line(x, y + L * dy, x, y, x + L * dx, y, fill=accent, width=w, tags=tag)
    if title:
        c.create_text(x1 + 20 * u, y1 + 22 * u, text="◢ " + title.upper(), anchor="w",
                      font=title_font, fill=accent, tags=tag)
        c.create_line(x1 + 20 * u, y1 + 38 * u, x2 - 20 * u, y1 + 38 * u, fill=mix(panel, accent, 0.18), tags=tag)
        c.create_line(x1 + 20 * u, y1 + 38 * u, x1 + 56 * u, y1 + 38 * u, fill=accent, width=max(1, int(2 * u)),
                      tags=tag)


def gauge(c, x, y, w, u, label, value, accent, panel, font, small_font, tag="dyn", high_is_good=False):
    """A labelled segmented bar (value 0..100, or None if unknown). Turns amber when it needs attention:
    above 85% (CPU, memory) or, for high_is_good gauges like battery, below 20%."""
    c.create_text(x, y, text=label.upper(), anchor="w", font=small_font, fill=mix(panel, "#ffffff", 0.6), tags=tag)
    shown = "--" if value is None else f"{value:.0f}%"
    c.create_text(x + w, y, text=shown, anchor="e", font=font, fill=accent, tags=tag)
    by = y + 14 * u
    segs = 30
    gap = 2 * u
    sw = (w - gap * (segs - 1)) / segs
    lit = 0 if value is None else round(segs * max(0, min(100, value)) / 100)
    warn = value is not None and (value < 20 if high_is_good else value >= 85)
    colour = AMBER if warn else accent
    for i in range(segs):
        sx = x + i * (sw + gap)
        c.create_rectangle(sx, by, sx + sw, by + 7 * u, outline="",
                           fill=colour if i < lit else mix(panel, accent, 0.1), tags=tag)


# ---------- see-through windows and fonts, per system ----------
def make_see_through(window, canvas=None):
    """Make the window's background invisible so only what's drawn shows.
    Windows: the KEY colour becomes see-through (and click-through). Mac: real transparency."""
    import sys
    if sys.platform == "win32":
        window.attributes("-transparentcolor", KEY)
    elif sys.platform == "darwin":
        try:
            window.attributes("-transparent", True)
            window.configure(bg="systemTransparent")
            if canvas is not None:
                canvas.configure(bg="systemTransparent")
        except Exception as exc:
            print(f"(transparency not available: {exc})")


def pick_fonts(tkfont_module, root=None):
    """(HUD font, body font) that exist on this system."""
    fam = set(tkfont_module.families(root) if root is not None else tkfont_module.families())
    hud = next((f for f in ("Bahnschrift", "DIN Condensed", "DIN Alternate", "Avenir Next Condensed",
                            "Segoe UI", "Helvetica Neue") if f in fam), "Helvetica")
    body = next((f for f in ("Segoe UI", "Helvetica Neue", "SF Pro Text") if f in fam), "Helvetica")
    return hud, body
