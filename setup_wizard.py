"""First-run setup: language, API key, your name, voice, wake word, start at login, usage stats.
Runs automatically the first time Wisp starts (or any time: py setup_wizard.py)."""
import sys
import threading
import tkinter as tk

import autostart
import claude_setup
import credentials
import i18n
import ui_kit as ui
from app_info import APP_NAME, VERSION
from i18n import L

KEYS_URL = "https://console.anthropic.com/settings/keys"
LIMITS_URL = "https://console.anthropic.com/settings/limits"


class SetupWizard:
    def __init__(self, root=None):
        i18n.load_language()
        self.cfg = ui.load_config()
        self.accent = self.cfg.get("accent_colour", "#38d6ff")
        self.root = root or tk.Tk()
        r = self.root
        r.title(APP_NAME)
        r.configure(bg=ui.BG)
        r.geometry("620x700")
        r.resizable(False, False)
        self.f = ui.fonts(r)
        self.choices = {
            "name": self.cfg.get("user_name", ""),
            "voice": self.cfg.get("edge_voice", "en-GB-RyanNeural"),
            "wake": self.cfg.get("wake_word", "hey_jarvis"),
            "autostart": autostart.is_enabled() if sys.platform in ("win32", "darwin") else False,
            "stats": self.cfg.get("share_usage_stats", True),
        }
        self.key_ok = credentials.has_api_key()
        self.connected = False
        self.pages = [self.page_language, self.page_welcome, self.page_key, self.page_you, self.page_listen,
                      self.page_stats, self.page_done]
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
        last = self.index == len(self.pages) - 1
        self.next_btn.config(text=L("Start Wisp", "启动 Wisp") if last else L("Next", "下一步"))
        self.back_btn.config(text=L("Back", "上一步"))

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
            if self.pages[self.index] == self.page_you:
                self.choices["name"] = self.name_entry.get().strip()
            self.index -= 1
            self.show()

    def heading(self, title, text):
        tk.Label(self.body, text=title, bg=ui.BG, fg=self.accent, font=self.f["title"], anchor="w").pack(fill="x")
        tk.Label(self.body, text=text, bg=ui.BG, fg=ui.TEXT, font=self.f["body"], justify="left", anchor="w",
                 wraplength=540).pack(fill="x", pady=(8, 14))

    # ---------- pages ----------
    def page_language(self):
        self.heading("Language  ·  语言",
                     "Choose the language you'll speak to Wisp in.\n选择你和 Wisp 对话的语言。")
        for code, label in i18n.LANGUAGES.items():
            selected = i18n.LANG == code
            ui.FlatButton(self.body, ("●  " if selected else "○  ") + label, lambda c=code: self.pick_language(c),
                          bg=self.accent if selected else ui.CARD, fg="#031018" if selected else ui.TEXT,
                          hover=self.accent, font=self.f["head"]).pack(fill="x", pady=4, ipady=6)
        tk.Label(self.body,
                 text="Wake phrases (“Hey Jarvis”) are English-only for now; holding the talk key works in any language.\n"
                      "唤醒词（“Hey Jarvis”）目前只有英文；按住说话键可以使用任何语言。",
                 bg=ui.BG, fg=ui.DIM, font=self.f["small"], justify="left", anchor="w",
                 wraplength=540).pack(fill="x", pady=(24, 0))

    def pick_language(self, code):
        i18n.apply_language(code, ui.save_config)
        self.cfg = ui.load_config()
        self.choices["voice"] = self.cfg.get("edge_voice", self.choices["voice"])
        self.show()

    def page_welcome(self):
        self.heading(L(f"Welcome to {APP_NAME}", f"欢迎使用 {APP_NAME}"),
                     L(f"{APP_NAME} is a voice assistant that can use your computer for you: search the web properly, "
                       "open and control apps, run long tasks in the background, set timers and routines, "
                       "and more.\n\nThis takes about two minutes.",
                       f"{APP_NAME} 是一个能替你操作电脑的语音助手：认真搜索网络、打开和控制应用、在后台处理耗时任务、"
                       "设置计时器和例程等等。\n\n设置大约需要两分钟。"))
        tk.Label(self.body, text=L(f"Version {VERSION}  ·  free and open source (MIT licence)",
                                   f"版本 {VERSION}  ·  免费开源（MIT 许可）"), bg=ui.BG,
                 fg=ui.DIM, font=self.f["small"], anchor="w").pack(fill="x", pady=(30, 0))

    def page_key(self):
        self.heading(L("Connect to Claude", "连接 Claude"),
                     L(f"{APP_NAME} needs an Anthropic API key to think. It's pay-as-you-go: "
                       "most requests cost about a cent.",
                       f"{APP_NAME} 需要一个 Anthropic API 密钥来思考。按用量付费：大多数请求大约一美分。"))
        self.claude_card = claude_setup.status_card(self.body, self.f, self.accent, credentials.load_api_key,
                                                    on_ready=self.mark_connected)
        self.claude_card.pack(fill="x", pady=(0, 12))

        # Step 1: get a key
        self.step(1, L("Get a key", "获取密钥"),
                  L("Sign in, add a few dollars of credit under Billing, then click “Create Key” and copy it.",
                    "登录后在“Billing”里充值几美元，然后点击“Create Key”并复制。"))
        ui.FlatButton(self.body, L("Open Anthropic Console", "打开 Anthropic 控制台"),
                      lambda: ui.open_url(KEYS_URL), font=self.f["small"]).pack(anchor="w", padx=(30, 0))

        # Step 2: paste it
        self.step(2, L("Paste it here", "粘贴到这里"), None)
        row = tk.Frame(self.body, bg=ui.BG)
        row.pack(fill="x", padx=(30, 0))
        self.key_entry = ui.entry(row, "", show="•", width=34, f=self.f["body"])
        self.key_entry.pack(side="left", ipady=5)
        self.key_entry.bind("<Return>", lambda e: self.check_key())
        ui.FlatButton(row, L("Paste", "粘贴"), self.paste_key, font=self.f["small"]).pack(side="left", padx=(6, 0))
        ui.FlatButton(row, L("Check & save", "验证并保存"), self.check_key, bg=self.accent, fg="#031018",
                      hover=self.accent, font=self.f["small"]).pack(side="left", padx=6)
        self.key_status = tk.Label(self.body, bg=ui.BG, font=self.f["small"], anchor="w")
        self.key_status.pack(fill="x", padx=(30, 0), pady=(4, 0))
        if self.key_ok:
            self.key_status.config(text=L(f"✓ A key is already saved ({credentials.masked()}).",
                                          f"✓ 已保存密钥（{credentials.masked()}）。"), fg=ui.GREEN)

        # Step 3: spending limit
        self.step(3, L("Set a monthly limit (recommended)", "设置每月上限（建议）"),
                  L("So you never spend more than you planned.", "这样花费永远不会超出预算。"))
        ui.FlatButton(self.body, L("Open spending limits", "打开消费上限设置"), lambda: ui.open_url(LIMITS_URL),
                      font=self.f["small"]).pack(anchor="w", padx=(30, 0))

        tk.Label(self.body, text=L("Your key is stored encrypted on this computer and is only ever sent to Anthropic.\n"
                                   "Already signed in to Claude Code yourself? Click “Test connection” above: "
                                   "if it shows ✓, you can skip the key.",
                                   "密钥加密保存在本机，只会发送给 Anthropic。\n"
                                   "已经自己登录了 Claude Code？点击上方“测试连接”，显示 ✓ 就可以跳过密钥。"),
                 bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w", wraplength=540, justify="left").pack(
            fill="x", pady=(14, 0))

    def step(self, number, title, hint):
        row = tk.Frame(self.body, bg=ui.BG)
        row.pack(fill="x", pady=(10, 2))
        tk.Label(row, text=str(number), bg=self.accent, fg="#031018", font=self.f["small"], width=2).pack(
            side="left", padx=(0, 10))
        tk.Label(row, text=title, bg=ui.BG, fg=ui.TEXT, font=self.f["head"], anchor="w").pack(side="left")
        if hint:
            tk.Label(self.body, text=hint, bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w", justify="left",
                     wraplength=510).pack(fill="x", padx=(30, 0), pady=(0, 4))

    def paste_key(self):
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            text = ""
        self.key_entry.delete(0, "end")
        self.key_entry.insert(0, text)
        if text:
            self.check_key()

    def mark_connected(self):
        self.connected = True

    def check_key(self):
        key = self.key_entry.get().strip()
        self.key_status.config(text=L("Checking…", "正在验证……"), fg=ui.DIM)

        def work():
            ok, msg = credentials.check_api_key(key)
            if ok:
                credentials.save_api_key(key)
                self.key_ok = True
            text = ("✓ " + L(msg + " Saved.", "密钥有效，已保存。")) if ok else ("✗ " + msg)

            def show():
                if self.key_status.winfo_exists():
                    self.key_status.config(text=text, fg=ui.GREEN if ok else ui.RED)
                if ok and getattr(self, "claude_card", None) is not None and self.claude_card.winfo_exists():
                    self.claude_card.test()  # prove Claude Code works with the new key
            self.root.after(0, show)
        threading.Thread(target=work, daemon=True).start()

    def page_you(self):
        self.heading(L("About you", "关于你"), L("What should I call you? (Optional.)", "我该怎么称呼你？（选填）"))
        self.name_entry = ui.entry(self.body, self.choices["name"], width=30, f=self.f["body"])
        self.name_entry.pack(anchor="w", ipady=6)
        tk.Label(self.body, text=L("Pick a voice:", "选择声音："), bg=ui.BG, fg=ui.DIM, font=self.f["small"],
                 anchor="w").pack(fill="x", pady=(22, 6))
        voices = ui.VOICES_ZH if i18n.is_zh() else ui.VOICES
        if self.choices["voice"] not in dict(voices):
            self.choices["voice"] = voices[0][0]
        self.voice_var = tk.StringVar(value=self.choices["voice"])
        for code, label in voices:
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
        voice.Speaker(cfg).speak(L(f"Good evening{', ' + name if name else ''}. All systems are online.",
                                   f"晚上好{'，' + name if name else ''}。所有系统已上线。"))

    def page_listen(self):
        import hotkeys
        talk = hotkeys.label(self.cfg.get("talk_key", "f9"))
        self.heading(L("Talking to me", "和我对话"),
                     L(f"Hold {talk} (or click the orb) any time to talk. You can also turn on a wake "
                       "phrase so you can just say it. Listening for it happens entirely on your computer.",
                       f"随时按住 {talk}（或点击光球）说话。也可以开启唤醒词，直接喊出来即可。"
                       "唤醒词检测完全在本机进行。注意：唤醒词是英文的，唤醒之后可以说中文。"))
        self.wake_var = tk.StringVar(value=self.choices["wake"])
        for code, label in ui.WAKE_WORDS:
            if not code:
                label = L(label, "关闭（使用快捷键或点击光球）")
            tk.Radiobutton(self.body, text=label, value=code, variable=self.wake_var, bg=ui.BG, fg=ui.TEXT,
                           selectcolor=ui.CARD, activebackground=ui.BG, activeforeground=ui.TEXT, font=self.f["body"],
                           anchor="w", command=lambda: self.choices.update(wake=self.wake_var.get())).pack(fill="x")
        if sys.platform in ("win32", "darwin"):
            row = tk.Frame(self.body, bg=ui.BG)
            row.pack(fill="x", pady=(24, 0))
            tk.Label(row, text=L(f"Start {APP_NAME} when I log in", f"登录时自动启动 {APP_NAME}"), bg=ui.BG,
                     fg=ui.TEXT, font=self.f["body"]).pack(side="left")
            ui.Switch(row, self.choices["autostart"], lambda v: self.choices.update(autostart=v), self.accent,
                      bg=ui.BG).pack(side="right")

    def page_stats(self):
        self.heading(L("Anonymous usage stats", "匿名使用统计"),
                     L(f"{APP_NAME} is free and made by one developer. To see whether people keep using it and which "
                       "features matter, it sends anonymous usage stats: a random ID, the version, that it was used "
                       "today, and which kinds of features were used (like “timer” or “routine”).\n\n"
                       "It never sends anything you say or type, Claude's replies, files, screenshots or your location.",
                       f"{APP_NAME} 是免费的，由一位开发者制作。为了了解大家是否在持续使用、哪些功能更有用，"
                       "它会发送匿名使用统计：随机编号、版本号、今天是否使用过，以及用了哪类功能（比如“计时器”“例程”）。\n\n"
                       "绝不会发送你说的话或输入的内容、Claude 的回复、文件、截图或你的位置。"))
        row = tk.Frame(self.body, bg=ui.CARD, padx=16, pady=12)
        row.pack(fill="x", pady=(4, 10))
        tk.Label(row, text=L("Share anonymous usage stats", "分享匿名使用统计"), bg=ui.CARD, fg=ui.TEXT,
                 font=self.f["body"]).pack(side="left")
        ui.Switch(row, self.choices["stats"], lambda v: self.choices.update(stats=v), self.accent).pack(side="right")
        ui.FlatButton(self.body, L("Read exactly what's sent (PRIVACY.md)", "查看具体发送内容（PRIVACY.md）"),
                      lambda: ui.open_file(ui.ROOT / "PRIVACY.md"), font=self.f["small"]).pack(anchor="w")
        tk.Label(self.body, text=L("You can change this any time in Settings. Feedback you choose to send is separate.",
                                   "之后可以随时在设置中更改。你主动发送的反馈不受此开关影响。"),
                 bg=ui.BG, fg=ui.DIM, font=self.f["small"], anchor="w").pack(fill="x", pady=(10, 0))

    def page_done(self):
        self.heading(L("All set", "设置完成"), L("Here's how to use me:", "使用方法："))
        wake = dict(ui.WAKE_WORDS).get(self.choices["wake"], "")
        import hotkeys
        key = lambda name, default: hotkeys.label(self.cfg.get(name, default))
        tips = [(key("talk_key", "f9"), L("hold to talk (or click the orb)", "按住说话（或点击光球）"))]
        if self.choices["wake"]:
            tips.insert(0, (wake, L("say it any time, then ask", "随时说出唤醒词，然后提问")))
        tips += [(L("Right-click the orb", "右键点击光球"), L("menu: settings, routines, feedback", "菜单：设置、例程、反馈")),
                 (key("hud_key", "ctrl+shift+j"), L("full-screen HUD", "全屏界面")),
                 (key("show_hide_key", "ctrl+shift+space"), L("hide / show", "隐藏 / 显示")),
                 (L("“in the background, …”", "“在后台帮我……”"), L("run long tasks while you keep working", "后台处理耗时任务")),
                 (L("“when I say X, do Y”", "“当我说X的时候，做Y”"), L("make your own routine", "创建你自己的例程")),
                 (L("“I have a suggestion: …”", "“我有个建议：……”"), L("send feedback to the developer", "向开发者发送反馈"))]
        for k, what in tips:
            row = tk.Frame(self.body, bg=ui.BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=k, bg=ui.BG, fg=self.accent, font=self.f["head"], width=24, anchor="w").pack(side="left")
            tk.Label(row, text=what, bg=ui.BG, fg=ui.TEXT, font=self.f["body"], anchor="w").pack(side="left")
        if not (self.key_ok or self.connected):
            tk.Label(self.body, text=L("Claude isn't connected yet. You can finish this any time in Settings > Claude.",
                                       "Claude 尚未连接。之后可以随时在“设置 > Claude”中完成。"),
                     bg=ui.BG, fg=ui.RED, font=self.f["small"], anchor="w", wraplength=540).pack(fill="x", pady=(16, 0))

    # ---------- save ----------
    def finish(self):
        c = self.choices
        ui.save_config({"user_name": c["name"], "edge_voice": c["voice"], "voice_engine": "edge",
                        "language": i18n.LANG, "wake_word": c["wake"], "share_usage_stats": bool(c["stats"]),
                        "setup_done": True})
        if sys.platform in ("win32", "darwin"):
            try:
                autostart.set_enabled(c["autostart"])
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SetupWizard().run()
