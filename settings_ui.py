"""Settings window: everything in config.json, with switches and dropdowns instead of editing a file."""
import sys
import threading
import tkinter as tk

import autostart
import credentials
import telemetry
import ui_kit as ui
from app_info import APP_NAME, VERSION

MODELS = [("", "Default"), ("sonnet", "Sonnet - fast, smart (recommended)"), ("haiku", "Haiku - fastest, cheapest"),
          ("opus", "Opus - smartest, slowest, most expensive")]


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.cfg = ui.load_config()
        self.accent = self.cfg.get("accent_colour", "#38d6ff")
        self.changes = {}
        self.needs_restart = False
        win = self.win = tk.Toplevel(app.root, bg=ui.BG)
        win.title(f"{APP_NAME} settings")
        win.geometry("600x720")
        self.f = ui.fonts(win)

        tk.Label(win, text="S E T T I N G S", bg=ui.BG, fg=self.accent, font=self.f["title"]).pack(pady=(18, 6))
        outer = tk.Frame(win, bg=ui.BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=ui.BG, highlightthickness=0)
        bar = tk.Scrollbar(outer, command=canvas.yview, bg=ui.BG, troughcolor=ui.BG, bd=0, width=10)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=bar.set)
        self.body = tk.Frame(canvas, bg=ui.BG)
        canvas.create_window((0, 0), window=self.body, anchor="nw", width=570)
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self.build()

        bottom = tk.Frame(win, bg=ui.BG)
        bottom.pack(fill="x", padx=20, pady=14)
        self.status = tk.Label(bottom, text="", bg=ui.BG, fg=ui.DIM, font=self.f["small"])
        self.status.pack(side="left")
        ui.FlatButton(bottom, "Save", self.save, bg=self.accent, fg="#031018", hover=self.accent).pack(side="right")
        ui.FlatButton(bottom, "Cancel", win.destroy).pack(side="right", padx=8)

    # ---------- layout helpers ----------
    def section(self, title):
        tk.Label(self.body, text=" ".join(title.upper()), bg=ui.BG, fg=self.accent, font=self.f["head"],
                 anchor="w").pack(fill="x", padx=20, pady=(18, 6))

    def row(self, label, hint=None):
        card = tk.Frame(self.body, bg=ui.CARD, padx=14, pady=10)
        card.pack(fill="x", padx=20, pady=3)
        left = tk.Frame(card, bg=ui.CARD)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=label, bg=ui.CARD, fg=ui.TEXT, font=self.f["body"], anchor="w").pack(fill="x")
        if hint:
            tk.Label(left, text=hint, bg=ui.CARD, fg=ui.DIM, font=self.f["small"], anchor="w", justify="left",
                     wraplength=330).pack(fill="x")
        right = tk.Frame(card, bg=ui.CARD)
        right.pack(side="right")
        return right

    def switch(self, parent, key, default, restart=False, on_change=None):
        def changed(v):
            self.changes[key] = v
            if restart:
                self.needs_restart = True
            if on_change:
                on_change(v)
        s = ui.Switch(parent, self.cfg.get(key, default), changed, self.accent)
        s.pack()
        return s

    def dropdown(self, parent, key, options, default, restart=False):
        labels = {code: label for code, label in options}
        var = tk.StringVar(value=labels.get(self.cfg.get(key, default), options[0][1]))
        menu = tk.OptionMenu(parent, var, *[label for _, label in options],
                             command=lambda label: self._set(key, next(c for c, l in options if l == label), restart))
        menu.config(bg="#1a222c", fg=ui.TEXT, activebackground=self.accent, activeforeground="#031018",
                    highlightthickness=0, bd=0, font=self.f["small"], width=30)
        menu["menu"].config(bg="#1a222c", fg=ui.TEXT, activebackground=self.accent, activeforeground="#031018")
        menu.pack()
        return var

    def text(self, parent, key, default="", width=22, restart=False):
        e = ui.entry(parent, self.cfg.get(key, default), width=width, f=self.f["body"])
        e.pack(ipady=4)
        e.bind("<KeyRelease>", lambda ev: self._set(key, e.get().strip(), restart))
        return e

    def slider(self, parent, key, default, lo, hi, res, restart=False, fmt=None):
        value = self.cfg.get(key, default)
        if fmt == "percent":  # "+8%" <-> 8
            value = int(str(value).replace("%", "") or 0)
        s = tk.Scale(parent, from_=lo, to=hi, resolution=res, orient="horizontal", length=170, bg=ui.CARD,
                     fg=ui.TEXT, troughcolor="#26303c", highlightthickness=0, bd=0, activebackground=self.accent,
                     font=self.f["small"],
                     command=lambda v: self._set(key, (f"{int(float(v)):+d}%" if fmt == "percent" else float(v)), restart))
        s.set(value)
        s.pack()

    def _set(self, key, value, restart=False):
        self.changes[key] = value
        if restart:
            self.needs_restart = True

    # ---------- the settings ----------
    def build(self):
        self.section("Claude")
        r = self.row("Anthropic API key", f"Currently: {credentials.masked()}. Stored encrypted on this PC.")
        ui.FlatButton(r, "Change", self.change_key, font=self.f["small"]).pack()
        self.key_area = tk.Frame(self.body, bg=ui.BG)
        self.key_area.pack(fill="x", padx=20)
        r = self.row("Model", "Which Claude model answers you.")
        self.dropdown(r, "model", MODELS, "sonnet", restart=True)

        self.section("You")
        r = self.row("Your name", "Used in greetings and the HUD.")
        self.text(r, "user_name")

        self.section("Voice")
        r = self.row("Voice")
        self.dropdown(r, "edge_voice", ui.VOICES, "en-GB-RyanNeural", restart=True)
        r = self.row("Hear it", "Plays a sample with the voice and speed above (after saving).")
        ui.FlatButton(r, "▶ Preview", self.preview, font=self.f["small"]).pack()
        r = self.row("Speaking speed")
        self.slider(r, "edge_rate", "+8%", -30, 40, 2, restart=True, fmt="percent")
        r = self.row("Speak replies out loud", "Off = replies are shown but not spoken.")
        self.switch(r, "speak_replies", True, restart=True)

        self.section("Listening")
        r = self.row("Wake phrase", "Say it to start talking. Detected on your PC; nothing is sent until you say it.")
        self.dropdown(r, "wake_word", ui.WAKE_WORDS, "hey_jarvis", restart=True)
        r = self.row("Wake phrase sensitivity", "Lower = hears you more easily; higher = fewer false alarms.")
        self.slider(r, "wake_sensitivity", 0.5, 0.3, 0.8, 0.05, restart=True)
        r = self.row("Listen for my answer after a question", "Reopens the mic when Wisp asks you something.")
        self.switch(r, "follow_up_listening", True)
        r = self.row("Push-to-talk key")
        self.text(r, "talk_key", "f9", width=10, restart=True)

        self.section("Look")
        r = self.row("Colour")
        swatches = tk.Frame(r, bg=ui.CARD)
        swatches.pack()
        self.swatch_widgets = []
        for colour in ui.ACCENTS:
            c = tk.Canvas(swatches, width=24, height=24, bg=ui.CARD, highlightthickness=0, cursor="hand2")
            c.pack(side="left", padx=2)
            c.bind("<ButtonRelease-1>", lambda e, col=colour: self.pick_colour(col))
            self.swatch_widgets.append((c, colour))
        self.pick_colour(self.cfg.get("accent_colour", ui.ACCENTS[0]), initial=True)
        r = self.row("Full-screen HUD when talking", "Off = just the corner orb.")
        self.switch(r, "full_hud", True)
        r = self.row("HUD background darkness")
        self.slider(r, "hud_dim", 0.55, 0.0, 0.9, 0.05)
        r = self.row("Show / hide shortcut")
        self.text(r, "show_hide_key", "ctrl+shift+space", width=18, restart=True)
        r = self.row("Full HUD shortcut")
        self.text(r, "hud_key", "ctrl+shift+j", width=18, restart=True)

        self.section("System")
        if sys.platform == "win32":
            r = self.row(f"Start {APP_NAME} with Windows", "Starts hidden in the tray.")
            ui.Switch(r, autostart.is_enabled(), lambda v: autostart.set_enabled(v), self.accent).pack()
        r = self.row("Share anonymous usage stats",
                     "Helps the developer improve Wisp. Never includes what you say, files or your location.")
        self.switch(r, "share_usage_stats", True)
        ui.FlatButton(self.body, "What's sent? (PRIVACY.md)", lambda: ui.open_file(ui.ROOT / "PRIVACY.md"),
                      bg=ui.BG, font=self.f["small"]).pack(anchor="w", padx=20)

        self.section("Updates")
        r = self.row(f"{APP_NAME} {VERSION}", "Checks for new versions automatically twice a day.")
        ui.FlatButton(r, "Check now", self.check_updates, font=self.f["small"]).pack()
        self.update_label = tk.Label(self.body, text="", bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w",
                                     wraplength=540, justify="left")
        self.update_label.pack(fill="x", padx=20)
        tk.Frame(self.body, bg=ui.BG, height=20).pack()

    # ---------- actions ----------
    def pick_colour(self, colour, initial=False):
        for c, col in self.swatch_widgets:
            c.delete("all")
            c.create_oval(3, 3, 21, 21, fill=col, outline="#ffffff" if col == colour else col, width=2)
        if not initial:
            self._set("accent_colour", colour, restart=True)

    def change_key(self):
        for w in self.key_area.winfo_children():
            w.destroy()
        row = tk.Frame(self.key_area, bg=ui.BG)
        row.pack(fill="x", pady=6)
        e = ui.entry(row, "", show="•", width=40, f=self.f["body"])
        e.pack(side="left", ipady=4)
        status = tk.Label(self.key_area, bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w")
        status.pack(fill="x")

        def check():
            status.config(text="Checking…", fg=ui.DIM)

            def work():
                ok, msg = credentials.check_api_key(e.get())
                if ok:
                    credentials.save_api_key(e.get())
                    self.needs_restart = True
                self.win.after(0, lambda: status.config(text=("✓ Saved. " if ok else "✗ ") + msg,
                                                        fg=ui.GREEN if ok else ui.RED))
            threading.Thread(target=work, daemon=True).start()
        ui.FlatButton(row, "Check & save", check, bg=self.accent, fg="#031018", hover=self.accent,
                      font=self.f["small"]).pack(side="left", padx=6)
        ui.FlatButton(row, "Get a key", lambda: ui.open_url("https://console.anthropic.com/settings/keys"),
                      font=self.f["small"]).pack(side="left")

    def preview(self):
        import voice
        cfg = dict(ui.load_config(), **self.changes)
        voice.Speaker(cfg).speak("Good evening. This is how I sound.")

    def check_updates(self):
        self.update_label.config(text="Checking…", fg=ui.DIM)

        def work():
            import app_info
            import updates
            if not app_info.repo_configured():
                msg, colour = "Updates aren't set up in this copy (no GitHub repo in app_info.py).", ui.DIM
            else:
                try:
                    info = updates.check()
                    if info:
                        msg, colour = f"Version {info['version']} is available! Use “Update now” in the menu.", self.accent
                        self.app.events.put(("ui_update", info))
                    else:
                        msg, colour = "You're on the latest version.", ui.GREEN
                except Exception as exc:
                    msg, colour = f"Couldn't check: {exc}", ui.RED
            self.win.after(0, lambda: self.update_label.config(text=msg, fg=colour))
        threading.Thread(target=work, daemon=True).start()

    def save(self):
        if not self.changes:
            self.win.destroy()
            return
        if "share_usage_stats" in self.changes:
            telemetry.set_enabled(self.app.cfg, self.changes["share_usage_stats"])
        ui.save_config(self.changes)
        live = {k: v for k, v in self.changes.items()
                if k in ("user_name", "follow_up_listening", "full_hud", "hud_dim", "share_usage_stats")}
        self.app.cfg.update(live)  # these apply straight away
        if self.needs_restart:
            self.status.config(text="Saved. Some changes need a restart.", fg=self.accent)
            for w in self.win.pack_slaves()[-1].pack_slaves():
                if isinstance(w, ui.FlatButton) and w.cget("text") == "Save":
                    w.config(text="Restart now")
                    w.command = self.app.restart
            self.changes = {}
        else:
            self.win.destroy()
