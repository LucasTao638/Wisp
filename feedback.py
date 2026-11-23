"""Feedback: ideas, problems and praise, sent straight to the developer.

Open it from the menu ("Send feedback"), the tray, the phone app, or by saying "I have a suggestion: ...".
You always see exactly what will be sent and press Send yourself.

It's delivered as a "feedback_submitted" event to the developer's PostHog project (the same place as the
anonymous usage stats). It's sent even if usage stats are off, because you're choosing to send it.
If you're offline it waits in feedback_outbox.json and goes later.
Prefer public? "Post on GitHub instead" opens a pre-filled GitHub issue.
"""
import json
import platform
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import app_info

ROOT = Path(__file__).resolve().parent
OUTBOX = ROOT / "feedback_outbox.json"
KINDS = ["idea", "problem", "praise", "other"]


def configured():
    return app_info.analytics_configured()


def log_tail(lines=60):
    """The end of the log, for problem reports (shown to you before sending)."""
    for name in ("wisp.log", "sidekick.log"):
        path = ROOT / name
        if path.exists():
            try:
                return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
            except OSError:
                pass
    return ""


def build(kind, message, rating=None, email="", log=""):
    import i18n
    import telemetry
    props = {"kind": kind if kind in KINDS else "other", "message": message.strip()[:5000],
             "app_version": app_info.VERSION, "os": f"{platform.system()} {platform.release()}",
             "language": i18n.LANG, "$process_person_profile": False, "$geoip_disable": True, "$ip": None}
    try:
        if rating and 1 <= int(rating) <= 5:
            props["rating"] = int(rating)
    except (TypeError, ValueError):
        pass
    if email.strip():
        props["email"] = email.strip()[:200]
    if log.strip():
        props["log"] = log[-8000:]
    return {"event": "feedback_submitted", "distinct_id": telemetry.install_id(), "properties": props,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _post(events):
    body = json.dumps({"api_key": app_info.POSTHOG_KEY, "batch": events}).encode()
    req = urllib.request.Request(f"{app_info.POSTHOG_HOST}/batch/", data=body,
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15).read()


def _load_outbox():
    try:
        return json.loads(OUTBOX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def send(kind, message, rating=None, email="", log=""):
    """Returns "sent", "queued" (offline - will retry) or "not_configured"."""
    if not configured():
        return "not_configured"
    event = build(kind, message, rating, email, log)
    try:
        _post([event])
        return "sent"
    except Exception:
        OUTBOX.write_text(json.dumps(_load_outbox() + [event]), encoding="utf-8")
        return "queued"


def retry_outbox():
    """Try to send anything that was saved while offline (called at startup and every hour)."""
    pending = _load_outbox()
    if pending and configured():
        try:
            _post(pending)
            OUTBOX.unlink(missing_ok=True)
        except Exception:
            pass
    timer = threading.Timer(3600, retry_outbox)
    timer.daemon = True
    timer.start()


def github_issue_url(kind, message, rating=None):
    if not app_info.repo_configured():
        return None
    labels = {"idea": "enhancement", "problem": "bug", "praise": "feedback", "other": "feedback"}
    title = (message.strip().splitlines() or ["Feedback"])[0][:80] or "Feedback"
    body = (f"{message.strip()}\n\n---\nType: {kind}" + (f" · Rating: {rating}/5" if rating else "")
            + f"\nWisp {app_info.VERSION} · {platform.system()} {platform.release()}")
    query = urllib.parse.urlencode({"title": title, "body": body, "labels": labels.get(kind, "feedback")})
    return f"https://github.com/{app_info.GITHUB_REPO}/issues/new?{query}"


# ---------- "How's it going?" once, after a week of use ----------
def maybe_nudge():
    """True the first time Wisp has been used on 7 different days (then never again)."""
    import telemetry
    data = telemetry._load()
    days = set(data.get("active_days", []))
    days.add(time.strftime("%Y-%m-%d"))
    data["active_days"] = sorted(days)[-30:]
    nudge = len(days) >= 7 and not data.get("feedback_nudged")
    if nudge:
        data["feedback_nudged"] = True
    telemetry._save(data)
    return nudge


# ---------- the window ----------
class FeedbackWindow:
    def __init__(self, parent, prefill="", accent="#38d6ff"):
        import tkinter as tk

        import ui_kit as ui
        from i18n import t
        self.ui, self.t = ui, t
        self.win = win = tk.Toplevel(parent, bg=ui.BG)
        win.title(t("fb_title"))
        win.geometry("560x640")
        win.attributes("-topmost", True)
        f = ui.fonts(win)
        self.accent = accent
        pad = {"padx": 24}
        tk.Label(win, text=t("fb_title"), bg=ui.BG, fg=accent, font=f["title"]).pack(anchor="w", pady=(20, 2), **pad)
        tk.Label(win, text=t("fb_intro"), bg=ui.BG, fg=ui.DIM, font=f["small"], wraplength=500,
                 justify="left").pack(anchor="w", **pad)

        tk.Label(win, text=t("fb_type"), bg=ui.BG, fg=ui.TEXT, font=f["head"]).pack(anchor="w", pady=(14, 4), **pad)
        self.kind = tk.StringVar(value="problem" if any(w in prefill.lower() for w in ("bug", "broken", "crash", "问题", "坏")) else "idea")
        kinds = tk.Frame(win, bg=ui.BG)
        kinds.pack(anchor="w", **pad)
        for key in KINDS:
            tk.Radiobutton(kinds, text=t(f"fb_{key}"), value=key, variable=self.kind, bg=ui.BG, fg=ui.TEXT,
                           selectcolor=ui.CARD, activebackground=ui.BG, activeforeground=ui.TEXT, font=f["small"],
                           command=self._kind_changed).pack(side="left", padx=(0, 10))

        tk.Label(win, text=t("fb_rating"), bg=ui.BG, fg=ui.TEXT, font=f["head"]).pack(anchor="w", pady=(14, 2), **pad)
        self.rating = 0
        stars = tk.Frame(win, bg=ui.BG)
        stars.pack(anchor="w", **pad)
        self.star_labels = []
        for i in range(1, 6):
            lbl = tk.Label(stars, text="☆", bg=ui.BG, fg=accent, font=("Segoe UI Symbol", 20), cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, n=i: self._set_rating(n))
            self.star_labels.append(lbl)

        tk.Label(win, text=t("fb_message"), bg=ui.BG, fg=ui.TEXT, font=f["head"]).pack(anchor="w", pady=(14, 4), **pad)
        self.text = tk.Text(win, height=6, bg="#1a222c", fg=ui.TEXT, insertbackground=ui.TEXT, bd=0, wrap="word",
                            highlightthickness=1, highlightbackground="#26303c", highlightcolor=accent, font=f["body"])
        self.text.pack(fill="x", **pad)
        self.text.insert("1.0", prefill)

        tk.Label(win, text=t("fb_email"), bg=ui.BG, fg=ui.DIM, font=f["small"]).pack(anchor="w", pady=(12, 2), **pad)
        self.email = ui.entry(win, "", width=40, f=f["body"])
        self.email.pack(anchor="w", ipady=4, **pad)

        self.attach = tk.BooleanVar(value=False)
        self.attach_box = tk.Checkbutton(win, text=t("fb_attach_log"), variable=self.attach, bg=ui.BG, fg=ui.TEXT,
                                         selectcolor=ui.CARD, activebackground=ui.BG, activeforeground=ui.TEXT,
                                         font=f["small"], wraplength=500, justify="left", command=self._show_log)
        self.log_view = tk.Text(win, height=5, bg=ui.CARD, fg=ui.DIM, bd=0, wrap="none", font=("Consolas", 8))
        tk.Label(win, text=t("fb_includes"), bg=ui.BG, fg=ui.DIM, font=f["small"]).pack(anchor="w", pady=(10, 0), **pad)
        self.status = tk.Label(win, text="", bg=ui.BG, fg=ui.DIM, font=f["small"], wraplength=500, justify="left")
        self.status.pack(anchor="w", pady=4, **pad)

        buttons = tk.Frame(win, bg=ui.BG)
        buttons.pack(fill="x", side="bottom", pady=16, **pad)
        ui.FlatButton(buttons, t("fb_send"), self.send, bg=accent, fg="#031018", hover=accent).pack(side="right")
        ui.FlatButton(buttons, t("fb_cancel"), win.destroy).pack(side="right", padx=8)
        if app_info.repo_configured():
            ui.FlatButton(buttons, t("fb_github"), self.github, font=f["small"]).pack(side="left")
        self._kind_changed()
        self.text.focus_set()

    def _set_rating(self, n):
        self.rating = n
        for i, lbl in enumerate(self.star_labels, start=1):
            lbl.config(text="★" if i <= n else "☆")

    def _kind_changed(self):
        if self.kind.get() == "problem":
            self.attach_box.pack(anchor="w", padx=24, pady=(10, 0), before=self.status)
        else:
            self.attach.set(False)
            self.attach_box.pack_forget()
            self.log_view.pack_forget()

    def _show_log(self):
        if self.attach.get():
            self.log_view.delete("1.0", "end")
            self.log_view.insert("1.0", log_tail() or "(empty)")
            self.log_view.pack(fill="x", padx=24, pady=4, before=self.status)
        else:
            self.log_view.pack_forget()

    def _message(self):
        return self.text.get("1.0", "end").strip()

    def send(self):
        message = self._message()
        if not message:
            self.status.config(text=self.t("fb_empty"), fg=self.ui.RED)
            return
        log = log_tail() if self.attach.get() else ""

        def work():
            result = send(self.kind.get(), message, self.rating or None, self.email.get(), log)
            text = {"sent": self.t("fb_sent"), "queued": self.t("fb_queued"), "not_configured": self.t("fb_not_setup")}[result]
            colour = self.ui.GREEN if result != "not_configured" else self.ui.RED

            def done():
                self.status.config(text=text, fg=colour)
                if result != "not_configured":
                    self.win.after(1500, self.win.destroy)
            self.win.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def github(self):
        url = github_issue_url(self.kind.get(), self._message() or "Feedback", self.rating or None)
        if url:
            webbrowser.open(url)
            self.win.destroy()
