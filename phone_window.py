"""The Phone window (right-click the orb > Phone): pair your phone with a QR code, use it away from home,
get notifications on it, and let Wisp control an Android phone."""
import threading
import tkinter as tk

import holo
import remote
import ui_kit as ui
from app_info import APP_NAME
from i18n import L


def draw_qr(canvas, text, size, accent):
    """Draw a QR code for text on a canvas (dark squares on white, so every phone camera reads it)."""
    canvas.delete("all")
    try:
        import qrcode
        qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(text)
        qr.make(fit=True)
        matrix = qr.get_matrix()
    except Exception as exc:
        canvas.create_text(size / 2, size / 2, text=L(f"QR code unavailable\n({exc})", f"无法显示二维码\n（{exc}）"),
                           fill=holo.DIM, width=size - 20, justify="center")
        return False
    n = len(matrix)
    cell = size / n
    canvas.create_rectangle(0, 0, size, size, fill="#ffffff", outline="")
    for y, row in enumerate(matrix):
        x = 0
        while x < n:   # draw runs of dark squares as one rectangle (much faster)
            if row[x]:
                start = x
                while x < n and row[x]:
                    x += 1
                canvas.create_rectangle(start * cell, y * cell, x * cell, (y + 1) * cell, fill="#04080c", outline="")
            else:
                x += 1
    return True


