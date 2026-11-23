"""Wisp - classic chat window (set "ui": "classic" in config.json to use it).

Type in the box, or hold the mic button / F9 to talk.
"""
import os
import queue
import re
import sys
import tkinter as tk
from tkinter import font as tkfont

import background
from core import Assistant

if sys.platform == "win32":
    try:  # sharp text on high-resolution screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# ---------- look and feel ----------
BG = "#16181d"
PANEL = "#1f2229"
FIELD = "#2a2e37"
TEXT = "#e8eaed"
MUTED = "#8b919c"
ACCENT = "#6c8cff"
USER = "#9db4ff"
ERROR = "#ff7b72"
STATUS = {  # status -> (dot colour, label)
    "starting": ("#8b919c", "Starting up"),
    "ready": ("#3fb950", "Ready"),
    "listening": ("#ff5c5c", "Listening"),
    "thinking": ("#e3b341", "Thinking"),
    "speaking": ("#6c8cff", "Speaking"),
}


def clean_markdown(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


class FlatButton(tk.Label):
    """A simple flat, rounded-looking button that works with dark colours on Windows."""

    def __init__(self, parent, text, command=None, bg=FIELD, fg=TEXT, hover="#363b46", **kw):
        super().__init__(parent, text=text, bg=bg, fg=fg, padx=12, pady=6, cursor="hand2", **kw)
        self._bg, self._hover, self.command, self.enabled = bg, hover, command, True
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))
        self.bind("<ButtonRelease-1>", lambda e: self.enabled and self.command and self.command())

    def set_colour(self, bg):
        self._bg = bg
        self.config(bg=bg)

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.config(fg=TEXT if enabled else MUTED, cursor="hand2" if enabled else "arrow")


