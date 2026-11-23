"""First-run setup: API key, your name, voice, wake word, start with Windows, usage stats.
Runs automatically the first time Wisp starts (or any time: py setup_wizard.py)."""
import sys
import threading
import tkinter as tk

import autostart
import credentials
import ui_kit as ui
from app_info import APP_NAME, VERSION

KEYS_URL = "https://console.anthropic.com/settings/keys"


class SetupWizard:
    def __init__(self, root=None):
        self.cfg = ui.load_config()
        self.accent = self.cfg.get("accent_colour", "#38d6ff")
        self.root = root or tk.Tk()
        r = self.root
        r.title(f"Set up {APP_NAME}")
        r.configure(bg=ui.BG)
        r.geometry("620x560")
        r.resizable(False, False)
        self.f = ui.fonts(r)
        self.choices = {
            "name": self.cfg.get("user_name", ""),
            "voice": self.cfg.get("edge_voice", "en-GB-RyanNeural"),
            "wake": self.cfg.get("wake_word", "hey_jarvis"),
            "autostart": autostart.is_enabled() if sys.platform == "win32" else False,
            "stats": self.cfg.get("share_usage_stats", True),
        }
        self.key_ok = credentials.has_api_key()
        self.pages = [self.page_welcome, self.page_key, self.page_you, self.page_listen, self.page_stats, self.page_done]
        self.index = 0
        self.body = tk.Frame(r, bg=ui.BG)
        self.body.pack(fill="both", expand=True, padx=36, pady=(28, 0))
        nav = tk.Frame(r, bg=ui.BG)
        nav.pack(fill="x", padx=36, pady=22)
        self.dots = tk.Label(nav, bg=ui.BG, fg=ui.DIM, font=self.f["small"])
        self.dots.pack(side="left")
        self.next_btn = ui.FlatButton(nav, "Next", self.next, bg=self.accent, fg="#031018", hover=self.accent)
        self.next_btn.pack(side="right")
        self.back_btn = ui.FlatButton(nav, "Back", self.back)
        self.back_btn.pack(side="right", padx=8)
        self.show()

    # ---------- navigation ----------
    def show(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.pages[self.index]()
        self.dots.config(text="  ".join("●" if i == self.index else "○" for i in range(len(self.pages))))
        self.back_btn.set_enabled(self.index > 0)
        self.next_btn.config(text="Start Wisp" if self.index == len(self.pages) - 1 else "Next")

    def next(self):
        if self.index == len(self.pages) - 1:
            self.finish()
            return
        if self.pages[self.index] == self.page_you:
            self.choices["name"] = self.name_entry.get().strip()
        self.index += 1
        self.show()

    def back(self):
        if self.index > 0:
            self.index -= 1
            self.show()

    def heading(self, title, text):
        tk.Label(self.body, text=title, bg=ui.BG, fg=self.accent, font=self.f["title"], anchor="w").pack(fill="x")
        tk.Label(self.body, text=text, bg=ui.BG, fg=ui.TEXT, font=self.f["body"], justify="left", anchor="w",
                 wraplength=540).pack(fill="x", pady=(8, 14))

    # ---------- pages ----------
    def page_welcome(self):
        self.heading(f"Welcome to {APP_NAME}",
                     f"{APP_NAME} is a voice assistant that can use your PC for you: search the web properly, "
                     "open and control apps, run long tasks in the background, set timers and routines, "
                     "and more.\n\nThis takes about two minutes.")
        tk.Label(self.body, text=f"Version {VERSION}  ·  free and open source (MIT licence)", bg=ui.BG,
                 fg=ui.DIM, font=self.f["small"], anchor="w").pack(fill="x", pady=(30, 0))

    def page_key(self):
        self.heading("Connect to Claude",
                     f"{APP_NAME}'s brain is Claude, made by Anthropic. Apps like this one use your own "
                     "Anthropic API key: you pay Anthropic only for what you use (typically a few cents per "
                     "request, more for big tasks), and you can set a monthly spending limit in their console.\n\n"
                     "Your key is stored encrypted on this PC and never leaves it except to talk to Anthropic.")
        row = tk.Frame(self.body, bg=ui.BG)
        row.pack(fill="x")
        ui.FlatButton(row, "1. Get a key (opens Anthropic)", lambda: ui.open_url(KEYS_URL)).pack(side="left")
        tk.Label(self.body, text="2. Paste it here:", bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w").pack(
            fill="x", pady=(16, 4))
        row2 = tk.Frame(self.body, bg=ui.BG)
        row2.pack(fill="x")
        self.key_entry = ui.entry(row2, "", show="•", width=44, f=self.f["body"])
        self.key_entry.pack(side="left", ipady=6)
        ui.FlatButton(row2, "Check & save", self.check_key, bg=self.accent, fg="#031018",
                      hover=self.accent).pack(side="left", padx=8)
        self.key_status = tk.Label(self.body, bg=ui.BG, font=self.f["body"], anchor="w")
        self.key_status.pack(fill="x", pady=10)
        if self.key_ok:
            self.key_status.config(text=f"✓ A key is already saved ({credentials.masked()}).", fg=ui.GREEN)
        tk.Label(self.body, text="Already set up Claude Code your own way? You can press Next to skip this.",
                 bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w", wraplength=540, justify="left").pack(
            fill="x", pady=(18, 0))

    def check_key(self):
        key = self.key_entry.get().strip()
        self.key_status.config(text="Checking…", fg=ui.DIM)

        def work():
            ok, msg = credentials.check_api_key(key)
            if ok:
                credentials.save_api_key(key)
                self.key_ok = True
            self.root.after(0, lambda: self.key_status.config(
                text=("✓ " if ok else "✗ ") + msg + (" Saved." if ok else ""), fg=ui.GREEN if ok else ui.RED))
        threading.Thread(target=work, daemon=True).start()

    def page_you(self):
        self.heading("About you", "What should I call you? (Optional.)")
        self.name_entry = ui.entry(self.body, self.choices["name"], width=30, f=self.f["body"])
        self.name_entry.pack(anchor="w", ipady=6)
        tk.Label(self.body, text="Pick a voice:", bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w").pack(
            fill="x", pady=(22, 6))
        self.voice_var = tk.StringVar(value=self.choices["voice"])
        for code, label in ui.VOICES:
            row = tk.Frame(self.body, bg=ui.BG)
            row.pack(fill="x")
            tk.Radiobutton(row, text=label, value=code, variable=self.voice_var, bg=ui.BG, fg=ui.TEXT,
                           selectcolor=ui.CARD, activebackground=ui.BG, activeforeground=ui.TEXT,
                           font=self.f["body"], command=lambda: self.choices.update(voice=self.voice_var.get())
                           ).pack(side="left")
            ui.FlatButton(row, "▶", lambda c=code: self.preview(c), font=self.f["small"]).pack(side="left", padx=6)

    def preview(self, voice_code):
        import voice
        cfg = dict(self.cfg, voice_engine="edge", edge_voice=voice_code)
        name = self.name_entry.get().strip() if hasattr(self, "name_entry") else ""
        voice.Speaker(cfg).speak(f"Good evening{', ' + name if name else ''}. All systems are online.")

    def page_listen(self):
        self.heading("Talking to me", "Hold F9 (or click the orb) any time to talk. You can also turn on a wake "
                     "phrase so you can just say it. Listening for it happens entirely on your PC.")
        self.wake_var = tk.StringVar(value=self.choices["wake"])
        for code, label in ui.WAKE_WORDS:
            tk.Radiobutton(self.body, text=label, value=code, variable=self.wake_var, bg=ui.BG, fg=ui.TEXT,
                           selectcolor=ui.CARD, activebackground=ui.BG, activeforeground=ui.TEXT, font=self.f["body"],
                           anchor="w", command=lambda: self.choices.update(wake=self.wake_var.get())).pack(fill="x")
        if sys.platform == "win32":
            row = tk.Frame(self.body, bg=ui.BG)
            row.pack(fill="x", pady=(24, 0))
            tk.Label(row, text=f"Start {APP_NAME} when I log in to Windows", bg=ui.BG, fg=ui.TEXT,
                     font=self.f["body"]).pack(side="left")
            ui.Switch(row, self.choices["autostart"], lambda v: self.choices.update(autostart=v), self.accent,
                      bg=ui.BG).pack(side="right")

    def page_stats(self):
        self.heading("Anonymous usage stats",
                     f"{APP_NAME} is free and made by one developer. To see whether people keep using it and which "
                     "features matter, it sends anonymous usage stats: a random ID, the version, that it was used "
                     "today, and which kinds of features were used (like “timer” or “routine”).\n\n"
                     "It never sends anything you say or type, Claude's replies, files, screenshots or your location.")
        row = tk.Frame(self.body, bg=ui.CARD, padx=16, pady=12)
        row.pack(fill="x", pady=(4, 10))
        tk.Label(row, text="Share anonymous usage stats", bg=ui.CARD, fg=ui.TEXT, font=self.f["body"]).pack(side="left")
        ui.Switch(row, self.choices["stats"], lambda v: self.choices.update(stats=v), self.accent).pack(side="right")
        ui.FlatButton(self.body, "Read exactly what's sent (PRIVACY.md)",
                      lambda: ui.open_file(ui.ROOT / "PRIVACY.md"), font=self.f["small"]).pack(anchor="w")
        tk.Label(self.body, text="You can change this any time in Settings.", bg=ui.BG, fg=ui.DIM,
                 font=self.f["small"], anchor="w").pack(fill="x", pady=(10, 0))

    def page_done(self):
        self.heading("All set", "Here's how to use me:")
        wake = dict(ui.WAKE_WORDS).get(self.choices["wake"], "")
        tips = [("F9", "hold to talk (or click the orb)")]
        if self.choices["wake"]:
            tips.insert(0, (wake, "say it any time, then ask"))
        tips += [("Right-click the orb", "menu: settings, routines, connect your phone"),
                 ("Ctrl+Shift+J", "full-screen HUD"), ("Ctrl+Shift+Space", "hide / show"),
                 ("“in the background, …”", "run long tasks while you keep working"),
                 ("“when I say X, do Y”", "make your own routine")]
        for key, what in tips:
            row = tk.Frame(self.body, bg=ui.BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=key, bg=ui.BG, fg=self.accent, font=self.f["head"], width=24, anchor="w").pack(side="left")
            tk.Label(row, text=what, bg=ui.BG, fg=ui.TEXT, font=self.f["body"], anchor="w").pack(side="left")
        if not self.key_ok:
            tk.Label(self.body, text="No API key saved. If Claude Code isn't set up another way, add one in Settings.",
                     bg=ui.BG, fg=ui.RED, font=self.f["small"], anchor="w", wraplength=540).pack(fill="x", pady=(16, 0))

    # ---------- save ----------
    def finish(self):
        c = self.choices
        ui.save_config({"user_name": c["name"], "edge_voice": c["voice"], "voice_engine": "edge",
                        "wake_word": c["wake"], "share_usage_stats": bool(c["stats"]), "setup_done": True})
        if sys.platform == "win32":
            try:
                autostart.set_enabled(c["autostart"])
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SetupWizard().run()
