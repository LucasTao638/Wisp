"""Phone remote: control Wisp from your phone's web browser.

Wisp runs a small web server on your PC. Open the address on your phone (same Wi-Fi),
type the 6-digit PIN shown on your PC once, and your phone stays paired.

Security:
  - Every request needs a secret token that your phone only gets by entering the PIN shown on the PC.
  - The PIN changes every time you open the pairing window, expires after 10 minutes,
    and is replaced after 5 wrong guesses.
  - "Forget all phones" in the pairing window unpairs everything.
  - It's plain HTTP on your home network. Away from home it goes through an encrypted Cloudflare link
    (see tunnel.py) - no ports opened on your router. Or use Tailscale if you prefer.
  - You can also pair by scanning a QR code (a one-time code that expires after 10 minutes).
  - Too many requests with a wrong token from one place get that place blocked for a while.

The phone app is one page (remote_page.html). On your Wi-Fi it's served from here; away from home it's
served from the project's GitHub Pages site and talks to this PC through the secure link.
"""
import hashlib
import hmac
import io
import json
import os
import secrets
import socket
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import background
import focus
import sysplat
import timers

ROOT = Path(__file__).resolve().parent
DEVICES = ROOT / "phone.json"
PAGE = ROOT / "remote_page.html"


# ---------- paired phones ----------
def _load_devices():
    try:
        return json.loads(DEVICES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "devices": []}


def _save_devices(data):
    tmp = DEVICES.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, DEVICES)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def settings():
    """Phone settings + the private channel names (made once, kept in phone.json)."""
    data = _load_devices()
    changed = False
    if not data.get("topic"):
        data["topic"] = "wisp-" + secrets.token_hex(12)       # where the PC posts its current address
        changed = True
    if not data.get("notify_topic"):
        data["notify_topic"] = "wisp-n-" + secrets.token_hex(12)   # notifications sent to your phone
        changed = True
    if changed:
        _save_devices(data)
    return data


def set_option(key, value):
    data = settings()
    data[key] = value
    _save_devices(data)


def is_enabled():
    return _load_devices().get("enabled", False)


def set_enabled(on):
    data = _load_devices()
    data["enabled"] = bool(on)
    _save_devices(data)


def paired_count():
    return len(_load_devices().get("devices", []))


def forget_all():
    data = _load_devices()
    data["devices"] = []
    _save_devices(data)


