"""Wisp - minimal HUD (the default look). A floating, animated orb with no window frame.

  Click the orb (or hold F9) to talk     Type a command in the box underneath
  Drag anywhere to move it               Right-click for the menu
  Esc stops the current task             Double-click the text to see the whole conversation
  Say "Hey Jarvis" to talk hands-free.  Tray icon / Ctrl+Shift+Space: show or hide. Hides itself while a game or video is fullscreen.
"""
import math
import threading
import queue
import re
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

import autostart
import background
import remote
import updates
import i18n
from i18n import L, t
tr = t  # same function; for places where t means the time
from app_info import APP_NAME
from context import hide_from_screenshots
import classic_ui  # reuses its jobs window
from hud_draw import KEY, draw_orb, hex_to_rgb, make_see_through, mix, orb_state, pick_fonts
from hud_menu import HudMenu
from overlay import FullHud
from widget import TalkWidget
from classic_ui import clean_markdown
from core import Assistant

if sys.platform == "win32":
    try:  # sharp text on high-resolution screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

PANEL = "#0a0e13"
TEXT = "#dfe7ef"
DIM = "#6b7785"
RED = "#ff6b6b"

AMBER_TEXT = "#ffb547"
FIELD_BG = "#121820"
STATUS_WORDS = {s: f"status_{s}" for s in ("starting", "ready", "listening", "thinking", "speaking")}


def _key_label(key):
    import hotkeys
    return hotkeys.label(key) if key else ""


class _CaptureGuard:
    """Used around a screenshot on Mac: hides Wisp's windows, then brings them back."""

    def __init__(self, app):
        self.app = app

    def __enter__(self):
        done = threading.Event()
        self.app.events.put(("ui_capture", ("hide", done)))
        done.wait(2)
        time.sleep(0.35)  # let macOS finish redrawing
        return self

    def __exit__(self, *exc):
        self.app.events.put(("ui_capture", ("show", None)))
        return False


