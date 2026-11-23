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


def draw_orb(c, cx, cy, s, colour, pulse, spin, t, ripples, tag="orb", bg=KEY, detail=1):
    """The animated orb. s = size multiplier. detail=2 adds extra rings for the full-screen HUD."""
    for r0 in ripples:
        age = (t - r0) / 1.2
        rr = (52 + age * 80 * (1.6 if detail > 1 else 1)) * s
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=mix(bg, colour, (1 - age) * 0.8),
                      width=2, tags=tag)

    if detail > 1:
        # extra outer rings for the big HUD
        r = 172 * s
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=mix(bg, colour, 0.18), width=1, tags=tag)
        for k in range(4):
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=(-t * 9) % 360 + k * 90, extent=28,
                         style="arc", outline=mix(bg, colour, 0.55), width=max(2, int(2 * s)), tags=tag)
        r = 186 * s
        for i in range(120):
            if i % 10 < 7:
                a = math.radians(t * -3) + i * math.tau / 120
                c.create_line(cx + math.cos(a) * r, cy + math.sin(a) * r,
                              cx + math.cos(a) * (r + 4 * s), cy + math.sin(a) * (r + 4 * s),
                              fill=mix(bg, colour, 0.25), tags=tag)

    r_out = 150 * s
    rot = math.radians(t * 6)
    for i in range(72):
        a = rot + i * math.tau / 72
        long = i % 6 == 0
        r1 = r_out - (12 if long else 6) * s
        c.create_line(cx + math.cos(a) * r1, cy + math.sin(a) * r1,
                      cx + math.cos(a) * r_out, cy + math.sin(a) * r_out,
                      fill=mix(bg, colour, 0.55 if long else 0.3), width=2 if long else 1, tags=tag)

    r = 128 * s
    c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=mix(bg, colour, 0.28), width=1, tags=tag)

    r = 116 * s
    base = (t * spin) % 360
    for k in range(3):
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=base + k * 120, extent=62,
                     style="arc", outline=colour, width=max(2, int(3 * s)), tags=tag)
    r = 100 * s
    for k in range(2):
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=-base * 1.4 + k * 180, extent=105,
                     style="arc", outline=mix(bg, colour, 0.6), width=max(1, int(2 * s)), tags=tag)

    core = (46 + pulse) * s
    for step, strength in ((30, 0.07), (20, 0.13), (11, 0.22), (4, 0.38)):
        g = core + step * s
        c.create_oval(cx - g, cy - g, cx + g, cy + g, fill=mix(bg, colour, strength), outline="", tags=tag)
    c.create_oval(cx - core, cy - core, cx + core, cy + core, fill=mix(bg, colour, 0.85),
                  outline=mix(colour, "#ffffff", 0.5), width=1, tags=tag)
    inner = core * 0.55
    c.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, fill=mix(colour, "#ffffff", 0.55),
                  outline="", tags=tag)


def bracket_panel(c, x1, y1, x2, y2, accent, panel, u, title=None, title_font=None, tag="static"):
    """A dark panel with glowing corner brackets and an optional title, HUD-style."""
    c.create_rectangle(x1, y1, x2, y2, fill=panel, outline=mix(panel, accent, 0.22), tags=tag)
    L = 18 * u
    w = max(2, int(2 * u))
    for (x, y, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        c.create_line(x, y, x + L * dx, y, fill=accent, width=w, tags=tag)
        c.create_line(x, y, x, y + L * dy, fill=accent, width=w, tags=tag)
    if title:
        c.create_text(x1 + 16 * u, y1 + 18 * u, text=" ".join(title.upper()), anchor="w",
                      font=title_font, fill=accent, tags=tag)
        c.create_line(x1 + 16 * u, y1 + 34 * u, x2 - 16 * u, y1 + 34 * u,
                      fill=mix(panel, accent, 0.3), tags=tag)


def gauge(c, x, y, w, u, label, value, accent, panel, font, small_font, tag="dyn"):
    """A labelled horizontal bar (value 0..100, or None if unknown)."""
    c.create_text(x, y, text=label, anchor="w", font=small_font, fill=mix(panel, "#ffffff", 0.6), tags=tag)
    shown = "--" if value is None else f"{value:.0f}%"
    c.create_text(x + w, y, text=shown, anchor="e", font=font, fill=accent, tags=tag)
    by = y + 14 * u
    c.create_rectangle(x, by, x + w, by + 6 * u, fill=mix(panel, accent, 0.12), outline="", tags=tag)
    if value is not None:
        colour = accent if value < 85 else AMBER
        c.create_rectangle(x, by, x + w * max(0, min(100, value)) / 100, by + 6 * u, fill=colour,
                           outline="", tags=tag)
