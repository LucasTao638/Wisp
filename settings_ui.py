"""Settings window: everything in config.json, with switches and dropdowns instead of editing a file."""
import sys
import threading
import tkinter as tk

import autostart
import claude_setup
import credentials
import i18n
import telemetry
import ui_kit as ui
from app_info import APP_NAME, VERSION
from i18n import L

def models():
    return [("", L("Default", "默认")),
            ("sonnet", L("Sonnet - fast, smart (recommended)", "Sonnet - 快速、聪明（推荐）")),
            ("haiku", L("Haiku - fastest, cheapest", "Haiku - 最快、最便宜")),
            ("opus", L("Opus - smartest, slowest, most expensive", "Opus - 最聪明、最慢、最贵"))]


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.cfg = ui.load_config()
        self.accent = self.cfg.get("accent_colour", "#38d6ff")
        self.changes = {}
        self.needs_restart = False
        win = self.win = tk.Toplevel(app.root, bg=ui.BG)
        win.title(L(f"{APP_NAME} settings", f"{APP_NAME} 设置"))
        win.geometry("600x720")
        self.f = ui.fonts(win)

        tk.Label(win, text=L("S E T T I N G S", "设  置"), bg=ui.BG, fg=self.accent, font=self.f["title"]).pack(pady=(18, 6))
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
        self.save_btn = ui.FlatButton(bottom, L("Save", "保存"), self.save, bg=self.accent, fg="#031018", hover=self.accent).pack(side="right")
        ui.FlatButton(bottom, L("Cancel", "取消"), win.destroy).pack(side="right", padx=8)

    # ---------- layout helpers ----------
    def section(self, title):
        tk.Label(self.body, text=title if i18n.is_zh() else " ".join(title.upper()), bg=ui.BG, fg=self.accent, font=self.f["head"],
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
        self.section(L("Language", "语言"))
        r = self.row(L("Language", "语言"), L("What you speak and how Wisp answers. Also switches the voice and "
                                              "speech recognition to suit. Needs a restart.",
                                              "你说的语言和 Wisp 回答的语言，同时切换合适的声音和语音识别。需要重启。"))
        self.language_dropdown(r)

        self.section("Claude")
        r = self.row(L("Anthropic API key", "Anthropic API 密钥"),
                     L(f"Currently: {credentials.masked()}. Stored encrypted on this computer.",
                       f"当前：{credentials.masked()}。加密保存在本机。"))
        btns = tk.Frame(r, bg=ui.CARD)
        btns.pack()
        ui.FlatButton(btns, L("Change", "更改"), self.change_key, font=self.f["small"]).pack(side="left")
        if credentials.has_api_key():
            ui.FlatButton(btns, L("Remove", "删除"), self.remove_key, font=self.f["small"]).pack(side="left", padx=(6, 0))
        self.key_area = tk.Frame(self.body, bg=ui.BG)
        self.key_area.pack(fill="x", padx=20)
        claude_setup.status_card(self.body, self.f, self.accent, credentials.load_api_key).pack(
            fill="x", padx=20, pady=(6, 4))
        r = self.row(L("Model", "模型"), L("Which Claude model answers you.", "由哪个 Claude 模型回答你。"))
        self.dropdown(r, "model", models(), "sonnet", restart=True)

        self.section(L("You", "你"))
        r = self.row(L("Your name", "你的名字"), L("Used in greetings and the HUD.", "用于问候和全屏界面。"))
        self.text(r, "user_name")

        self.section(L("Voice", "声音"))
        r = self.row(L("Voice", "声音"))
        voices = ui.VOICES_ZH + ui.VOICES if i18n.is_zh() else ui.VOICES + ui.VOICES_ZH
        self.voice_var = self.dropdown(r, "edge_voice", voices, voices[0][0], restart=True)
        r = self.row(L("Hear it", "试听"), L("Plays a sample with the voice and speed above.", "用上面的声音和语速播放一段示例。"))
        ui.FlatButton(r, L("▶ Preview", "▶ 试听"), self.preview, font=self.f["small"]).pack()
        r = self.row(L("Speaking speed", "语速"))
        self.slider(r, "edge_rate", "+8%", -30, 40, 2, restart=True, fmt="percent")
        r = self.row(L("Speak replies out loud", "朗读回复"), L("Off = replies are shown but not spoken.", "关闭后只显示回复，不朗读。"))
        self.switch(r, "speak_replies", True, restart=True)

        self.section(L("Listening", "聆听"))
        r = self.row(L("Wake phrase", "唤醒词"),
                     L("Say it to start talking. Detected on your computer; nothing is sent until you say it.",
                       "说出它即可开始对话。在本机检测，说出之前不会发送任何内容。唤醒词目前只有英文。"))
        wake_words = [(c, lab if c else L(lab, "关闭（使用快捷键或点击光球）")) for c, lab in ui.WAKE_WORDS]
        self.dropdown(r, "wake_word", wake_words, "hey_jarvis", restart=True)
        r = self.row(L("Wake phrase sensitivity", "唤醒灵敏度"),
                     L("Lower = hears you more easily; higher = fewer false alarms.", "越低越容易听到你；越高误唤醒越少。"))
        self.slider(r, "wake_sensitivity", 0.5, 0.3, 0.8, 0.05, restart=True)
        r = self.row(L("Listen for my answer after a question", "提问后自动聆听回答"),
                     L("Reopens the mic when Wisp asks you something.", "Wisp 向你提问时自动重新打开麦克风。"))
        self.switch(r, "follow_up_listening", True)
        r = self.row(L("Push-to-talk key", "按住说话键"), L("e.g. f9, alt_r (Right Alt / Option), ctrl+alt+t",
                                                         "例如 f9、alt_r（右 Alt / Option）、ctrl+alt+t"))
        self.text(r, "talk_key", "f9", width=10, restart=True)

        r = self.row(L("Conversation mode", "对话模式"),
                     L("After each reply, keep listening so you can just carry on - no wake phrase. "
                       "Say “that's all” or stay quiet to finish.",
                       "每次回答后继续听，你可以直接接着说，不用唤醒词。说“没事了”或不说话即结束。"))
        self.switch(r, "conversation_mode", True)
        r = self.row(L("Keep listening for", "继续听多久"), L("Seconds after each reply.", "每次回答后的秒数。"))
        self.slider(r, "conversation_seconds", 8, 4, 20, 1)
        r = self.row(L("I use headphones", "我戴耳机"),
                     L("Then you can just start talking while Wisp is speaking to interrupt it. "
                       "(Leave off with speakers: Wisp would hear itself.)",
                       "这样 Wisp 说话时你直接开口就能打断它。（用扬声器时请关闭，否则 Wisp 会听到自己。）"))
        self.switch(r, "headphones_mode", False)
        r = self.row(L("Talking over Wisp interrupts it", "说话时打断 Wisp"),
                     L("A new spoken request stops the current one. Off = it waits its turn.",
                       "新的语音请求会停止当前任务。关闭后会排队等待。"))
        self.switch(r, "talking_interrupts", True)
        r = self.row(L("Wait if I sound unfinished", "我没说完时继续等"),
                     L("Keeps listening after “…and” or “um”.", "听到“然后”“嗯”之类时继续听。"))
        self.switch(r, "wait_for_unfinished", True, restart=True)
        r = self.row(L("Pause that means I've finished", "多长的停顿算说完"), L("Seconds of quiet.", "安静的秒数。"))
        self.slider(r, "finished_talking_pause", 1.2, 0.6, 3.0, 0.1, restart=True)

        self.section(L("Look", "外观"))
        r = self.row(L("Colour", "颜色"))
        swatches = tk.Frame(r, bg=ui.CARD)
        swatches.pack()
        self.swatch_widgets = []
        for colour in ui.ACCENTS:
            c = tk.Canvas(swatches, width=24, height=24, bg=ui.CARD, highlightthickness=0, cursor="hand2")
            c.pack(side="left", padx=2)
            c.bind("<ButtonRelease-1>", lambda e, col=colour: self.pick_colour(col))
            self.swatch_widgets.append((c, colour))
        self.pick_colour(self.cfg.get("accent_colour", ui.ACCENTS[0]), initial=True)
        r = self.row(L("When you talk to Wisp", "和 Wisp 对话时"),
                     L("Side widget doesn't dim the screen.", "侧边小窗不会让屏幕变暗。"))
        self.dropdown(r, "talk_view", [("widget", L("Show the side widget", "显示侧边小窗")),
                                       ("hud", L("Show the full-screen HUD", "显示全屏界面")),
                                       ("orb", L("Just the orb", "只显示光球"))], "widget")
        r = self.row(L("HUD background darkness", "全屏界面背景暗度"))
        self.slider(r, "hud_dim", 0.55, 0.0, 0.9, 0.05)
        r = self.row(L("Show / hide shortcut", "显示 / 隐藏快捷键"))
        self.text(r, "show_hide_key", "ctrl+shift+space", width=18, restart=True)
        r = self.row(L("Full HUD shortcut", "全屏界面快捷键"))
        self.text(r, "hud_key", "ctrl+shift+j", width=18, restart=True)

        self.section(L("System", "系统"))
        if sys.platform in ("win32", "darwin"):
            r = self.row(L(f"Start {APP_NAME} when I log in", f"登录时自动启动 {APP_NAME}"), L("Starts hidden.", "启动后隐藏。"))
            ui.Switch(r, autostart.is_enabled(), lambda v: autostart.set_enabled(v), self.accent).pack()
        r = self.row(L("Share anonymous usage stats", "分享匿名使用统计"),
                     L("Helps the developer improve Wisp. Never includes what you say, files or your location.",
                       "帮助开发者改进 Wisp。绝不包含你说的话、文件或你的位置。"))
        self.switch(r, "share_usage_stats", True)
        ui.FlatButton(self.body, L("What's sent? (PRIVACY.md)", "会发送什么？（PRIVACY.md）"), lambda: ui.open_file(ui.ROOT / "PRIVACY.md"),
                      bg=ui.BG, font=self.f["small"]).pack(anchor="w", padx=20)

        self.section(L("Feedback", "反馈"))
        r = self.row(L("Suggest an improvement or report a problem", "提出改进建议或报告问题"),
                     L("Goes straight to the developer. You can also just say “I have a suggestion: …”.",
                       "直接发送给开发者。也可以直接说“我有个建议：……”。"))
        ui.FlatButton(r, L("Send feedback", "发送反馈"), self.open_feedback, font=self.f["small"]).pack()

        self.section(L("Updates", "更新"))
        r = self.row(f"{APP_NAME} {VERSION}", L("Checks for new versions automatically twice a day.", "每天自动检查两次新版本。"))
        ui.FlatButton(r, L("Check now", "立即检查"), self.check_updates, font=self.f["small"]).pack()
        self.update_label = tk.Label(self.body, text="", bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w",
                                     wraplength=540, justify="left")
        self.update_label.pack(fill="x", padx=20)
        tk.Frame(self.body, bg=ui.BG, height=20).pack()

    def language_dropdown(self, parent):
        options = list(i18n.LANGUAGES.items())
        var = tk.StringVar(value=i18n.LANGUAGES.get(self.cfg.get("language", "en"), options[0][1]))

        def picked(label):
            code = next(c for c, lab in options if lab == label)
            if code == self.cfg.get("language", "en") and "language" not in self.changes:
                return
            self.changes.update(i18n.LANGUAGE_DEFAULTS[code])
            self.changes["language"] = code
            self.needs_restart = True
            voice_label = dict(ui.VOICES + ui.VOICES_ZH).get(self.changes["edge_voice"])
            if voice_label and hasattr(self, "voice_var"):
                self.voice_var.set(voice_label)
            self.status.config(text=L("Restart to switch language.", "重启后切换语言。"), fg=self.accent)
        menu = tk.OptionMenu(parent, var, *[lab for _, lab in options], command=picked)
        menu.config(bg="#1a222c", fg=ui.TEXT, activebackground=self.accent, activeforeground="#031018",
                    highlightthickness=0, bd=0, font=self.f["small"], width=30)
        menu["menu"].config(bg="#1a222c", fg=ui.TEXT, activebackground=self.accent, activeforeground="#031018")
        menu.pack()

    def open_feedback(self):
        show = getattr(self.app, "show_feedback", None)
        if show:
            show()
        else:
            import feedback
            feedback.FeedbackWindow(self.win, "", self.accent)

    # ---------- actions ----------
    def pick_colour(self, colour, initial=False):
        for c, col in self.swatch_widgets:
            c.delete("all")
            c.create_oval(3, 3, 21, 21, fill=col, outline="#ffffff" if col == colour else col, width=2)
        if not initial:
            self._set("accent_colour", colour, restart=True)

    def remove_key(self):
        """Forget the saved key, so Claude Code's own sign-in is used instead."""
        credentials.save_api_key("")
        self.needs_restart = True
        for w in self.key_area.winfo_children():
            w.destroy()
        tk.Label(self.key_area, text=L("✓ Key removed. Wisp will use Claude Code's own sign-in after a restart.",
                                       "✓ 密钥已删除。重启后 Wisp 将使用 Claude Code 自己的登录。"),
                 bg=ui.BG, fg=ui.GREEN, font=self.f["small"], anchor="w").pack(fill="x", pady=4)

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
            status.config(text=L("Checking…", "正在验证……"), fg=ui.DIM)

            def work():
                ok, msg = credentials.check_api_key(e.get())
                if ok:
                    credentials.save_api_key(e.get())
                    self.needs_restart = True
                self.win.after(0, lambda: status.config(text=("✓ " + L("Saved. " + msg, "已保存。") if ok else "✗ " + msg),
                                                        fg=ui.GREEN if ok else ui.RED))
            threading.Thread(target=work, daemon=True).start()
        ui.FlatButton(row, L("Check & save", "验证并保存"), check, bg=self.accent, fg="#031018", hover=self.accent,
                      font=self.f["small"]).pack(side="left", padx=6)
        ui.FlatButton(row, L("Get a key", "获取密钥"), lambda: ui.open_url("https://console.anthropic.com/settings/keys"),
                      font=self.f["small"]).pack(side="left")

    def preview(self):
        import voice
        cfg = dict(ui.load_config(), **self.changes)
        zh = str(cfg.get("edge_voice", "")).startswith("zh-")
        voice.Speaker(cfg).speak("晚上好，这是我的声音。" if zh else "Good evening. This is how I sound.")

    def check_updates(self):
        self.update_label.config(text=L("Checking…", "正在检查……"), fg=ui.DIM)

        def work():
            import app_info
            import updates
            if not app_info.repo_configured():
                msg, colour = L("Updates aren't set up in this copy (no GitHub repo in app_info.py).",
                                "此版本未配置更新（app_info.py 中没有 GitHub 仓库）。"), ui.DIM
            else:
                try:
                    info = updates.check()
                    if info:
                        msg, colour = L(f"Version {info['version']} is available! Use “Update now” in the menu.",
                                        f"新版本 {info['version']} 可用！请使用菜单中的“立即更新”。"), self.accent
                        self.app.events.put(("ui_update", info))
                    else:
                        msg, colour = L("You're on the latest version.", "已是最新版本。"), ui.GREEN
                except Exception as exc:
                    msg, colour = L(f"Couldn't check: {exc}", f"检查失败：{exc}"), ui.RED
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
                if k in ("user_name", "follow_up_listening", "full_hud", "hud_dim", "share_usage_stats", "talk_view",
                         "talking_interrupts", "widget_hide_seconds", "conversation_mode", "conversation_seconds",
                         "headphones_mode")}
        self.app.cfg.update(live)  # these apply straight away
        if self.needs_restart:
            self.status.config(text=L("Saved. Some changes need a restart.", "已保存。部分更改需要重启。"), fg=self.accent)
            self.save_btn.config(text=L("Restart now", "立即重启"))
            self.save_btn.command = self.app.restart
            self.changes = {}
        else:
            self.win.destroy()