class OrbApp:
    def __init__(self):
        self.events = queue.Queue()
        self.assistant = Assistant(lambda kind, text: self.events.put((kind, text)))
        self.cfg = self.assistant.cfg
        self.accent = self.cfg.get("accent_colour", "#38d6ff")
        self.status = "starting"
        import hotkeys
        self.caption = t("click_to_talk", key=hotkeys.label(self.cfg.get("talk_key", "f9")))
        self.step = ""
        self.log = []                  # everything that's happened, for the conversation window
        self.transcript = None
        self.jobs_window = None
        self.voice_on = False
        self.level = 0.0               # smoothed mic level
        self.ripples = []
        self._drag = None
        self.popup = None
        self.on_top = True
        self.peeking = False   # shown briefly because "Hey Jarvis" was said while hidden
        self.corner_visible = True

        self.root = root = tk.Tk()
        root.title("Wisp")
        self.s = max(1.0, root.winfo_fpixels("1i") / 96)  # screen scaling
        s = self.s
        self.W, self.H = int(380 * s), int(540 * s)
        self.cx, self.cy = self.W / 2, 190 * s

        root.overrideredirect(True)           # no title bar or border
        root.attributes("-topmost", True)
        root.configure(bg=KEY)
        root.geometry(f"{self.W}x{self.H}+{self._corner()[0]}+{self._corner()[1]}")
        self.hidden = False
        self.auto_hidden = False

        hud, body = pick_fonts(tkfont)
        self.f_status = tkfont.Font(family=hud, size=10, weight="bold")
        self.f_caption = tkfont.Font(family=body, size=11)
        self.f_small = tkfont.Font(family=body, size=9)
        self.f_title = tkfont.Font(family=hud, size=13, weight="bold")
        self.f_body = tkfont.Font(family=body, size=11)

        self.canvas = c = tk.Canvas(root, width=self.W, height=self.H, bg=KEY, highlightthickness=0)
        make_see_through(root, c)
        c.pack(fill="both", expand=True)
        self._build_panel()

        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Button-3>", lambda e: self.open_menu(e.x_root, e.y_root))
        c.bind("<Double-Button-1>", self._double_click)
        root.bind("<Escape>", lambda e: self.assistant.stop())

        self.assistant.start()
        self._start_tray()
        self._register_show_hide_key()
        self.overlay = FullHud(self)
        self.widget = TalkWidget(self)
        if sys.platform == "darwin":  # Mac can't exclude windows from screenshots: hide them for a moment
            import context
            context.screenshot_guard = lambda: _CaptureGuard(self)
        hide_from_screenshots(self.root)  # keep the orb out of screenshots (yours, Claude's and the phone's)
        import traceback
        self.root.report_callback_exception = lambda et, ev, tb: print(
            "(UI error)\n" + "".join(traceback.format_exception(et, ev, tb)))
        self.assistant.ui_action = lambda action: self.events.put(("ui", action))
        self.remote = remote.PhoneRemote(self.assistant, self.cfg.get("phone_port", 8765))
        self.phone_window = None
        if remote.is_enabled():
            self.remote.start()
        self.update_info = None
        self.updater = updates.UpdateChecker(lambda info: self.events.put(("ui_update", info)))
        self.updater.start()
        import feedback
        feedback.retry_outbox()  # anything written while offline
        if feedback.maybe_nudge():  # once, after a week of use: "how's it going?"
            self.root.after(15000, lambda: setattr(self, "caption", t("fb_nudge")))
        try:
            autostart.migrate()  # old "Sidekick" startup shortcut -> "Wisp"
        except Exception:
            pass
        if self.cfg.get("start_hidden", False) or "--startup" in sys.argv:
            root.after(500, self.hide)
        if self.cfg.get("auto_hide_fullscreen", True) and sys.platform == "win32":
            root.after(1500, self._watch_fullscreen)
        root.after(30, self.poll)
        root.after(16, self.animate)

    # ---------- static parts: text panel + input box ----------
    def _build_panel(self):
        s, c, W = self.s, self.canvas, self.W
        top, bottom, r = 345 * s, 530 * s, 22 * s
        x1, x2 = 14 * s, W - 14 * s
        pts = [x1 + r, top, x2 - r, top, x2, top, x2, top + r, x2, bottom - r, x2, bottom,
               x2 - r, bottom, x1 + r, bottom, x1, bottom, x1, bottom - r, x1, top + r, x1, top]
        c.create_polygon(pts, smooth=True, fill=PANEL, outline=mix(PANEL, self.accent, 0.35), width=1)

        self.status_id = c.create_text(W / 2, top + 24 * s, text="", font=self.f_status, fill=self.accent)
        self.step_id = c.create_text(W / 2, top + 46 * s, text="", font=self.f_small, fill=DIM, width=W - 70 * s)
        self.caption_id = c.create_text(W / 2, top + 64 * s, text="", font=self.f_caption, fill=TEXT,
                                        width=W - 70 * s, justify="center", anchor="n")
        self.menu_id = c.create_text(x2 - 22 * s, top + 24 * s, text="⋯", font=self.f_title, fill=DIM)
        c.tag_bind(self.menu_id, "<ButtonRelease-1>", lambda e: self.open_menu(e.x_root, e.y_root))
        self.hide_id = c.create_text(x1 + 22 * s, top + 22 * s, text="\u2013", font=self.f_title, fill=DIM)
        c.tag_bind(self.hide_id, "<ButtonRelease-1>", lambda e: self.root.after(10, self.hide))

        # input box
        self.entry = tk.Entry(self.root, bg=PANEL, fg=TEXT, bd=0, highlightthickness=0,
                              insertbackground=self.accent, font=self.f_body, justify="center")
        c.create_window(W / 2, bottom - 30 * s, window=self.entry, width=W - 80 * s, height=26 * s)
        c.create_line(40 * s, bottom - 15 * s, W - 40 * s, bottom - 15 * s, fill=mix(PANEL, self.accent, 0.45))
        self.placeholder = True
        self._show_placeholder()
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", lambda e: self._show_placeholder())
        self.entry.bind("<Button-1>", lambda e: (self.root.focus_force(), self.entry.focus_set()))
        self.entry.bind("<Return>", lambda e: self.send())
        self.entry.bind("<Escape>", lambda e: self.assistant.stop())

    def _show_placeholder(self):
        if not self.entry.get():
            self.placeholder = True
            self.entry.config(fg=DIM)
            self.entry.insert(0, t("type_placeholder"))

    def _clear_placeholder(self, _=None):
        if self.placeholder:
            self.entry.delete(0, "end")
            self.entry.config(fg=TEXT)
            self.placeholder = False

    def send(self):
        self.peeking = False
        text = "" if self.placeholder else self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.assistant.submit(text)

    def open_menu(self, x, y):
        if self.popup and self.popup.alive():
            self.popup.close()
        a = self.assistant
        wake_name = (self.cfg.get("wake_word") or "").replace("_", " ").title()

        def set_on_top(on):
            self.on_top = on
            self.root.attributes("-topmost", on)

        items = [
            *([{"label": t("menu_update", version=self.update_info["version"]), "command": self.install_update}]
              if self.update_info else []),
            {"label": t("menu_settings"), "command": self.show_settings},
            {"label": L("Run setup again", "重新运行设置"), "command": self.run_setup},
            {"label": t("menu_hud"), "command": self.overlay.open,
             "hint": _key_label(self.cfg.get("hud_key", "ctrl+shift+j"))},
            {"label": t("menu_conversation"), "command": self.show_transcript},
            {"label": t("menu_phone"), "command": self.show_phone_window},
            {"label": t("menu_routines"), "command": self.show_routines},
            {"label": t("menu_feedback"), "command": self.show_feedback},
            {"label": t("menu_jobs"), "command": self.show_jobs},
            {"label": t("menu_new_chat"), "command": a.new_chat},
            {"sep": True},
            {"label": t("menu_mute"), "toggle": (lambda: a.muted, a.set_muted)},
        ]
        if a.wake:
            items.append({"label": t("menu_listen_for", phrase=wake_name),
                          "toggle": (lambda: a.wake_enabled, lambda on: setattr(a, "wake_enabled", on))})
        items += [
            {"label": t("menu_on_top"), "toggle": (lambda: self.on_top, set_on_top)},
        ]
        if sys.platform == "win32":
            items.append({"label": t("menu_autostart"), "toggle": (autostart.is_enabled, autostart.set_enabled)})
        items += [
            {"sep": True},
            {"label": t("menu_stop"), "command": a.stop, "hint": "Esc"},
            {"label": t("menu_corner"), "command": self.to_corner},
            {"label": t("menu_log"), "command": self.open_log},
            {"label": t("menu_hide"), "command": self.hide,
             "hint": _key_label(self.cfg.get("show_hide_key", ""))},
            {"sep": True},
            {"label": t("menu_quit"), "command": self.quit, "danger": True},
        ]
        self.popup = HudMenu(self.root, items, x, y, self.accent, self.f_body, self.f_small, self.s,
                             panel=PANEL, text=TEXT, dim=DIM, danger=RED)

    # ---------- mouse: drag to move, click the orb to talk ----------
    def _press(self, e):
        self.peeking = False
        self._drag = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y(), False)

    def _motion(self, e):
        if not self._drag:
            return
        x0, y0, wx, wy, moved = self._drag
        dx, dy = e.x_root - x0, e.y_root - y0
        if moved or abs(dx) + abs(dy) > 4:
            self._drag = (x0, y0, wx, wy, True)
            self.root.geometry(f"+{wx + dx}+{wy + dy}")

    def _release(self, e):
        drag, self._drag = self._drag, None
        if drag and drag[4]:
            cx, cy = self._corner()
            if abs(self.root.winfo_x() - cx) + abs(self.root.winfo_y() - cy) < 160 * self.s:
                self.to_corner()
            return
        if self._near_button(e):
            return
        if drag and not drag[4] and math.hypot(e.x - self.cx, e.y - self.cy) < 130 * self.s:
            if self.voice_on:
                self.assistant.toggle_listening()
            else:
                self.caption = L("Voice isn't available - type a command below.", "语音不可用，请在下方输入指令。")

    def _double_click(self, e):
        if e.y > 340 * self.s:
            self.show_transcript()

    # ---------- events from the assistant ----------
    def poll(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "ui":
                    self._ui_action(text)
                    continue
                if kind == "ui_capture":
                    self._capture_visibility(*text)
                    continue
                if kind == "ui_update":
                    self.update_info = text
                    self.caption = t("update_available", app=APP_NAME, version=text["version"])
                    background.notify(APP_NAME, L(f"Version {text['version']} is available. Right-click the orb to update.",
                                                  f"新版本 {text['version']} 可用。右键点击光球即可更新。"))
                    continue
                if kind == "wake":
                    self.caption = t("yes")
                    if not self._show_talk_view() and self.hidden and not self.auto_hidden \
                            and self._talk_view() != "widget":
                        self.show()          # pop up while helping, then tuck away again
                        self.peeking = True
                    continue
                if kind == "hearing":        # what's been heard so far, while you're still talking
                    self.caption = f"“{text} …”"
                    self.widget.on_event(kind, text)
                    continue
                self.log.append((kind, text))
                self._append_transcript(kind, text)
                self.widget.on_event(kind, text)
                if self.overlay.is_open:
                    self.overlay.on_event(kind, text)
                elif kind == "tool":
                    self.overlay.on_event(kind, text)  # keep the activity list up to date
                if kind == "status":
                    self.status = text
                    if text == "listening":
                        self._show_talk_view()
                    if text == "ready" and self.peeking:
                        self.root.after(int(self.cfg.get("peek_seconds", 6) * 1000), self._end_peek)
                    if text in ("ready", "speaking"):
                        self.step = ""
                elif kind == "voice":
                    self.voice_on = text == "on"
                elif kind == "user":
                    self.caption = f"“{text}”"
                    self.step = ""
                elif kind == "tool":
                    if "windows-mcp" in text and self.overlay.is_open:
                        # Claude is about to click around in your apps - get out of the way
                        self.overlay.close("Working in your apps\u2026")
                    if not text.startswith("took "):
                        self.step = "› " + self._friendly_step(text)
                elif kind == "say":
                    self.caption = text
                elif kind == "alert":  # a timer went off, or a focus session changed
                    self.caption = text
                    self._show_talk_view()
                elif kind == "error":
                    self.caption = text
                    self.status = "ready"
                elif kind == "info" and not text.startswith("took "):
                    if self.status in ("starting", "ready") or "Stopped" in text:
                        self.caption = text
        except queue.Empty:
            pass
        self.root.after(30, self.poll)

    @staticmethod
    def _friendly_step(step):
        name, _, detail = step.partition("  ")
        name = re.sub(r"^mcp__windows-mcp__", "", name)
        label = t(f"step_{name}") if not t(f"step_{name}").startswith("step_") else name
        return f"{label}: {detail}" if detail else label

    # ---------- the orb ----------
    def animate(self):
        c, s, t = self.canvas, self.s, time.time()
        c.delete("orb")
        if self.corner_visible:
            status, colour, pulse, spin = orb_state(self, t)
            draw_orb(c, self.cx, self.cy, s, colour, pulse, spin, t, self.ripples, tag="orb")
        else:
            status, colour = self.status, self.accent

        # text
        word = tr(STATUS_WORDS.get(status, "status_ready"))
        if status in ("thinking", "starting"):
            word += "." * (int(t * 2.5) % 4)
        c.itemconfig(self.status_id, text="  ".join(word), fill=colour)
        c.itemconfig(self.step_id, text=self.step[:80] or self._timer_line(t))
        caption = clean_markdown(self.caption)
        c.itemconfig(self.caption_id, text=caption if len(caption) < 230 else caption[:227] + "…")
        c.tag_raise("orb")
        self.root.after(33, self.animate)

    def _timer_line(self, t):
        """'⏱ Pasta 4:32' under the status, when a timer is running (checked twice a second)."""
        if t - getattr(self, "_timer_checked", 0) > 0.5:
            self._timer_checked = t
            self._next_timer = self.assistant.next_timer()
        import focus
        session = focus.session_text() if t - getattr(self, "_session_checked", 0) > 0.5 else getattr(self, "_session", None)
        if t - getattr(self, "_session_checked", 0) > 0.5:
            self._session_checked, self._session = t, session
        if session:
            return "\u25c9 " + session
        nxt = getattr(self, "_next_timer", None)
        if not nxt:
            return ""
        import timers
        name, left, kind = nxt
        when = timers.clock(left) if kind == "timer" or left < 3600 else timers.say_time(time.time() + left)
        return f"\u23f1 {name}  {when}"

    def _capture_visibility(self, action, done):
        """Hide (then restore) Wisp's windows so a Mac screenshot shows your screen, not Wisp."""
        if action == "hide":
            self._hidden_for_capture = [w for w in (self.root, self.overlay.dim, self.overlay.hud, self.widget.win)
                                        if w is not None and w.winfo_viewable()]
            for w in self._hidden_for_capture:
                w.withdraw()
            self.root.update_idletasks()
            if done:
                done.set()
        else:
            for w in getattr(self, "_hidden_for_capture", []):
                try:
                    w.deiconify()
                except tk.TclError:
                    pass
            self._hidden_for_capture = []

    # ---------- position ----------
    def _work_area(self):
        """The screen area not covered by the taskbar."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
                return rect.left, rect.top, rect.right, rect.bottom
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - int(48 * self.s)

    def _corner(self):
        _, _, right, bottom = self._work_area()
        return right - self.W - int(12 * self.s), bottom - self.H - int(8 * self.s)

    def to_corner(self):
        x, y = self._corner()
        self.root.geometry(f"+{x}+{y}")

    def _near_button(self, e):
        """True if the click was on the small hide / menu buttons (not the orb)."""
        for item in (self.hide_id, self.menu_id):
            x1, y1, x2, y2 = self.canvas.bbox(item) or (0, 0, 0, 0)
            if x1 - 6 <= e.x <= x2 + 6 and y1 - 6 <= e.y <= y2 + 6:
                return True
        return False

    # ---------- show / hide ----------
    def hide(self, auto=False):
        if self.hidden:
            return
        self.hidden, self.auto_hidden, self.peeking = True, auto, False
        self.assistant.hotkeys_active = self.cfg.get("talk_key_while_hidden", False)
        # "Hey Jarvis" keeps working while hidden (and during fullscreen games unless turned off)
        self.assistant.wake_allowed = not auto or self.cfg.get("wake_word_while_fullscreen", True)
        if self.assistant.recording:
            self.assistant.stop_listening()
        if self.popup and self.popup.alive():
            self.popup.close()
        self.overlay.close()
        self.corner_visible = True  # force the withdraw below to happen
        self.set_corner_visible(False)

    def show(self):
        if not self.hidden:
            return
        self.hidden = self.auto_hidden = self.peeking = False
        self.assistant.hotkeys_active = True
        self.assistant.wake_allowed = True
        self.set_corner_visible(True)

    def set_corner_visible(self, visible):
        """Show or hide the small corner orb (it hides while the full HUD is open, or when you hide it)."""
        visible = visible and not self.hidden and not self.overlay.is_open
        if visible == self.corner_visible:
            return
        self.corner_visible = visible
        if visible:
            self.root.deiconify()
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", self.on_top)
            self.root.lift()
        else:
            self.root.withdraw()

    def _talk_view(self):
        """What appears when you talk: "widget" (side panel), "hud" (full screen) or "orb" (nothing extra)."""
        view = self.cfg.get("talk_view", "widget")
        return view if view in ("widget", "hud", "orb") else "widget"

    def _show_talk_view(self):
        """Open the widget or HUD for a conversation. Returns True if something opened."""
        view = self._talk_view()
        if view == "hud" and self._full_hud_allowed():
            self.overlay.open()
            return True
        if view == "widget" and not self.auto_hidden and not self.overlay.is_open:
            self.widget.show()
            return True
        return False

    def _full_hud_allowed(self):
        """Open the big HUD when talking - but never over a fullscreen game."""
        return self.cfg.get("full_hud", True) and not self.auto_hidden and not self.overlay.is_open

    def _end_peek(self):
        a = self.assistant
        if self.peeking and self.status == "ready" and not a.is_listening and not a.busy.is_set() \
                and not a.is_speaking:
            self.hide()

    def toggle(self):
        self.show() if self.hidden else self.hide()

    def _register_show_hide_key(self):
        key = self.cfg.get("show_hide_key", "ctrl+shift+space")
        if not key:
            return
        try:
            import hotkeys
            hotkeys.add_hotkey(key, lambda: self.events.put(("ui", "toggle")))
            hud_key = self.cfg.get("hud_key", "ctrl+shift+j")
            if hud_key:
                hotkeys.add_hotkey(hud_key, lambda: self.events.put(("ui", "hud")))
        except Exception as exc:
            print(f"(show/hide hotkey off: {exc})")

    # ---------- tray icon ----------
    def _tray_image(self):
        from PIL import Image, ImageDraw
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        accent = hex_to_rgb(self.accent)
        d.ellipse((4, 4, 60, 60), outline=accent + (255,), width=5)
        d.ellipse((20, 20, 44, 44), fill=accent + (255,))
        return img

    def _start_tray(self):
        if sys.platform == "darwin":
            # No tray on Mac (it can't share the main thread with this window): clicking Wisp's Dock icon
            # shows it again, and Cmd+Q quits.
            try:
                self.root.createcommand("::tk::mac::ReopenApplication", lambda *a: self.events.put(("ui", "toggle")))
                self.root.createcommand("::tk::mac::Quit", lambda *a: self.events.put(("ui", "quit")))
            except Exception:
                pass
            self.tray = None
            return
        try:
            import pystray
        except ImportError:
            print("(tray icon off: run  py -V:3.13 -m pip install pystray pillow)")
            return
        post = lambda action: (lambda icon=None, item=None: self.events.put(("ui", action)))
        menu = pystray.Menu(
            pystray.MenuItem(t("tray_show_hide"), post("toggle"), default=True),
            pystray.MenuItem(t("menu_hud"), post("hud")),
            pystray.MenuItem(t("menu_settings"), post("settings")),
            pystray.MenuItem(t("menu_phone"), post("phone")),
            pystray.MenuItem(t("tray_talk"), post("talk")),
            pystray.MenuItem(t("menu_new_chat"), post("new_chat")),
            pystray.MenuItem(t("menu_jobs"), post("jobs")),
            pystray.MenuItem(t("menu_corner"), post("corner")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("menu_feedback"), post("feedback")),
            pystray.MenuItem(t("menu_quit"), post("quit")),
        )
        try:
            self.tray = pystray.Icon("Wisp", self._tray_image(), "Wisp", menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception as exc:
            self.tray = None
            print(f"(tray icon off: {exc})")

    def _ui_action(self, action):
        if isinstance(action, tuple) and action[0] == "feedback":  # "I have a suggestion: ..."
            self.show_feedback(action[1])
            return
        if action == "feedback":
            self.show_feedback()
        elif action == "toggle":
            self.toggle()
        elif action == "talk":
            self.show()
            if self.voice_on:
                self.assistant.toggle_listening()
        elif action == "new_chat":
            self.assistant.new_chat()
        elif action == "jobs":
            self.show_jobs()
        elif action == "corner":
            self.show()
            self.to_corner()
        elif action == "hud":
            self.overlay.toggle()
        elif action == "phone":
            self.show_phone_window()
        elif action == "settings":
            self.show()
            self.show_settings()
        elif action == "quit":
            self.quit()

    # ---------- auto-hide while a game or video is fullscreen ----------
    def _foreground_is_fullscreen(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        own = {self.root.winfo_id()} | self.overlay.handles()
        try:
            own.add(int(self.root.wm_frame(), 16))
        except (ValueError, tk.TclError):
            pass
        if hwnd in own or user32.GetParent(self.root.winfo_id()) == hwnd:
            return False
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        if name.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False  # the desktop and taskbar
        style = user32.GetWindowLongW(hwnd, -16)
        if style & 0x00C00000 == 0x00C00000:
            return False  # has a title bar, so it's a normal (maybe maximised) window

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))
        m = info.rcMonitor
        return rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom

    def _watch_fullscreen(self):
        try:
            if self.overlay.is_open:
                raise StopIteration  # our own HUD is fullscreen - don't count it as a game
            fullscreen = self._foreground_is_fullscreen()
            if fullscreen and not self.hidden:
                self.hide(auto=True)
            elif not fullscreen and self.hidden and self.auto_hidden:
                self.show()
        except (Exception, StopIteration):
            pass
        self.root.after(1000, self._watch_fullscreen)

    # ---------- extra windows ----------
    def show_transcript(self):
        if self.transcript and self.transcript.winfo_exists():
            self.transcript.lift()
            return
        win = self.transcript = tk.Toplevel(self.root, bg=PANEL)
        win.title(L("Wisp - conversation", "Wisp - 对话记录"))
        win.geometry(f"{int(480 * self.s)}x{int(560 * self.s)}")
        text = tk.Text(win, bg=PANEL, fg=TEXT, wrap="word", bd=0, padx=16, pady=12,
                       highlightthickness=0, font=self.f_body)
        text.pack(fill="both", expand=True)
        text.tag_config("you", foreground=mix(self.accent, "#ffffff", 0.4), spacing1=10)
        text.tag_config("tool", foreground=DIM, font=self.f_small, lmargin1=10)
        text.tag_config("say", font=(self.f_body.actual("family"), 11, "bold"))
        text.tag_config("info", foreground=DIM, font=self.f_small)
        text.tag_config("error", foreground=RED)
        self.transcript_text = text
        for kind, item in self.log:
            self._append_transcript(kind, item)

    def _append_transcript(self, kind, item):
        if not (self.transcript and self.transcript.winfo_exists()) or kind in ("status", "voice"):
            return
        text = self.transcript_text
        line = {"user": L(f"You: {item}", f"你：{item}"), "tool": f"› {item}", "reply": clean_markdown(item),
                "say": item}.get(kind, item)
        text.config(state="normal")
        text.insert("end", line + "\n", {"user": "you"}.get(kind, kind))
        text.config(state="disabled")
        text.see("end")

    def show_phone_window(self):
        """Pairing window: shows the address to open on your phone and a 6-digit PIN."""
        if self.phone_window and self.phone_window.winfo_exists():
            self.phone_window.destroy()
        remote.set_enabled(True)
        if not self.remote.start():
            return
        pin = self.remote.new_pin()
        s = self.s
        win = self.phone_window = tk.Toplevel(self.root, bg=PANEL)
        win.title(L("Wisp - connect phone", "Wisp - 连接手机"))
        win.attributes("-topmost", True)
        win.geometry(f"{int(460 * s)}x{int(500 * s)}")
        accent = self.accent
        title = tk.Label(win, text=L("C O N N E C T   P H O N E", "连 接 手 机"), bg=PANEL, fg=accent, font=self.f_title)
        title.pack(pady=(int(22 * s), int(6 * s)))
        tk.Label(win, text=L("On your phone (same Wi-Fi), open this in the browser:", "在手机上（同一 Wi-Fi）用浏览器打开："), bg=PANEL, fg=DIM,
                 font=self.f_small).pack()
        addresses = remote.local_addresses(self.remote.port)
        for i, addr in enumerate(addresses[:3]):
            tk.Label(win, text=addr, bg=PANEL, fg=TEXT if i == 0 else DIM,
                     font=(self.f_title.actual("family"), 16 if i == 0 else 11, "bold")).pack(pady=(int(8 * s), 0))
        tk.Label(win, text=L("then type this PIN:", "然后输入这个 PIN 码："), bg=PANEL, fg=DIM, font=self.f_small).pack(pady=(int(18 * s), 0))
        tk.Label(win, text=f"{pin[:3]} {pin[3:]}", bg=PANEL, fg=accent,
                 font=(self.f_title.actual("family"), 40, "bold")).pack()
        expiry = tk.Label(win, text="", bg=PANEL, fg=DIM, font=self.f_small)
        expiry.pack()
        devices = tk.Label(win, text="", bg=PANEL, fg=DIM, font=self.f_small)
        devices.pack(pady=(int(14 * s), 0))
        tip = L("Tip: in your phone's browser, choose \u201cAdd to Home Screen\u201d to use it like an app.\n"
                "Away from home? Install Tailscale (free) on both, then use the 100.x address.",
                "提示：在手机浏览器中选择“添加到主屏幕”，就能像应用一样使用。\n"
                "不在家？在电脑和手机上都安装 Tailscale（免费），然后使用 100.x 开头的地址。")
        tk.Label(win, text=tip, bg=PANEL, fg=DIM, font=self.f_small, justify="center",
                 wraplength=int(410 * s)).pack(pady=(int(10 * s), 0))
        row = tk.Frame(win, bg=PANEL)
        row.pack(pady=int(16 * s))

        def forget():
            remote.forget_all()
            update()

        def turn_off():
            remote.set_enabled(False)
            self.remote.stop()
            win.destroy()
            self.caption = L("Phone remote is off.", "手机遥控已关闭。")
        classic_ui.FlatButton(row, L("Forget all phones", "忘记所有手机"), forget, font=self.f_small).pack(side="left", padx=4)
        classic_ui.FlatButton(row, L("Turn off phone remote", "关闭手机遥控"), turn_off, font=self.f_small).pack(side="left", padx=4)
        classic_ui.FlatButton(row, L("Done", "完成"), win.destroy, bg=accent, fg="#031018", hover=accent,
                              font=self.f_small).pack(side="left", padx=4)

        def update():
            if not win.winfo_exists():
                return
            left = self.remote.pin_expires - time.time()
            if self.remote.pin and left > 0:
                expiry.config(text=L("PIN works for ", "PIN 码剩余有效时间 ") + f"{int(left // 60)}:{int(left % 60):02d}", fg=DIM)
            else:
                expiry.config(text=L("PIN used or expired - reopen this window for a new one", "PIN 码已使用或已过期，请重新打开此窗口获取新的"), fg=AMBER_TEXT)
            n = remote.paired_count()
            devices.config(text=(L(f"{n} phone{'s' if n != 1 else ''} paired", f"已配对 {n} 部手机") if n
                                else L("No phones paired yet", "尚未配对手机")))
            win.after(1000, update)
        update()
        if not addresses:
            expiry.config(text=L("Couldn't find this computer's network address - is it connected to Wi-Fi?", "找不到这台电脑的网络地址，是否已连接 Wi-Fi？"))

    def show_routines(self):
        """Your routines in plain English, with Run / Delete. New ones: just tell Wisp "when I say X, do Y"."""
        import routines
        if getattr(self, "routines_window", None) and self.routines_window.winfo_exists():
            self.routines_window.lift()
            return
        s = self.s
        win = self.routines_window = tk.Toplevel(self.root, bg=PANEL)
        win.title(L("Wisp - routines", "Wisp - 例程"))
        win.geometry(f"{int(560 * s)}x{int(620 * s)}")
        tk.Label(win, text=L("R O U T I N E S", "例  程"), bg=PANEL, fg=self.accent, font=self.f_title).pack(pady=(int(18 * s), 2))
        tk.Label(win, text=L('To add one, just tell Wisp:  \u201cwhen I say movie night, open Netflix and turn the volume down\u201d\n'
                             'To change one:  \u201cadd Spotify to my gaming mode routine\u201d',
                             '添加例程，直接对 Wisp 说：“当我说电影之夜的时候，打开网飞并把音量调低”\n'
                             '修改例程：“把 Spotify 加到我的游戏模式例程里”'),
                 bg=PANEL, fg=DIM, font=self.f_small, justify="center").pack(pady=(0, int(10 * s)))
        body = tk.Frame(win, bg=PANEL)
        body.pack(fill="both", expand=True, padx=int(16 * s))
        bottom = tk.Frame(win, bg=PANEL)
        bottom.pack(fill="x", padx=int(16 * s), pady=int(12 * s))
        classic_ui.FlatButton(bottom, L("Edit the file (advanced)", "编辑文件（高级）"), lambda: self._open_file(routines.FILE),
                              font=self.f_small).pack(side="left")
        classic_ui.FlatButton(bottom, L("Close", "关闭"), win.destroy, bg=self.accent, fg="#031018", hover=self.accent,
                              font=self.f_small).pack(side="right")
        state = {"mtime": None}

        def run(name):
            self.assistant.submit(name)

        def delete(name):
            data = routines.load()
            data.pop(name, None)
            routines.save(data)
            build()

        def build():
            for w in body.winfo_children():
                w.destroy()
            data = routines.load()
            if not data:
                tk.Label(body, text=L("No routines yet.", "还没有例程。"), bg=PANEL, fg=DIM, font=self.f_body).pack(pady=20)
            for name, r in data.items():
                card = tk.Frame(body, bg=FIELD_BG, padx=int(14 * s), pady=int(10 * s))
                card.pack(fill="x", pady=int(5 * s))
                top = tk.Frame(card, bg=FIELD_BG)
                top.pack(fill="x")
                tk.Label(top, text=name.title(), bg=FIELD_BG, fg=self.accent, font=self.f_title).pack(side="left")
                classic_ui.FlatButton(top, L("Delete", "删除"), lambda n=name: delete(n), bg=FIELD_BG, font=self.f_small).pack(side="right")
                classic_ui.FlatButton(top, L("Run", "运行"), lambda n=name: run(n), bg=FIELD_BG, font=self.f_small).pack(side="right", padx=4)
                phrases = r.get("triggers") or [name]
                if i18n.is_zh():  # show the Chinese phrases first
                    phrases = sorted(phrases, key=lambda p: not any("\u4e00" <= ch <= "\u9fff" for ch in p))
                triggers = " / ".join(f"\u201c{trig}\u201d" for trig in phrases[:4])
                tk.Label(card, text=L(f"Say {triggers}", f"说 {triggers}"), bg=FIELD_BG, fg=DIM, font=self.f_small, anchor="w",
                         justify="left", wraplength=int(480 * s)).pack(fill="x", pady=(4, 0))
                tk.Label(card, text=(lambda d: d[:1].upper() + d[1:])(routines.describe(r)) + L(".", "。"), bg=FIELD_BG, fg=TEXT, font=self.f_small,
                         anchor="w", justify="left", wraplength=int(480 * s)).pack(fill="x", pady=(2, 0))
            problems = routines.check()
            if problems:
                tk.Label(body, text=L("Problem: ", "问题：") + problems[0], bg=PANEL, fg=RED, font=self.f_small,
                         wraplength=int(480 * s)).pack(pady=6)

        def watch():  # refresh when the file changes (e.g. after Wisp adds a routine)
            if not win.winfo_exists():
                return
            try:
                mtime = routines.FILE.stat().st_mtime
            except OSError:
                mtime = 0
            if mtime != state["mtime"]:
                state["mtime"] = mtime
                build()
            win.after(1500, watch)
        routines.load()
        watch()

    def open_log(self):
        from pathlib import Path
        log = Path(__file__).resolve().parent / "wisp.log"
        if not log.exists():
            log.write_text("(nothing logged yet)\n", encoding="utf-8")
        self._open_file(log)

    @staticmethod
    def _open_file(path):
        import subprocess
        if sys.platform == "win32":
            subprocess.Popen(["notepad", str(path)])

    def show_jobs(self):
        classic_ui.WispApp.show_jobs(self)  # same jobs window as the classic look

    def show_feedback(self, prefill=""):
        import feedback
        feedback.FeedbackWindow(self.root, prefill, self.accent)

    def run_setup(self):
        """Reopen the setup screen: restart Wisp with it showing first."""
        import ui_kit
        ui_kit.save_config({"setup_done": False})
        ui_kit.restart_wisp(self.root)

    def show_settings(self):
        from settings_ui import SettingsWindow
        if getattr(self, "settings_window", None) and self.settings_window.win.winfo_exists():
            self.settings_window.win.lift()
            return
        self.settings_window = SettingsWindow(self)

    def install_update(self):
        info = self.update_info

        def work():
            try:
                started = updates.install(info, on_progress=lambda m: setattr(self, "caption", m))
            except Exception as exc:
                self.caption = L(f"Update failed: {exc}", f"更新失败：{exc}")
                return
            if started:
                self.events.put(("ui", "quit"))
        threading.Thread(target=work, daemon=True).start()

    def restart(self):
        import ui_kit
        self._shutdown()
        ui_kit.restart_wisp(self.root)

    def quit(self):
        self._shutdown()
        self.root.destroy()

    def _shutdown(self):
        self.overlay.close()
        self.remote.stop()
        if getattr(self, "tray", None):
            try:
                self.tray.stop()
            except Exception:
                pass
        self.assistant.shutdown()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    OrbApp().run()