class PhoneWindow:
    W, H = 760, 640

    def __init__(self, app):
        self.app = app
        self.remote = app.remote
        self.accent = app.accent
        self.cfg = app.cfg
        remote.set_enabled(True)
        self.remote.start()
        self.win = win = tk.Toplevel(app.root, bg=holo.BG)
        win.title(L(f"{APP_NAME} - phone", f"{APP_NAME} - 手机"))
        win.geometry(f"{self.W}x{self.H}")
        win.minsize(700, 560)
        holo.dark_titlebar(win)
        self.f = ui.fonts(win)
        holo.Header(win, L("Your phone", "你的手机"), L("WISP // PHONE", "WISP // 手机"), self.accent, self.f,
                    width=self.W, height=74).pack(fill="x")
        body = tk.Frame(win, bg=holo.BG)
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # left: the QR code
        left = holo.Card(body, accent=self.accent, padx=18, pady=16)
        left.pack(side="left", fill="y")
        tk.Label(left, text=L("PAIR A PHONE", "配对手机"), bg=holo.PANEL, fg=self.accent, font=self.f["label"]).pack(anchor="w")
        tk.Label(left, text=L("Scan with your phone's camera", "用手机相机扫描"), bg=holo.PANEL, fg=holo.TEXT,
                 font=self.f["head"]).pack(anchor="w", pady=(4, 10))
        self.qr = tk.Canvas(left, width=230, height=230, bg="#ffffff", highlightthickness=0)
        self.qr.pack()
        self.qr_note = tk.Label(left, bg=holo.PANEL, fg=holo.DIM, font=self.f["small"], justify="left",
                                wraplength=230, anchor="w")
        self.qr_note.pack(fill="x", pady=(10, 0))
        self.devices = tk.Label(left, bg=holo.PANEL, fg=holo.DIM, font=self.f["small"], anchor="w")
        self.devices.pack(fill="x", pady=(8, 0))
        holo.Button(left, L("Forget all phones", "忘记所有手机"), self.forget, font=self.f["small"],
                    accent=self.accent).pack(anchor="w", pady=(8, 0))

        # right: options
        right = tk.Frame(body, bg=holo.BG)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        settings = remote.settings()
        self.away_status = self._switch_row(
            right, L("Use away from home", "在外面也能用"),
            L("A secure link through Cloudflare - no router setup. Your phone finds the PC by itself.",
              "通过 Cloudflare 的安全连接，无需设置路由器。手机会自动找到电脑。"),
            settings.get("away", False), self.set_away)
        self._switch_row(right, L("Phone can see & control the screen", "手机可以查看和控制屏幕"),
                         L("Live view of this computer; tap to click, type and scroll.",
                           "实时查看这台电脑，点按即可点击、输入和滚动。"),
                         self.cfg.get("phone_screen", True), self.set_screen)

        card = holo.Card(right, accent=self.accent, padx=16, pady=12)
        card.pack(fill="x", pady=(10, 0))
        tk.Label(card, text=L("Notifications on your phone", "手机通知"), bg=holo.PANEL, fg=holo.TEXT,
                 font=self.f["body"], anchor="w").pack(fill="x")
        topic = settings["notify_topic"]
        tk.Label(card, text=L("iPhone or Android: install the free “ntfy” app, tap +, and subscribe to:",
                              "iPhone 或安卓：安装免费的“ntfy”应用，点 +，订阅："),
                 bg=holo.PANEL, fg=holo.DIM, font=self.f["small"], anchor="w", justify="left",
                 wraplength=400).pack(fill="x", pady=(2, 4))
        row = tk.Frame(card, bg=holo.PANEL)
        row.pack(fill="x")
        tk.Label(row, text=topic, bg=holo.PANEL_HI, fg=self.accent, font=self.f["mono"], padx=8, pady=4).pack(side="left")
        holo.Button(row, L("Copy", "复制"), lambda: self._copy(topic), font=self.f["small"],
                    accent=self.accent).pack(side="left", padx=6)
        holo.Button(row, L("Send a test", "发送测试"), self.test_notify, font=self.f["small"],
                    accent=self.accent).pack(side="left")
        self.notify_status = tk.Label(card, bg=holo.PANEL, fg=holo.DIM, font=self.f["small"], anchor="w")
        self.notify_status.pack(fill="x", pady=(4, 0))

        card = holo.Card(right, accent=self.accent, padx=16, pady=12)
        card.pack(fill="x", pady=(10, 0))
        top = tk.Frame(card, bg=holo.PANEL)
        top.pack(fill="x")
        tk.Label(top, text=L("Let Wisp control my Android phone", "让 Wisp 控制我的安卓手机"), bg=holo.PANEL,
                 fg=holo.TEXT, font=self.f["body"]).pack(side="left")
        holo.Button(top, L("Set up…", "设置……"), lambda: AndroidSetup(app, self.f), font=self.f["small"],
                    accent=self.accent).pack(side="right")
        tk.Label(card, text=L("Open apps, tap, type and read the screen - by asking Wisp. (iPhones don't allow "
                              "this; Wisp can send them notifications and links instead.)",
                              "打开应用、点按、输入、读取屏幕——只要告诉 Wisp。（iPhone 不允许这样做；"
                              "Wisp 可以给 iPhone 发送通知和链接。）"),
                 bg=holo.PANEL, fg=holo.DIM, font=self.f["small"], anchor="w", justify="left",
                 wraplength=400).pack(fill="x", pady=(4, 0))

        bottom = tk.Frame(win, bg=holo.BG)
        bottom.pack(fill="x", side="bottom", padx=24, pady=(0, 16))
        holo.Button(bottom, L("Done", "完成"), win.destroy, kind="primary", font=self.f["head"], accent=self.accent,
                    padx=22, pady=8).pack(side="right")
        holo.Button(bottom, L("Turn off phone remote", "关闭手机遥控"), self.turn_off, font=self.f["small"],
                    accent=self.accent).pack(side="right", padx=10)

        self._last_link = None
        self._qr_made = 0
        self.refresh()

    # ---------- pieces ----------
    def _switch_row(self, parent, title, hint, value, command):
        card = holo.Card(parent, accent=self.accent, padx=16, pady=12)
        card.pack(fill="x", pady=(0, 10))
        top = tk.Frame(card, bg=holo.PANEL)
        top.pack(fill="x")
        tk.Label(top, text=title, bg=holo.PANEL, fg=holo.TEXT, font=self.f["body"]).pack(side="left")
        holo.Switch(top, value, command, self.accent).pack(side="right")
        status = tk.Label(card, text=hint, bg=holo.PANEL, fg=holo.DIM, font=self.f["small"], anchor="w",
                          justify="left", wraplength=400)
        status.pack(fill="x", pady=(4, 0))
        return status

    def _copy(self, text):
        self.win.clipboard_clear()
        self.win.clipboard_append(text)

    # ---------- actions ----------
    def set_away(self, on):
        remote.set_option("away", bool(on))
        if on:
            self.remote.start_away()
        else:
            self.remote.stop_away()
        self._qr_made = 0
        self.refresh(once=True)

    def set_screen(self, on):
        self.cfg["phone_screen"] = bool(on)
        ui.save_config({"phone_screen": bool(on)})

    def test_notify(self):
        self.notify_status.config(text=L("Sending…", "正在发送……"), fg=holo.DIM)

        def work():
            try:
                import phone
                phone.notify(L("Wisp can reach your phone.", "Wisp 已经可以联系你的手机。"), "Wisp")
                msg, colour = L("✓ Sent. Didn't arrive? Check you subscribed to the name above.",
                                "✓ 已发送。没收到？请确认订阅了上面的名称。"), holo.GREEN
            except Exception as exc:
                msg, colour = f"✗ {exc}", holo.RED
            self.win.after(0, lambda: self.notify_status.winfo_exists() and self.notify_status.config(text=msg, fg=colour))
        threading.Thread(target=work, daemon=True).start()

    def forget(self):
        remote.forget_all()
        self.refresh(once=True)

    def turn_off(self):
        remote.set_enabled(False)
        self.remote.stop()
        self.win.destroy()

    def refresh(self, once=False):
        """Keep the QR code and status lines current (the away link can appear a few seconds after start)."""
        if not self.win.winfo_exists():
            return
        import time
        away = remote.settings().get("away", False)
        url = self.remote.away_url
        if away and not url:
            status = self.remote.tunnel.status if self.remote.tunnel else "starting"
            self.away_status.config(text=L("Starting the secure link…", "正在建立安全连接……")
                                    if status != "error" else L("Couldn't start the secure link - retrying.",
                                                                "安全连接启动失败，正在重试。"),
                                    fg=holo.AMBER)
        elif away:
            self.away_status.config(text=L("✓ On. Your phone can reach this PC from anywhere.",
                                           "✓ 已开启。手机在任何地方都能连接这台电脑。"), fg=holo.GREEN)
        link_kind = "away" if (away and url) else "home"
        if link_kind != self._last_link or time.time() - self._qr_made > 540:   # codes last 10 minutes
            link = self.remote.pair_link(away=link_kind == "away")
            draw_qr(self.qr, link, 230, self.accent)
            self._last_link, self._qr_made = link_kind, time.time()
            if link_kind == "away":
                self.qr_note.config(text=L("Works anywhere. Then use “Add to Home Screen” to keep it like an app.",
                                           "在哪里都能用。之后选择“添加到主屏幕”，就能像应用一样使用。"))
            else:
                lan = remote.local_addresses(self.remote.port)
                pin = self.remote.new_pin()
                self.qr_note.config(text=L(f"Same Wi-Fi only. Or open {lan[0] if lan else '(no network)'} and type "
                                           f"PIN {pin[:3]} {pin[3:]}.",
                                           f"仅限同一 Wi-Fi。也可以打开 {lan[0] if lan else '（无网络）'} 并输入 "
                                           f"PIN {pin[:3]} {pin[3:]}。"))
        n = remote.paired_count()
        self.devices.config(text=L(f"{n} phone{'s' if n != 1 else ''} paired", f"已配对 {n} 部手机") if n
                            else L("No phones paired yet", "尚未配对手机"))
        if not once:
            self.win.after(1500, self.refresh)


