"""Away-from-home phone remote: a secure https link to Wisp's phone remote, with nothing to set up.

How it works:
  1. Wisp runs Cloudflare's free "quick tunnel" (cloudflared, downloaded the first time). It gives a random
     https://….trycloudflare.com address that reaches the phone remote on this computer - no account,
     no router settings, encrypted all the way.
  2. That address changes every time Wisp starts, so Wisp posts the current one to a private, random
     channel on ntfy.sh (a free notification service). The phone app looks there to find your PC.
  3. Every request still needs the secret token your phone got when you paired it (scan the QR code).
"""
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "bin"
NTFY = "https://ntfy.sh"
RELEASES = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _ssl():
    try:
        import certifi  # comes with edge-tts; Python on a Mac doesn't find the system certificates by itself
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _download(url, dest, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "Wisp"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def cloudflared_path():
    name = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"
    return shutil.which("cloudflared") or str(BIN / name)


def ensure_cloudflared(on_progress=None):
    """Download cloudflared (Cloudflare's official tunnel program) into Wisp's bin folder if needed."""
    path = Path(cloudflared_path())
    if path.exists():
        return str(path)
    BIN.mkdir(exist_ok=True)
    if on_progress:
        on_progress("Downloading Cloudflare's tunnel program (about 20 MB, once)…")
    if sys.platform == "win32":
        _download(RELEASES + "cloudflared-windows-amd64.exe", path)
    elif sys.platform == "darwin":
        arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "amd64"
        tgz = BIN / "cloudflared.tgz"
        _download(RELEASES + f"cloudflared-darwin-{arch}.tgz", tgz)
        with tarfile.open(tgz) as t:
            member = next(m for m in t.getmembers() if m.name.endswith("cloudflared"))
            member.name = "cloudflared"
            t.extract(member, BIN)
        tgz.unlink()
        subprocess.run(["xattr", "-d", "com.apple.quarantine", str(path)], capture_output=True)
    else:
        _download(RELEASES + "cloudflared-linux-amd64", path)
    os.chmod(path, 0o755)
    return str(path)


def publish(topic, message, title=None, click=None, tags=None, timeout=15):
    """Post a message to an ntfy.sh channel. Used for the PC's current address, and for phone notifications."""
    headers = {"User-Agent": "Wisp"}
    if title:
        headers["Title"] = title.encode("utf-8").decode("latin-1", "ignore")
    if click:
        headers["Click"] = click
    if tags:
        headers["Tags"] = tags
    req = urllib.request.Request(f"{NTFY}/{topic}", data=message.encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
        return r.status == 200


class Tunnel:
    """Keeps a quick tunnel running while 'Use away from home' is on, and keeps its address published."""

    REPUBLISH_EVERY = 4 * 3600   # ntfy keeps messages for 12 hours, so post the address again before then

    def __init__(self, port, topic, on_status=None):
        self.port, self.topic = port, topic
        self.on_status = on_status or (lambda text: None)
        self.url = None
        self.proc = None
        self.wanted = False
        self.status = "off"
        self._thread = None

    def start(self):
        if self.wanted:
            return
        self.wanted = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        threading.Thread(target=self.keep_published, daemon=True).start()

    def stop(self):
        self.wanted = False
        self.url = None
        self._set("off")
        proc, self.proc = self.proc, None
        if proc and proc.poll() is None:
            proc.terminate()

    def _set(self, status, detail=""):
        self.status = status
        self.on_status(detail or status)

    def _run(self):
        backoff = 5
        while self.wanted:
            try:
                exe = ensure_cloudflared(lambda t: self._set("starting", t))
                self._set("starting", "Starting the secure link…")
                self.proc = subprocess.Popen(
                    [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                    encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
                for line in self.proc.stdout:
                    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                    if m and m.group(0) != self.url:
                        self.url = m.group(0)
                        self._announce()
                        backoff = 5
                        self._set("on", self.url)
                    if not self.wanted:
                        break
            except Exception as exc:
                self._set("error", f"Secure link problem: {exc}")
            self.url = None
            if self.wanted:
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)

    def _announce(self):
        """Tell the phone app where the PC is now."""
        try:
            publish(self.topic, json.dumps({"wisp": self.url, "at": int(time.time())}))
        except Exception as exc:
            self._set("error", f"Couldn't post the link for your phone: {exc}")

    def keep_published(self):
        """cloudflared is quiet once it's running, so re-post the address every few hours from here."""
        while self.wanted:
            time.sleep(self.REPUBLISH_EVERY)
            if self.url:
                self._announce()
