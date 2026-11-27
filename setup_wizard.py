"""First-run setup: language, connecting Claude, your name and voice, talking, usage stats.
Runs automatically the first time Wisp starts (or any time: py setup_wizard.py)."""
import sys
import threading
import tkinter as tk

import autostart
import claude_setup
import credentials
import holo
import i18n
import ui_kit as ui
from app_info import APP_NAME, VERSION
from i18n import L

KEYS_URL = "https://console.anthropic.com/settings/keys"
LIMITS_URL = "https://console.anthropic.com/settings/limits"

LINE = holo.LINE
CARD_HI = holo.PANEL_HI
DARK_TEXT = holo.ON_ACCENT
W = 720  # window width


class SetupWizard:
    def __init__(self, root=None):
        i18n.load_language()
        self.cfg = ui.load_config()
        self.accent = self.cfg.get("accent_colour", "#38d6ff")
        self.root = root or tk.Tk()
        r = self.root
        r.title(f"{APP_NAME} setup")
        r.configure(bg=ui.BG)
        r.geometry(f"{W}x700")
        r.resizable(False, False)
        holo.dark_titlebar(r)
        self.f = ui.fonts(r)
        self.choices = {
            "name": self.cfg.get("user_name", ""),
            "voice": self.cfg.get("edge_voice", "en-GB-RyanNeural"),
            "wake": self.cfg.get("wake_word", "hey_jarvis"),
            "autostart": autostart.is_enabled() if sys.platform in ("win32", "darwin") else False,
            "stats": self.cfg.get("share_usage_stats", True),
            "personality": self.cfg.get("personality", "butler"),
        }
        self.key_ok = credentials.has_api_key()
        self.connected = False
        self.connect_way = "key"
        self.pages = [
            (self.page_language, ("Language", "语言")),
            (self.page_welcome, ("Welcome", "欢迎")),
            (self.page_connect, ("Connect Claude", "连接 Claude")),
            (self.page_you, ("You", "关于你")),
            (self.page_listen, ("Talking", "对话")),
            (self.page_stats, ("Privacy", "隐私")),
            (self.page_done, ("Done", "完成")),
        ]
        self.index = 0
        # bring the window to the front (on a Mac it can otherwise open behind other windows)
        r.lift()
        r.attributes("-topmost", True)
        r.after(800, lambda: r.attributes("-topmost", False))
        r.after(100, r.focus_force)

        # top: title strip + segmented progress
        self.top = tk.Canvas(r, width=W, height=92, bg=ui.BG, highlightthickness=0)
        self.top.pack(fill="x")

        # bottom: version on the left, Back / Next on the right
        nav = tk.Frame(r, bg=ui.BG)
        nav.pack(fill="x", side="bottom", padx=40, pady=(14, 18))
        line = tk.Canvas(r, height=2, bg=ui.BG, highlightthickness=0)
        line.pack(fill="x", side="bottom", padx=40)
        line.create_line(0, 1, 4000, 1, fill=LINE)
        line.create_line(0, 1, 60, 1, fill=holo.mix(ui.BG, self.accent, 0.6), width=2)
        tk.Label(nav, text=f"WISP  v{VERSION}", bg=ui.BG, fg=holo.MUTED, font=self.f["label"]).pack(side="left")
        self.next_btn = holo.Button(nav, "Next", self.next, kind="primary", font=self.f["head"], accent=self.accent,
                                    padx=22, pady=9)
        self.next_btn.pack(side="right")
        self.back_btn = holo.Button(nav, "Back", self.back, kind="ghost", font=self.f["body"], accent=self.accent,
                                    padx=16, pady=8)
        self.back_btn.pack(side="right", padx=10)

        # middle: the page
        self.body = tk.Frame(r, bg=ui.BG)
        self.body.pack(fill="both", expand=True, padx=40, pady=(18, 0))

        self.show()

    # ---------- navigation ----------
    def _draw_top(self):
        c, a = self.top, self.accent
        c.delete("all")
        holo.grid_texture(c, W, 92, holo.mix(ui.BG, a, 0.04), step=16)
        total, i = len(self.pages), self.index
        c.create_text(40, 26, text="◢ WISP  //  " + L("SETUP", "设置"), anchor="w", font=self.f["label"],
                      fill=a)
        c.create_text(W - 40, 26, text=L(f"STEP {i + 1:02d} / {total:02d}", f"第 {i + 1} / {total} 步"),
                      anchor="e", font=self.f["label"], fill=ui.DIM)
        # segmented progress: done = filled, current = glowing outline, later = faint
        x0, x1, y, h, gap = 40, W - 40, 44, 8, 6
        seg = (x1 - x0 - gap * (total - 1)) / total
        for k in range(total):
            sx = x0 + k * (seg + gap)
            pts = holo.chamfer(sx, y, sx + seg, y + h, 3, "tl br")
            if k < i:
                c.create_polygon(pts, fill=holo.mix(ui.BG, a, 0.7), outline="")
            elif k == i:
                c.create_polygon(pts, fill=holo.mix(ui.BG, a, 0.25), outline=a)
            else:
                c.create_polygon(pts, fill=holo.PANEL, outline=LINE)
        name = self.pages[i][1]
        sx = x0 + i * (seg + gap)
        c.create_text(sx, y + 24, text=holo.spaced(L(name[0], name[1])), anchor="w", font=self.f["label"],
                      fill=holo.mix(ui.BG, a, 0.85))
        c.create_line(0, 91, W, 91, fill=holo.LINE_SOFT)

    def show(self):
        for w in self.body.winfo_children():
            w.destroy()
        page, name = self.pages[self.index]
        page()
        self._draw_top()
        self.back_btn.set_enabled(self.index > 0)
        last = self.index == len(self.pages) - 1
        self.next_btn.config(text=L("Start Wisp  ▸", "启动 Wisp  ▸") if last else L("Next  ▸", "下一步  ▸"))
        self.back_btn.config(text=L("Back", "上一步"))

    def _save_name(self):
        if self.pages[self.index][0] == self.page_you and hasattr(self, "name_entry"):
            self.choices["name"] = self.name_entry.get().strip()

    def next(self):
        if self.index == len(self.pages) - 1:
            self.finish()
            return
        self._save_name()
        self.index += 1
        self.show()

    def back(self):
        if self.index > 0:
            self._save_name()
            self.index -= 1
            self.show()

    # ---------- building blocks ----------
    def heading(self, title, text=None):
        tk.Label(self.body, text=title, bg=ui.BG, fg=ui.TEXT, font=self.f["title"], anchor="w").pack(fill="x")
        if text:
            tk.Label(self.body, text=text, bg=ui.BG, fg=ui.DIM, font=self.f["body"], justify="left", anchor="w",
                     wraplength=630).pack(fill="x", pady=(4, 16))

    def note(self, parent, text, colour=None, bg=ui.BG, pady=(12, 0)):
        label = tk.Label(parent, text=text, bg=bg, fg=colour or ui.DIM, font=self.f["small"], justify="left",
                         anchor="w", wraplength=610)
        label.pack(fill="x", pady=pady)
        return label

    def choice(self, parent, title, subtitle, selected, command, side=None):
        """A clickable card: ◆ when chosen (glowing border), ◇ when not. Used for languages, options,
        voices and wake phrases."""
        bg = CARD_HI if selected else holo.PANEL
        card = holo.Card(parent, accent=self.accent, padx=14, pady=10, bg=bg, selected=selected, cursor="hand2")
        top = tk.Frame(card, bg=bg, cursor="hand2")
        top.pack(fill="x")
        mark = tk.Label(top, text="◆" if selected else "◇", bg=bg, fg=self.accent if selected else holo.MUTED,
                        font=self.f["body"], cursor="hand2")
        mark.pack(side="left", padx=(0, 10))
        head = tk.Label(top, text=title, bg=bg, fg=ui.TEXT if selected else holo.mix(ui.TEXT, ui.BG, 0.15),
                        font=self.f["head"], anchor="w", cursor="hand2")
        head.pack(side="left")
        widgets = [card, top, mark, head]
        if subtitle:
            sub = tk.Label(card, text=subtitle, bg=bg, fg=ui.DIM, font=self.f["small"], anchor="w",
                           justify="left", cursor="hand2")
            sub.pack(fill="x", padx=(24, 0), pady=(2, 0))
            widgets.append(sub)
        for w in widgets:
            w.bind("<ButtonRelease-1>", lambda e: command())
        if side:
            card.pack(side=side, fill="both", expand=True, padx=(0, 10) if side == "left" else 0)
        else:
            card.pack(fill="x", pady=4)
        return top

    def numbered(self, parent, number, title, hint=None, bg=holo.PANEL):
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=(10, 2))
        badge = tk.Canvas(row, width=30, height=20, bg=bg, highlightthickness=0)
        badge.create_polygon(holo.chamfer(0.5, 0.5, 29, 19, 4), fill=holo.mix(bg, self.accent, 0.18),
                             outline=self.accent)
        badge.create_text(15, 10, text=f"{number:02d}", font=self.f["label"], fill=self.accent)
        badge.pack(side="left", padx=(0, 10))
        tk.Label(row, text=title, bg=bg, fg=ui.TEXT, font=self.f["head"], anchor="w").pack(side="left")
        if hint:
            tk.Label(parent, text=hint, bg=bg, fg=ui.DIM, font=self.f["small"], anchor="w", justify="left",
                     wraplength=560).pack(fill="x", padx=(40, 0), pady=(0, 6))

    def button(self, parent, text, command, primary=False):
        return holo.Button(parent, text, command, kind="primary" if primary else "ghost", font=self.f["small"],
                           accent=self.accent)

    def switch_row(self, label, value, on_change):
        row = holo.Card(self.body, accent=self.accent, padx=16, pady=10)
        row.pack(fill="x", pady=(12, 0))
        tk.Label(row, text=label, bg=holo.PANEL, fg=ui.TEXT, font=self.f["body"]).pack(side="left")
        holo.Switch(row, value, on_change, self.accent).pack(side="right")

    # ---------- 1. language ----------
    def page_language(self):
        # English until someone picks 中文 - then this page (and everything after) switches to Chinese.
        self.heading(L("Choose your language", "选择语言"),
                     L("This is the language you'll speak to Wisp in. You can change it later in Settings.",
                       "这是你和 Wisp 对话时使用的语言。之后可以在设置中更改。"))
        for code, label in i18n.LANGUAGES.items():
            self.choice(self.body, label, None, i18n.LANG == code, lambda c=code: self.pick_language(c))
        self.note(self.body, L("Wake phrases (“Hey Jarvis”) are English-only for now; holding the talk key works "
                               "in any language.",
                               "唤醒词（“Hey Jarvis”）目前只有英文；按住说话键可以使用任何语言。"), pady=(18, 0))

    def pick_language(self, code):
        i18n.apply_language(code, ui.save_config)
        self.cfg = ui.load_config()
        self.choices["voice"] = self.cfg.get("edge_voice", self.choices["voice"])
        self.show()

    # ---------- 2. welcome ----------
    def page_welcome(self):
        self.heading(L(f"Welcome to {APP_NAME}", f"欢迎使用 {APP_NAME}"),
                     L("A voice assistant that uses your computer for you. Setup takes about two minutes.",
                       "一个能替你操作电脑的语音助手。设置大约需要两分钟。"))
        things = [(L("Research the web properly", "认真搜索网络"), L("and read the pages, not just links",
                                                                 "并阅读网页内容，而不只是给链接")),
                  (L("Open and control apps", "打开和控制应用"), L("clicks and types for you", "替你点击和输入")),
                  (L("Work in the background", "在后台工作"), L("long tasks while you keep going",
                                                             "你继续工作时处理耗时任务")),
                  (L("Timers, reminders, routines", "计时器、提醒、例程"), L("set up just by talking", "说一句就能设置"))]
        grid = tk.Frame(self.body, bg=ui.BG)
        grid.pack(fill="x")
        for i, (title, text) in enumerate(things):
            cell = holo.Card(grid, accent=self.accent, padx=14, pady=12)
            cell.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 10) if i % 2 == 0 else 0, pady=5)
            tk.Label(cell, text=title, bg=ui.CARD, fg=ui.TEXT, font=self.f["head"], anchor="w").pack(fill="x")
            tk.Label(cell, text=text, bg=ui.CARD, fg=ui.DIM, font=self.f["small"], anchor="w").pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="c")
        grid.columnconfigure(1, weight=1, uniform="c")
        self.note(self.body, L(f"Version {VERSION}  ·  free and open source (MIT licence)",
                               f"版本 {VERSION}  ·  免费开源（MIT 许可）"), pady=(22, 0))

    # ---------- 3. connect Claude ----------
    def page_connect(self):
        self.heading(L("Connect Claude", "连接 Claude"),
                     L(f"{APP_NAME}'s brain is Claude, made by Anthropic. Pick one way to connect it:",
                       f"{APP_NAME} 的大脑是 Anthropic 公司的 Claude。选择一种连接方式："))
        cards = tk.Frame(self.body, bg=ui.BG)
        cards.pack(fill="x")
        self.choice(cards, L("Option 1:  API key", "方式一：API 密钥"),
                    L("Quickest. Copy one key into Wisp.", "最快。把一个密钥复制到 Wisp。"),
                    self.connect_way == "key", lambda: self.pick_way("key"), side="left")
        self.choice(cards, L("Option 2:  Claude Code sign-in", "方式二：登录 Claude Code"),
                    L("No key to copy. Sign in in your browser.", "无需复制密钥，在浏览器中登录。"),
                    self.connect_way == "signin", lambda: self.pick_way("signin"), side="right")

        panel = holo.Card(self.body, accent=self.accent, padx=18, pady=8)
        panel.pack(fill="x", pady=(12, 0))
        if self.connect_way == "key":
            self.connect_with_key(panel)
        else:
            self.connect_with_signin(panel)

        self.claude_card = claude_setup.status_card(self.body, self.f, self.accent, credentials.load_api_key,
                                                    on_ready=self.mark_connected)
        self.claude_card.pack(fill="x", pady=(12, 0))
        self.note(self.body, L("Both options are pay-as-you-go through your Anthropic account: most requests cost "
                               "about a cent. Set a monthly limit so there are no surprises.",
                               "两种方式都通过你的 Anthropic 账户按用量付费：大多数请求约一美分。"
                               "建议设置每月上限。"), pady=(10, 0))

    def pick_way(self, way):
        self.connect_way = way
        self.show()

    def connect_with_key(self, panel):
        self.numbered(panel, 1, L("Get a key", "获取密钥"),
                      L("Sign in, add a few dollars of credit under Billing, then click “Create Key” and copy it.",
                        "登录后在“Billing”里充值几美元，然后点击“Create Key”并复制。"))
        row = tk.Frame(panel, bg=ui.CARD)
        row.pack(fill="x", padx=(30, 0))
        self.button(row, L("Open Anthropic Console  ↗", "打开 Anthropic 控制台  ↗"),
                    lambda: ui.open_url(KEYS_URL)).pack(side="left")
        self.button(row, L("Set a monthly limit  ↗", "设置每月上限  ↗"),
                    lambda: ui.open_url(LIMITS_URL)).pack(side="left", padx=6)

        self.numbered(panel, 2, L("Paste it here", "粘贴到这里"))
        row = tk.Frame(panel, bg=ui.CARD)
        row.pack(fill="x", padx=(30, 0))
        self.key_entry = ui.entry(row, "", show="•", width=30, f=self.f["body"])
        self.key_entry.pack(side="left", ipady=5)
        self.key_entry.bind("<Return>", lambda e: self.check_key())
        self.button(row, L("Paste", "粘贴"), self.paste_key).pack(side="left", padx=(6, 0))
        self.button(row, L("Check & save", "验证并保存"), self.check_key, primary=True).pack(side="left", padx=6)
        self.key_status = self.note(panel, "", bg=ui.CARD, pady=(6, 4))
        self.key_status.pack_configure(padx=(30, 0))
        if self.key_ok:
            self.key_status.config(text=L(f"✓ A key is already saved ({credentials.masked()}).",
                                          f"✓ 已保存密钥（{credentials.masked()}）。"), fg=ui.GREEN)

    def connect_with_signin(self, panel):
        self.numbered(panel, 1, L("Open Claude Code", "打开 Claude Code"),
                      L("A window opens. Choose “Anthropic Console account”, then sign in in your browser. "
                        "When it says you're signed in, close that window.",
                        "会打开一个窗口。选择“Anthropic Console account”，然后在浏览器中登录。"
                        "显示登录成功后关闭那个窗口。"))
        row = tk.Frame(panel, bg=ui.CARD)
        row.pack(fill="x", padx=(30, 0))
        self.button(row, L("Open Claude Code sign-in", "打开 Claude Code 登录"), self.open_sign_in,
                    primary=True).pack(side="left")
        self.signin_status = self.note(panel, "", bg=ui.CARD, pady=(4, 0))
        self.signin_status.pack_configure(padx=(30, 0))

        self.numbered(panel, 2, L("Test it", "测试"),
                      L("Come back here and click “Test connection” below. A ✓ means you're done.",
                        "回到这里，点击下方的“测试连接”。显示 ✓ 就完成了。"))
        if self.key_ok:
            row = tk.Frame(panel, bg=ui.CARD)
            row.pack(fill="x", padx=(30, 0), pady=(2, 6))
            tk.Label(row, text=L("A saved API key would be used instead of your sign-in.",
                                 "已保存的 API 密钥会优先于登录使用。"),
                     bg=ui.CARD, fg=ui.RED, font=self.f["small"]).pack(side="left")
            self.button(row, L("Remove saved key", "删除已保存的密钥"), self.remove_key).pack(side="left", padx=8)

    def open_sign_in(self):
        ok, msg = claude_setup.open_sign_in()
        if not ok:
            self.signin_status.config(text="✗ " + (L("Install Claude Code first (button below).",
                                                     "请先安装 Claude Code（下方按钮）。")
                                                   if "Install" in msg else msg), fg=ui.RED)

    def remove_key(self):
        credentials.save_api_key("")
        self.key_ok = False
        self.show()

    def mark_connected(self):
        self.connected = True

    def paste_key(self):
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            text = ""
        self.key_entry.delete(0, "end")
        self.key_entry.insert(0, text)
        if text:
            self.check_key()

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
                if ok and self.claude_card.winfo_exists():
                    self.claude_card.test()  # prove Claude Code works with the new key
            self.root.after(0, show)
        threading.Thread(target=work, daemon=True).start()

    # ---------- 4. you ----------
    def page_you(self):
        self.heading(L("About you", "关于你"), L("What should I call you, and how should I sound?",
                                                 "我该怎么称呼你？想要什么样的声音？"))
        tk.Label(self.body, text=L("Your name (optional)", "你的名字（选填）"), bg=ui.BG, fg=ui.DIM,
                 font=self.f["small"], anchor="w").pack(fill="x")
        self.name_entry = ui.entry(self.body, self.choices["name"], width=32, f=self.f["body"])
        self.name_entry.pack(anchor="w", ipady=6, pady=(4, 14))
        tk.Label(self.body, text=L("Personality", "性格"), bg=ui.BG, fg=ui.DIM, font=self.f["small"],
                 anchor="w").pack(fill="x", pady=(0, 2))
        cards = tk.Frame(self.body, bg=ui.BG)
        cards.pack(fill="x", pady=(0, 14))
        for side, (code, title, sub) in zip(("left", "right"), (
                ("butler", L("Composed butler", "沉稳管家"), L("Calm, polite, dry wit", "冷静、礼貌、含蓄幽默")),
                ("friendly", L("Friendly", "亲切"), L("Casual and relaxed", "随和、轻松")))):
            self.choice(cards, title, sub, self.choices["personality"] == code,
                        lambda c=code: self.pick_personality(c), side=side)
        tk.Label(self.body, text=L("Voice  (▶ to hear it)", "声音（点 ▶ 试听）"), bg=ui.BG, fg=ui.DIM,
                 font=self.f["small"], anchor="w").pack(fill="x", pady=(0, 2))
        voices = ui.VOICES_ZH if i18n.is_zh() else ui.VOICES
        if self.choices["voice"] not in dict(voices):
            self.choices["voice"] = voices[0][0]
        grid = tk.Frame(self.body, bg=ui.BG)
        grid.pack(fill="x")
        for i, (code, label) in enumerate(voices):
            selected = self.choices["voice"] == code
            bg = CARD_HI if selected else ui.CARD
            cell = holo.Card(grid, accent=self.accent, padx=0, pady=0, bg=bg, selected=selected, cursor="hand2")
            cell.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 8) if i % 2 == 0 else 0, pady=3)
            mark = tk.Label(cell, text=("◆  " if selected else "◇  ") + label, bg=bg, anchor="w",
                            fg=ui.TEXT if selected else ui.DIM, font=self.f["body"], cursor="hand2")
            mark.pack(side="left", fill="x", expand=True, padx=10, pady=7)
            for w in (cell, mark):
                w.bind("<ButtonRelease-1>", lambda e, c=code: self.pick_voice(c))
            holo.Button(cell, "▶", lambda c=code: self.preview(c), font=self.f["small"], accent=self.accent,
                        padx=9, pady=3).pack(side="right", padx=6)
        grid.columnconfigure(0, weight=1, uniform="v")
        grid.columnconfigure(1, weight=1, uniform="v")

    def pick_personality(self, code):
        self._save_name()
        self.choices["personality"] = code
        self.show()

    def pick_voice(self, code):
        self._save_name()
        self.choices["voice"] = code
        self.show()

    def preview(self, voice_code):
        import voice
        cfg = dict(self.cfg, voice_engine="edge", edge_voice=voice_code)
        name = self.name_entry.get().strip() if hasattr(self, "name_entry") else ""
        threading.Thread(target=lambda: voice.Speaker(cfg).speak(
            L(f"Good evening{', ' + name if name else ''}. All systems are online.",
              f"晚上好{'，' + name if name else ''}。所有系统已上线。")), daemon=True).start()

    # ---------- 5. talking ----------
    def page_listen(self):
        import hotkeys
        talk = hotkeys.label(self.cfg.get("talk_key", "f9"))
        self.heading(L("Talking to me", "和我对话"),
                     L(f"Hold {talk} or click the orb any time. A wake phrase lets you just say it; "
                       "listening for it happens entirely on your computer.",
                       f"随时按住 {talk} 或点击光球。开启唤醒词后直接喊出来即可，检测完全在本机进行。"
                       "唤醒词是英文的，唤醒之后可以说中文。"))
        for code, label in ui.WAKE_WORDS:
            if not code:
                label = L(label, "关闭（使用快捷键或点击光球）")
            self.choice(self.body, label, None, self.choices["wake"] == code, lambda c=code: self.pick_wake(c))
        if sys.platform in ("win32", "darwin"):
            self.switch_row(L(f"Start {APP_NAME} when I log in", f"登录时自动启动 {APP_NAME}"),
                            self.choices["autostart"], lambda v: self.choices.update(autostart=v))
        if sys.platform == "darwin":
            self.mac_permissions()

    def mac_permissions(self):
        """macOS asks for these the first time Wisp needs them. If a prompt was missed or refused, fix it here."""
        card = holo.Card(self.body, accent=self.accent, padx=16, pady=10)
        card.pack(fill="x", pady=(14, 0))
        tk.Label(card, text=L("Mac permissions", "Mac 权限"), bg=ui.CARD, fg=ui.TEXT, font=self.f["head"],
                 anchor="w").pack(fill="x")
        tk.Label(card, text=L("macOS asks for these when Wisp first needs them. Missed one, or clicked "
                              "“Don't Allow”? Open it here and switch Wisp on.",
                              "macOS 会在 Wisp 第一次需要时询问。如果错过了或点了“不允许”，在这里打开并为 Wisp 开启。"),
                 bg=ui.CARD, fg=ui.DIM, font=self.f["small"], anchor="w", justify="left", wraplength=540).pack(
            fill="x", pady=(2, 8))
        row = tk.Frame(card, bg=ui.CARD)
        row.pack(fill="x")
        base = "x-apple.systempreferences:com.apple.preference.security?Privacy_"
        for label, pane in ((L("Microphone", "麦克风"), "Microphone"), (L("Accessibility", "辅助功能"), "Accessibility"),
                            (L("Input Monitoring", "输入监控"), "ListenEvent"), (L("Automation", "自动化"), "Automation")):
            self.button(row, label + "  ↗", lambda p=pane: ui.open_file(base + p)).pack(side="left", padx=(0, 6))

    def pick_wake(self, code):
        self.choices["wake"] = code
        self.show()

    # ---------- 6. privacy ----------
    def page_stats(self):
        self.heading(L("Anonymous usage stats", "匿名使用统计"),
                     L(f"{APP_NAME} is free and made by one developer. Anonymous stats show whether people keep "
                       "using it and which features matter.",
                       f"{APP_NAME} 是免费的，由一位开发者制作。匿名统计可以了解大家是否在持续使用、哪些功能更有用。"))
        cols = tk.Frame(self.body, bg=ui.BG)
        cols.pack(fill="x")
        for i, (title, items, colour) in enumerate([
                (L("Sent", "会发送"), L("A random ID\nThe version\nThat it was used today\nWhich kinds of features "
                                         "(like “timer”)", "随机编号\n版本号\n今天是否使用过\n用了哪类功能（比如“计时器”）"),
                 ui.GREEN),
                (L("Never sent", "绝不发送"), L("Anything you say or type\nClaude's replies\nFiles or screenshots\n"
                                                "Your location", "你说的话或输入的内容\nClaude 的回复\n文件或截图\n你的位置"),
                 ui.RED)]):
            cell = holo.Card(cols, accent=self.accent, padx=14, pady=12)
            cell.grid(row=0, column=i, sticky="nsew", padx=(0, 10) if i == 0 else 0)
            tk.Label(cell, text=title, bg=ui.CARD, fg=colour, font=self.f["head"], anchor="w").pack(fill="x")
            tk.Label(cell, text=items, bg=ui.CARD, fg=ui.TEXT, font=self.f["small"], anchor="w",
                     justify="left").pack(fill="x", pady=(4, 0))
        cols.columnconfigure(0, weight=1, uniform="s")
        cols.columnconfigure(1, weight=1, uniform="s")
        self.switch_row(L("Share anonymous usage stats", "分享匿名使用统计"), self.choices["stats"],
                        lambda v: self.choices.update(stats=v))
        row = tk.Frame(self.body, bg=ui.BG)
        row.pack(fill="x", pady=(12, 0))
        self.button(row, L("Read exactly what's sent (PRIVACY.md)", "查看具体发送内容（PRIVACY.md）"),
                    lambda: ui.open_file(ui.ROOT / "PRIVACY.md")).pack(side="left")
        self.note(self.body, L("You can change this any time in Settings. Feedback you choose to send is separate.",
                               "之后可以随时在设置中更改。你主动发送的反馈不受此开关影响。"), pady=(10, 0))

    # ---------- 7. done ----------
    def page_done(self):
        self.heading(L("You're all set", "设置完成"), L("Here's how to use me:", "使用方法："))
        import hotkeys
        key = lambda name, default: hotkeys.label(self.cfg.get(name, default))
        tips = [(key("talk_key", "f9"), L("hold to talk (or click the orb)", "按住说话（或点击光球）"))]
        if self.choices["wake"]:
            tips.insert(0, (dict(ui.WAKE_WORDS).get(self.choices["wake"], ""),
                            L("say it any time, then ask", "随时说出唤醒词，然后提问")))
        tips += [(L("Right-click the orb", "右键点击光球"), L("settings, routines, feedback", "设置、例程、反馈")),
                 (key("hud_key", "ctrl+shift+j"), L("full-screen HUD", "全屏界面")),
                 (key("show_hide_key", "ctrl+shift+space"), L("hide / show", "隐藏 / 显示")),
                 (L("“in the background, …”", "“在后台帮我……”"), L("long tasks while you work", "后台处理耗时任务")),
                 (L("“when I say X, do Y”", "“当我说X的时候，做Y”"), L("make your own routine", "创建你自己的例程"))]
        card = holo.Card(self.body, accent=self.accent, padx=16, pady=10)
        card.pack(fill="x")
        for k, what in tips:
            row = tk.Frame(card, bg=ui.CARD)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=k, bg=ui.CARD, fg=self.accent, font=self.f["head"], width=24, anchor="w").pack(
                side="left")
            tk.Label(row, text=what, bg=ui.CARD, fg=ui.TEXT, font=self.f["body"], anchor="w").pack(side="left")
        if not (self.key_ok or self.connected):
            self.note(self.body, L("Claude isn't connected yet (or wasn't tested). You can finish this any time "
                                   "in Settings > Claude.",
                                   "Claude 尚未连接（或未测试）。之后可以随时在“设置 > Claude”中完成。"),
                      colour=ui.RED, pady=(14, 0))

    # ---------- save ----------
    def finish(self):
        c = self.choices
        ui.save_config({"user_name": c["name"], "edge_voice": c["voice"], "voice_engine": "edge",
                        "personality": c["personality"],
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