class AndroidSetup:
    """Step-by-step: turn on Wireless debugging, pair with the code, connect."""

    def __init__(self, app, f):
        self.app, self.f, self.accent = app, f, app.accent
        self.win = win = tk.Toplevel(app.root, bg=holo.BG)
        win.title(L("Control your Android phone", "控制你的安卓手机"))
        win.geometry("640x600")
        holo.dark_titlebar(win)
        holo.Header(win, L("Android phone", "安卓手机"), L("WISP // PHONE CONTROL", "WISP // 手机控制"), self.accent,
                    f, width=640, height=74).pack(fill="x")
        body = tk.Frame(win, bg=holo.BG)
        body.pack(fill="both", expand=True, padx=24, pady=12)
        steps = [
            L("On the phone: Settings > About phone > tap “Build number” 7 times (turns on Developer options).",
              "在手机上：设置 > 关于手机 > 连续点“版本号”7 次（开启开发者选项）。"),
            L("Settings > Developer options > turn on “Wireless debugging” (phone and PC on the same Wi-Fi).",
              "设置 > 开发者选项 > 打开“无线调试”（手机和电脑连同一个 Wi-Fi）。"),
            L("Tap “Wireless debugging” > “Pair device with pairing code”, and type what it shows here:",
              "点“无线调试” > “使用配对码配对设备”，把显示的内容填到这里："),
        ]
        for i, text in enumerate(steps, 1):
            row = tk.Frame(body, bg=holo.BG)
            row.pack(fill="x", pady=4)
            badge = tk.Canvas(row, width=30, height=20, bg=holo.BG, highlightthickness=0)
            badge.create_polygon(holo.chamfer(0.5, 0.5, 29, 19, 4), fill=holo.mix(holo.BG, self.accent, 0.18),
                                 outline=self.accent)
            badge.create_text(15, 10, text=f"{i:02d}", font=f["label"], fill=self.accent)
            badge.pack(side="left", anchor="n", padx=(0, 10))
            tk.Label(row, text=text, bg=holo.BG, fg=holo.TEXT, font=f["small"], anchor="w", justify="left",
                     wraplength=520).pack(side="left", fill="x")
        form = holo.Card(body, accent=self.accent, padx=16, pady=12)
        form.pack(fill="x", pady=(10, 0))
        self.addr = self._field(form, L("IP address & port", "IP 地址和端口"), "192.168.1.23:37159")
        self.code = self._field(form, L("Wi-Fi pairing code", "Wi-Fi 配对码"), "123456")
        holo.Button(form, L("Pair and connect", "配对并连接"), self.pair, kind="primary", font=f["small"],
                    accent=self.accent).pack(anchor="e", pady=(8, 0))
        self.status = tk.Label(body, bg=holo.BG, fg=holo.DIM, font=f["small"], anchor="w", justify="left",
                               wraplength=580)
        self.status.pack(fill="x", pady=(10, 0))
        tk.Label(body, text=L("After this, just ask: “open Spotify on my phone”, “what's on my phone screen?”, "
                              "“reply ‘on my way’ in WhatsApp”. If the phone restarts, turn Wireless debugging on again "
                              "- Wisp reconnects by itself.",
                              "之后直接说：“在手机上打开 Spotify”“我手机屏幕上是什么？”。手机重启后，"
                              "重新打开无线调试即可，Wisp 会自动重新连接。"),
                 bg=holo.BG, fg=holo.DIM, font=f["small"], anchor="w", justify="left", wraplength=580).pack(
            fill="x", pady=(8, 0))

    def _field(self, parent, label, placeholder):
        row = tk.Frame(parent, bg=holo.PANEL)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=holo.PANEL, fg=holo.DIM, font=self.f["small"], width=18, anchor="w").pack(side="left")
        e = holo.entry(row, "", width=24, font=self.f["body"], accent=self.accent)
        e.pack(side="left", ipady=4)
        tk.Label(row, text=placeholder, bg=holo.PANEL, fg=holo.MUTED, font=self.f["mono"]).pack(side="left", padx=8)
        return e

    def pair(self):
        addr, code = self.addr.get().strip(), self.code.get().strip()
        self.status.config(text=L("Working…", "正在处理……"), fg=holo.DIM)

        def say(text, colour=holo.DIM):
            self.win.after(0, lambda: self.status.winfo_exists() and self.status.config(text=text, fg=colour))

        def work():
            import phone
            try:
                phone.ensure_adb(lambda t: say(t))
                phone.pair(addr, code)
                say(L("Paired. Connecting…", "已配对，正在连接……"))
                phone.connect()
                say(L("✓ Connected! Try: “open YouTube on my phone”.", "✓ 已连接！试试说：“在手机上打开 YouTube”。"),
                    holo.GREEN)
            except Exception as exc:
                say(f"✗ {exc}", holo.RED)
        threading.Thread(target=work, daemon=True).start()