class WispApp:
    def __init__(self):
        self.events = queue.Queue()
        self.assistant = Assistant(lambda kind, text: self.events.put((kind, text)))
        self.status = "starting"
        self.dots = 0
        self.jobs_window = None

        self.root = root = tk.Tk()
        root.title("Wisp")
        root.configure(bg=BG)
        root.minsize(360, 420)
        w, h = 440, 640
        x = root.winfo_screenwidth() - w - 40
        y = root.winfo_screenheight() - h - 90
        root.geometry(f"{w}x{h}+{x}+{y}")

        base = "Segoe UI" if sys.platform == "win32" else "Helvetica"
        self.f_body = tkfont.Font(family=base, size=11)
        self.f_small = tkfont.Font(family=base, size=9)
        self.f_bold = tkfont.Font(family=base, size=11, weight="bold")
        self.f_title = tkfont.Font(family=base, size=13, weight="bold")
        root.option_add("*Font", self.f_body)

        self._build_header()
        self._build_chat()
        self._build_input()

        root.bind("<Escape>", lambda e: self.assistant.stop())
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.add("info", "Hi! Type below, or hold the mic button (or F9) and talk.")
        self.assistant.start()
        root.after(50, self.poll)
        root.after(400, self.animate)

    # ---------- layout ----------
    def _build_header(self):
        bar = tk.Frame(self.root, bg=PANEL, padx=14, pady=10)
        bar.pack(fill="x")
        self.dot = tk.Canvas(bar, width=12, height=12, bg=PANEL, highlightthickness=0)
        self.dot_id = self.dot.create_oval(1, 1, 11, 11, fill=STATUS["starting"][0], outline="")
        self.dot.pack(side="left")
        tk.Label(bar, text="Wisp", bg=PANEL, fg=TEXT, font=self.f_title).pack(side="left", padx=(8, 6))
        self.status_label = tk.Label(bar, text="Starting up", bg=PANEL, fg=MUTED, font=self.f_small)
        self.status_label.pack(side="left")

        self.pin_btn = FlatButton(bar, "Pin", self.toggle_pin, bg=PANEL, font=self.f_small)
        self.pin_btn.pack(side="right", padx=2)
        self.mute_btn = FlatButton(bar, "Mute" if not self.assistant.muted else "Unmute",
                                   self.toggle_mute, bg=PANEL, font=self.f_small)
        self.mute_btn.pack(side="right", padx=2)
        FlatButton(bar, "Jobs", self.show_jobs, bg=PANEL, font=self.f_small).pack(side="right", padx=2)
        FlatButton(bar, "New chat", self.assistant.new_chat, bg=PANEL, font=self.f_small).pack(side="right", padx=2)

    def _build_chat(self):
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="both", expand=True)
        scroll = tk.Scrollbar(frame, bg=BG, troughcolor=BG, bd=0, width=10)
        scroll.pack(side="right", fill="y")
        self.chat = tk.Text(frame, bg=BG, fg=TEXT, wrap="word", bd=0, padx=16, pady=12,
                            highlightthickness=0, cursor="arrow", spacing1=2, spacing3=2,
                            yscrollcommand=scroll.set, insertbackground=TEXT)
        self.chat.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.chat.yview)
        c = self.chat
        c.tag_config("you_label", foreground=MUTED, font=self.f_small, justify="right", spacing1=10)
        c.tag_config("you", foreground=USER, justify="right", lmargin1=60, lmargin2=60)
        c.tag_config("bot_label", foreground=MUTED, font=self.f_small, spacing1=10)
        c.tag_config("bot", foreground=TEXT, rmargin=30)
        c.tag_config("say", foreground=TEXT, font=self.f_bold, rmargin=30)
        c.tag_config("tool", foreground=MUTED, font=self.f_small, lmargin1=8, lmargin2=20)
        c.tag_config("info", foreground=MUTED, font=self.f_small, justify="center", spacing1=6, spacing3=6)
        c.tag_config("error", foreground=ERROR, spacing1=6)
        c.config(state="disabled")
        # allow selecting/copying text even though it's read-only
        c.bind("<1>", lambda e: c.focus_set())

    def _build_input(self):
        bar = tk.Frame(self.root, bg=PANEL, padx=12, pady=12)
        bar.pack(fill="x")
        box = tk.Frame(bar, bg=FIELD, padx=10, pady=8)
        box.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(box, bg=FIELD, fg=TEXT, bd=0, insertbackground=TEXT,
                              highlightthickness=0, font=self.f_body)
        self.entry.pack(fill="x")
        self.entry.bind("<Return>", lambda e: self.send())
        self.entry.focus_set()

        self.mic_btn = FlatButton(bar, "Hold to talk", bg=FIELD)
        self.mic_btn.pack(side="left", padx=(8, 0), ipady=2)
        self.mic_btn.bind("<ButtonPress-1>", lambda e: self.mic_btn.enabled and self.assistant.start_listening())
        self.mic_btn.bind("<ButtonRelease-1>", lambda e: self.mic_btn.enabled and self.assistant.stop_listening())
        self.mic_btn.set_enabled(False)

        self.send_btn = FlatButton(bar, "Send", self.send, bg=ACCENT, fg="#ffffff", hover="#8aa3ff")
        self.send_btn.pack(side="left", padx=(8, 0), ipady=2)
        self.stop_btn = FlatButton(bar, "Stop", self.assistant.stop, bg=FIELD)
        self.stop_btn.pack(side="left", padx=(8, 0), ipady=2)

    # ---------- chat ----------
    def add(self, kind, text):
        c = self.chat
        c.config(state="normal")
        if kind == "user":
            c.insert("end", "You\n", "you_label")
            c.insert("end", text + "\n", "you")
            self.last_bot_label = False
        elif kind in ("tool", "reply", "say"):
            if not getattr(self, "last_bot_label", False):
                c.insert("end", "Wisp\n", "bot_label")
                self.last_bot_label = True
            if kind == "tool":
                c.insert("end", "› " + text + "\n", "tool")
            elif kind == "reply":
                c.insert("end", clean_markdown(text) + "\n", "bot")
            else:
                c.insert("end", text + "\n", "say")
        elif kind == "error":
            c.insert("end", text + "\n", "error")
        else:
            c.insert("end", text + "\n", "info")
        c.config(state="disabled")
        c.see("end")

    def send(self):
        text = self.entry.get().strip()
        if text:
            self.entry.delete(0, "end")
            self.assistant.submit(text)

    # ---------- events from the assistant ----------
    def poll(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "status":
                    self.set_status(text)
                elif kind == "voice":
                    self.mic_btn.set_enabled(text == "on")
                elif kind == "info" and text.startswith("took "):
                    self.add("tool", text)
                else:
                    self.add(kind, text)
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def set_status(self, status):
        self.status = status
        colour, label = STATUS.get(status, STATUS["ready"])
        self.dot.itemconfig(self.dot_id, fill=colour)
        self.status_label.config(text=label)
        self.mic_btn.set_colour("#a33b3b" if status == "listening" else FIELD)
        if status == "listening":
            self.mic_btn.config(text="Listening...")
        else:
            self.mic_btn.config(text="Hold to talk")

    def animate(self):
        if self.status in ("thinking", "starting", "listening"):
            self.dots = (self.dots + 1) % 4
            self.status_label.config(text=STATUS[self.status][1] + "." * self.dots)
        self.root.after(400, self.animate)

    # ---------- header buttons ----------
    def toggle_pin(self):
        on = not self.root.attributes("-topmost")
        self.root.attributes("-topmost", on)
        self.pin_btn.config(text="Unpin" if on else "Pin")

    def toggle_mute(self):
        self.assistant.set_muted(not self.assistant.muted)
        self.mute_btn.config(text="Unmute" if self.assistant.muted else "Mute")

    def show_jobs(self):
        if self.jobs_window and self.jobs_window.winfo_exists():
            self.jobs_window.lift()
            return
        win = self.jobs_window = tk.Toplevel(self.root, bg=BG)
        win.title("Background jobs")
        win.geometry("520x460")
        tk.Label(win, text="Background jobs", bg=BG, fg=TEXT, font=self.f_title).pack(anchor="w", padx=14, pady=(12, 4))
        tk.Label(win, text='Start one by saying "in the background, ..." - click a job to see its result.',
                 bg=BG, fg=MUTED, font=self.f_small).pack(anchor="w", padx=14)
        listbox = tk.Listbox(win, bg=PANEL, fg=TEXT, bd=0, highlightthickness=0, height=8,
                             selectbackground=ACCENT, activestyle="none")
        listbox.pack(fill="x", padx=14, pady=8)
        detail = tk.Text(win, bg=PANEL, fg=TEXT, wrap="word", bd=0, padx=10, pady=8, highlightthickness=0)
        detail.pack(fill="both", expand=True, padx=14)
        buttons = tk.Frame(win, bg=BG)
        buttons.pack(fill="x", padx=14, pady=10)
        FlatButton(buttons, "Open jobs folder",
                   lambda: os.startfile(background.JOBS) if hasattr(os, "startfile") else None).pack(side="left")
        FlatButton(buttons, "Open output folder",
                   lambda: os.startfile(background.ROOT / "workspace" / "output") if hasattr(os, "startfile") else None
                   ).pack(side="left", padx=8)
        jobs = []

        def show(_=None):
            sel = listbox.curselection()
            if not sel:
                return
            job = jobs[sel[0]]
            body = f"Task: {job['task']}\nStatus: {job['status']}   Started: {job.get('started', '')}"
            if job.get("finished"):
                body += f"   Finished: {job['finished']}"
            body += "\n\n" + clean_markdown(job.get("result") or job.get("error") or "Still working on it...")
            detail.config(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", body)
            detail.config(state="disabled")

        def refresh():
            if not win.winfo_exists():
                return
            selected = listbox.curselection()
            jobs[:] = background.list_jobs(limit=30)
            listbox.delete(0, "end")
            icons = {"done": "✓", "failed": "✗", "running": "…", "queued": "…"}
            for job in jobs:
                listbox.insert("end", f" {icons.get(job['status'], '?')}  {job['task'][:60]}")
            if not jobs:
                listbox.insert("end", " No background jobs yet.")
            if selected and selected[0] < len(jobs):
                listbox.selection_set(selected[0])
            win.after(3000, refresh)

        listbox.bind("<<ListboxSelect>>", show)
        refresh()

    def quit(self):
        self.assistant.shutdown()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    WispApp().run()