def local_addresses(port):
    """The addresses your phone can use (your Wi-Fi IP first; Tailscale 100.x addresses too)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))  # no data is sent; this just finds the main network interface
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return [f"http://{ip}:{port}" for ip in ips]


# ---------- PC controls the phone can use ----------
MEDIA_KEYS = sysplat.MEDIA_ACTIONS  # play_pause, next, previous, volume_up, volume_down, mute_pc


_screen_lock = threading.Lock()
_screen_cache = (0.0, 0, None)


def screen_jpeg(width=720, quality=55):
    """The main screen, small and fast, for the live view (shared between quick repeated requests)."""
    global _screen_cache
    from PIL import ImageGrab
    with _screen_lock:
        at, w, data = _screen_cache
        if data is not None and w == width and time.time() - at < 0.25:
            return data
        img = ImageGrab.grab()   # main screen
        if img.width > width:
            img = img.resize((width, int(img.height * width / img.width)))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=quality)
        _screen_cache = (time.time(), width, buf.getvalue())
        return _screen_cache[2]


def decode_audio(data):
    """Audio recorded on the phone (webm/opus or mp4/aac) -> 16 kHz mono float32 for speech-to-text."""
    import av
    import numpy as np
    out = []
    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
        for frame in container.decode(stream):
            for f in resampler.resample(frame):
                out.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            out.append(f.to_ndarray().reshape(-1))
    return np.concatenate(out).astype("float32") if out else np.zeros(0, dtype="float32")


def screenshot_jpeg(max_width=1600):
    from PIL import Image
    tmp = Path(tempfile.gettempdir()) / "wisp_phone_shot.png"
    sysplat.screenshot(tmp)
    img = Image.open(tmp)
    if img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=70)
    return buf.getvalue()


class PhoneRemote:
    def __init__(self, assistant, port=8765):
        self.a = assistant
        self.port = port
        self.server = None
        self.events = []          # (seq, kind, text, time) - recent things that happened
        self.seq = 0
        self.cond = threading.Condition()
        self.pin = None
        self.pin_expires = 0.0
        self.pin_tries = 0
        self.codes = {}           # one-time QR pairing codes -> expiry time
        self.fails = {}           # client -> (count, first failure time): blocks token guessing
        self.tunnel = None
        assistant.add_listener(self._on_event)

    # ---------- lifecycle ----------
    def start(self):
        if self.server:
            return True
        remote = self

        class Handler(RemoteHandler):
            pass
        Handler.remote = remote
        try:
            self.server = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        except OSError as exc:
            self.a.emit("info", f"Phone remote couldn't start on port {self.port} ({exc}).")
            return False
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    def stop(self):
        self.stop_away()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    # ---------- away from home ----------
    def start_away(self, on_status=None):
        import tunnel
        if not self.start():
            return False
        if self.tunnel is None:
            self.tunnel = tunnel.Tunnel(self.port, settings()["topic"], on_status)
        self.tunnel.start()
        return True

    def stop_away(self):
        if self.tunnel:
            self.tunnel.stop()

    @property
    def away_url(self):
        return self.tunnel.url if self.tunnel else None

    @property
    def running(self):
        return self.server is not None

    # ---------- pairing ----------
    def new_pin(self):
        self.pin = f"{secrets.randbelow(1_000_000):06d}"
        self.pin_expires = time.time() + 600
        self.pin_tries = 0
        return self.pin

    def new_pair_code(self):
        """A one-time code for the QR code (much longer than a PIN, so it's safe to use over the internet)."""
        code = secrets.token_urlsafe(18)
        now = time.time()
        self.codes = {c: t for c, t in self.codes.items() if t > now}
        self.codes[code] = now + 600
        return code

    def pair_link(self, away=False):
        """What the QR code opens on the phone."""
        from app_info import PHONE_APP_URL
        code = self.new_pair_code()
        if away and self.away_url:
            from urllib.parse import quote
            return f"{PHONE_APP_URL}#pair={code}&t={settings()['topic']}&u={quote(self.away_url, safe='')}"
        lan = local_addresses(self.port)
        return f"{lan[0] if lan else 'http://localhost:%d' % self.port}/#pair={code}"

    def pair(self, pin, name, code=None):
        if code:
            expires = self.codes.pop(str(code), 0)
            if time.time() > expires:
                return None, "That QR code has expired. Show a new one on your PC."
            return self._issue_token(name)
        if not self.pin or time.time() > self.pin_expires:
            return None, "No pairing code is active. On your PC: right-click the orb > Connect phone."
        self.pin_tries += 1
        if not hmac.compare_digest(str(pin).strip(), self.pin):
            if self.pin_tries >= 5:
                self.new_pin()
                self.a.emit("info", "Too many wrong phone PINs - a new PIN has been made.")
                return None, "Too many wrong tries. Check the new PIN on your PC."
            return None, "Wrong PIN."
        self.pin = None  # one PIN, one phone
        return self._issue_token(name)

    def _issue_token(self, name):
        token = secrets.token_urlsafe(32)
        data = _load_devices()
        data.setdefault("devices", []).append({"name": (name or "Phone")[:40], "hash": _hash(token),
                                               "paired": time.strftime("%Y-%m-%d %H:%M")})
        _save_devices(data)
        from i18n import L
        self.a.emit("info", L(f"Phone paired: {name or 'Phone'}.", f"手机已配对：{name or '手机'}。"))
        return token, None

    def check_token(self, token, client="?"):
        """Is this a paired phone? Too many wrong tokens from one client blocks it for 15 minutes."""
        count, first = self.fails.get(client, (0, 0.0))
        if count >= 20 and time.time() - first < 900:
            return False
        h = _hash(token or "")
        ok = bool(token) and any(hmac.compare_digest(h, d["hash"]) for d in _load_devices().get("devices", []))
        if not ok:
            if time.time() - first > 900:
                count, first = 0, time.time()
            self.fails[client] = (count + 1, first)
        return ok

    # ---------- events for the phone ----------
    def _on_event(self, kind, text):
        if kind not in ("user", "tool", "reply", "say", "alert", "status", "error", "info"):
            return
        if kind == "info" and (text.startswith("took ") or "Loading speech" in text):
            return
        with self.cond:
            self.seq += 1
            self.events.append((self.seq, kind, text, time.time()))
            self.events = self.events[-300:]
            self.cond.notify_all()

    def events_after(self, after, wait=25.0):
        deadline = time.time() + wait
        with self.cond:
            while True:
                new = [e for e in self.events if e[0] > after]
                if new or time.time() >= deadline:
                    return [{"seq": s, "kind": k, "text": t, "time": tm} for s, k, t, tm in new], self.seq
                self.cond.wait(timeout=deadline - time.time())

    # ---------- state + actions ----------
    def state(self):
        a = self.a
        status = "listening" if a.is_listening else ("speaking" if a.is_speaking else
                                                     ("thinking" if a.busy.is_set() else "ready"))
        items = [{"id": i["id"], "kind": i["kind"], "label": i["label"] or _kind_name(i["kind"]),
                  "left": max(0, i["due"] - time.time()), "when": timers.say_time(i["due"])}
                 for i in timers.upcoming()[:8]]
        jobs = [{"id": j["id"], "task": j["task"], "status": j["status"], "say": j.get("say", ""),
                 "result": (j.get("result") or j.get("error") or "")[:4000]} for j in background.list_jobs(limit=8)]
        import routines
        import i18n
        return {"status": status, "muted": a.muted, "timers": items, "jobs": jobs, "lang": i18n.LANG,
                "screen": a.cfg.get("phone_screen", True), "version": __import__("app_info").VERSION,
                "session": focus.session_text(), "focus_today": int(focus.focus_minutes_today()),
                "routines": [{"name": n, "says": routines.describe(r)} for n, r in routines.load().items()][:20], "speak_on_pc": a.cfg.get("phone_replies_on_pc", False),
                "name": a.cfg.get("user_name", ""), "accent": a.cfg.get("accent_colour", "#38d6ff"),
                "seq": self.seq}

    def action(self, name, value=None):
        a = self.a
        if name in MEDIA_KEYS:
            sysplat.media(name)
        elif name == "lock_pc":
            sysplat.lock_screen()
        elif name == "stop":
            a.stop()
        elif name == "new_chat":
            a.new_chat()
        elif name == "mute":
            a.set_muted(bool(value))
        elif name == "speak_on_pc":
            a.cfg["phone_replies_on_pc"] = bool(value)
        elif name == "open_hud" and a.ui_action:
            a.ui_action("hud")
        elif name == "cancel_timer":
            timers.cancel(value if value is not None else "all")
        elif name == "focus_session":
            focus.start_session(float(value or 25), 5, 4)
        elif name == "stop_session":
            focus.stop_session()
        elif name == "routine":
            import routines
            found = routines.load().get(str(value))
            if not found:
                return False
            a.submit(str(value), source="phone")  # runs through the normal pipeline (triggers include the name)
        else:
            return False
        return True


def _kind_name(kind):
    from i18n import L
    return {"timer": L("Timer", "计时器"), "alarm": L("Alarm", "闹钟"), "reminder": L("Reminder", "提醒")}.get(kind, kind)


class RemoteHandler(BaseHTTPRequestHandler):
    remote = None  # set when the server starts
    server_version = "Wisp"

    def log_message(self, *args):  # keep the log quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        """The phone app on GitHub Pages (away from home) is a different website, so allow it explicitly."""
        from app_info import PHONE_APP_URL
        origin = self.headers.get("Origin") or ""
        allowed = "/".join(PHONE_APP_URL.split("/")[:3])
        if origin and origin == allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _via_tunnel(self):
        """Came in through the away-from-home link (cloudflared connects from this computer)."""
        return self.client_address[0] in ("127.0.0.1", "::1") and bool(self.headers.get("CF-Connecting-IP"))

    def _client(self):
        # only trust Cloudflare's "real address" header when the request really came through the tunnel
        return self.headers.get("CF-Connecting-IP") if self._via_tunnel() else self.client_address[0]

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 64_000:
            return None
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def _authed(self):
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if self.remote.check_token(token, self._client()):
            return True
        self._send(401, {"error": "not paired"})
        return False

    def do_GET(self):
        url = urlparse(self.path)
        r = self.remote
        if url.path in ("/", "/index.html"):
            try:
                page = PAGE.read_bytes()
                import i18n
                if i18n.LANG == "zh":
                    page = page.replace(b'<html lang="en">', b'<html lang="zh-CN">', 1)
                return self._send(200, page, "text/html; charset=utf-8")
            except OSError:
                return self._send(500, "remote_page.html is missing", "text/plain")
        if url.path == "/manifest.json":
            return self._send(200, {"name": "Wisp", "short_name": "Wisp", "start_url": "/", "scope": "/",
                                    "display": "standalone", "background_color": "#05080c",
                                    "theme_color": "#05080c",
                                    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]})
        if url.path == "/icon.svg":
            accent = r.a.cfg.get("accent_colour", "#38d6ff")
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" '
                   f'fill="#05080c"/><circle cx="32" cy="32" r="22" fill="none" stroke="{accent}" stroke-width="4"/>'
                   f'<circle cx="32" cy="32" r="11" fill="{accent}"/></svg>')
            return self._send(200, svg, "image/svg+xml")
        if not self._authed():
            return
        if url.path == "/api/state":
            return self._send(200, r.state())
        if url.path == "/api/events":
            q = parse_qs(url.query)
            after = int(q.get("after", ["0"])[0])
            wait = min(25.0, float(q.get("wait", ["25"])[0]))
            events, seq = r.events_after(after, wait)
            return self._send(200, {"events": events, "seq": seq})
        if url.path == "/api/screen":
            if not r.a.cfg.get("phone_screen", True):
                return self._send(403, {"error": "Screen view is turned off in Wisp's settings."})
            q = parse_qs(url.query)
            width = max(240, min(1600, int(q.get("w", ["720"])[0])))
            try:
                return self._send(200, screen_jpeg(width), "image/jpeg")
            except Exception as exc:
                return self._send(500, {"error": f"Couldn't see the screen: {exc}"})
        if url.path == "/api/screenshot":
            try:
                return self._send(200, screenshot_jpeg(), "image/jpeg")
            except Exception as exc:
                return self._send(500, {"error": f"Couldn't take a screenshot: {exc}"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        r = self.remote
        if url.path == "/api/voice":   # raw audio, not JSON
            return self._voice()
        body = self._body()
        if body is None:
            return self._send(400, {"error": "bad request"})
        if url.path == "/api/pair":
            if self._via_tunnel() and not body.get("code"):
                # over the internet only the long one-time QR code is accepted, never the short PIN
                return self._send(403, {"error": "Scan the QR code in Wisp > Phone to pair."})
            token, err = r.pair(body.get("pin", ""), body.get("name", ""), code=body.get("code"))
            return self._send(200 if token else 403, {"token": token} if token else {"error": err})
        if not self._authed():
            return
        if url.path == "/api/ask":
            text = str(body.get("text", "")).strip()[:4000]
            if text:
                import telemetry
                telemetry.feature("phone_remote")
                r.a.submit(text, source="phone")
            return self._send(200, {"ok": bool(text)})
        if url.path == "/api/feedback":
            import feedback
            message = str(body.get("message", "")).strip()
            if not message:
                return self._send(400, {"error": "empty"})
            result = feedback.send(str(body.get("kind", "idea")), message, body.get("rating"), str(body.get("email", "")))
            return self._send(200, {"result": result})
        if url.path == "/api/input":
            if not r.a.cfg.get("phone_screen", True):
                return self._send(403, {"error": "Screen control is turned off in Wisp's settings."})
            import remote_input
            try:
                ok = remote_input.handle(body)
            except Exception as exc:
                return self._send(500, {"error": f"Couldn't control the mouse/keyboard: {exc}"})
            return self._send(200 if ok else 400, {"ok": ok})
        if url.path == "/api/action":
            ok = r.action(str(body.get("action", "")), body.get("value"))
            return self._send(200 if ok else 400, {"ok": ok})
        self._send(404, {"error": "not found"})

    def _voice(self):
        """Hold-to-talk on the phone: the recording is turned into text here, then run like a typed request."""
        if not self._authed():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= 15_000_000:
            return self._send(400, {"error": "recording missing or too long"})
        data = self.rfile.read(length)
        try:
            text = self.remote.a.transcribe_audio(decode_audio(data))
        except Exception as exc:
            return self._send(500, {"error": f"Couldn't understand the recording: {exc}"})
        if text:
            import telemetry
            telemetry.feature("phone_voice")
            self.remote.a.submit(text, source="phone")
        return self._send(200, {"text": text})
