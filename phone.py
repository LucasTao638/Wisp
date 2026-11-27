"""Wisp's phone tools - Claude runs these to reach your phone.

  python ../phone.py notify "Text" [--title T] [--link URL]   send a notification (iPhone and Android, needs the
                                                               free ntfy app subscribed - see Wisp > Phone)
  python ../phone.py status                                    is an Android phone connected?

Android only (needs "Wireless debugging" connected in Wisp > Phone):
  python ../phone.py screen                 screenshot -> prints the PNG path (open it with Read to see the screen)
  python ../phone.py ui                     what's on screen: buttons/text with tap positions (fast, use this first)
  python ../phone.py tap X Y                tap a point     |  python ../phone.py tap "Text"   tap what says that
  python ../phone.py type "hello"           type into the focused field
  python ../phone.py key back|home|recents|enter|delete|volume_up|volume_down|power|play_pause|next|previous
  python ../phone.py swipe up|down|left|right
  python ../phone.py open "Spotify"         open an app by name (or package)
  python ../phone.py link "https://..."     open a link on the phone
  python ../phone.py apps [filter]          list installed apps
  python ../phone.py battery
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "bin"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
PLATFORM_TOOLS = {"win32": "platform-tools-latest-windows.zip", "darwin": "platform-tools-latest-darwin.zip"}


class PhoneError(Exception):
    pass


# ---------------- notifications (any phone) ----------------
def notify(text, title=None, link=None):
    import remote
    import tunnel
    topic = remote.settings()["notify_topic"]
    tunnel.publish(topic, text, title=title or "Wisp", click=link, tags="crystal_ball")
    return "Sent to your phone."


# ---------------- adb (Android) ----------------
def adb_path():
    found = shutil.which("adb")
    if found:
        return found
    return str(BIN / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb"))


def ensure_adb(on_progress=None):
    """Download Google's platform-tools (adb) into Wisp's bin folder the first time."""
    path = Path(adb_path())
    if path.exists():
        return str(path)
    import tunnel
    name = PLATFORM_TOOLS.get(sys.platform, "platform-tools-latest-linux.zip")
    BIN.mkdir(exist_ok=True)
    if on_progress:
        on_progress("Downloading Android's connection tool (about 7 MB, once)…")
    zpath = BIN / name
    tunnel._download("https://dl.google.com/android/repository/" + name, zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(BIN)
    zpath.unlink()
    if sys.platform != "win32":
        os.chmod(path, 0o755)
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(BIN / "platform-tools")], capture_output=True)
    return str(path)


def adb(*args, timeout=30, check=True, binary=False):
    exe = adb_path()
    if not Path(exe).exists() and not shutil.which("adb"):
        raise PhoneError("No Android phone set up yet. Open Wisp > Phone > Control my Android phone.")
    r = subprocess.run([exe, *args], capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    out = r.stdout if binary else r.stdout.decode("utf-8", "replace")
    if check and r.returncode != 0:
        raise PhoneError((r.stderr.decode("utf-8", "replace") or str(out)).strip()[:300] or "adb failed")
    return out


def pair(host_port, code):
    """Step 1 (once): Wireless debugging > 'Pair device with pairing code' shows an address and a 6-digit code."""
    ensure_adb()
    out = adb("pair", host_port.strip(), code.strip(), timeout=30, check=False)
    if "Successfully paired" not in out:
        raise PhoneError(out.strip() or "Pairing didn't work - check the address and code.")
    _save({"paired": True})
    return out.strip()


def connect(host_port=None):
    """Step 2: connect. Without an address, find the phone on the Wi-Fi by itself (it advertises itself)."""
    ensure_adb()
    if host_port:
        out = adb("connect", host_port.strip(), check=False)
        if "connected" not in out or "failed" in out or "cannot" in out:
            raise PhoneError(out.strip())
        _save({"last": host_port.strip()})
        return out.strip()
    if devices():
        return "Already connected."
    services = adb("mdns", "services", check=False)
    for line in services.splitlines():
        m = re.search(r"_adb-tls-connect\._tcp\.?\s+(\d+\.\d+\.\d+\.\d+:\d+)", line)
        if m:
            out = adb("connect", m.group(1), check=False)
            if "connected" in out and "failed" not in out:
                _save({"last": m.group(1)})
                return out.strip()
    last = _load().get("last")
    if last:
        out = adb("connect", last, check=False)
        if "connected" in out and "failed" not in out:
            return out.strip()
    raise PhoneError("Couldn't find your phone. Is it on the same Wi-Fi, unlocked, with Wireless debugging on?")


def devices():
    out = adb("devices", check=False)
    return [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]


def _serial():
    found = devices()
    if not found:
        connect()
        found = devices()
    if not found:
        raise PhoneError("Your Android phone isn't connected.")
    return found[0]


def shell(*args, timeout=30):
    return adb("-s", _serial(), "shell", *args, timeout=timeout)


def _state_file():
    return ROOT / "android.json"


def _load():
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(update):
    data = _load()
    data.update(update)
    _state_file().write_text(json.dumps(data), encoding="utf-8")


def screen():
    png = adb("-s", _serial(), "exec-out", "screencap", "-p", binary=True, timeout=30)
    path = Path(tempfile.gettempdir()) / f"wisp_phone_{int(time.time())}.png"
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(png))
        if img.height > 1600:   # smaller, so it's quicker for Claude to look at
            img = img.resize((int(img.width * 1600 / img.height), 1600))
        img.save(path)
    except Exception:
        path.write_bytes(png)
    return str(path)


def ui_elements():
    """The visible things you can tap, with their centre points - from Android's own layout dump."""
    shell("uiautomator", "dump", "/sdcard/wisp_ui.xml", timeout=30)
    xml = shell("cat", "/sdcard/wisp_ui.xml")
    items = []
    for node in re.finditer(r"<node [^>]*>", xml):
        attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', node.group(0)))
        label = attrs.get("text") or attrs.get("content-desc") or ""
        clickable = attrs.get("clickable") == "true"
        if not label and not clickable:
            continue
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", attrs.get("bounds", ""))
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        if x2 <= x1 or y2 <= y1:
            continue
        rid = attrs.get("resource-id", "").split("/")[-1]
        items.append({"label": label, "id": rid, "x": (x1 + x2) // 2, "y": (y1 + y2) // 2, "tap": clickable,
                      "editable": attrs.get("class", "").endswith("EditText")})
    return items


def tap(x, y=None):
    if y is None:   # tap by text
        wanted = str(x).lower()
        items = ui_elements()
        match = next((i for i in items if i["label"].lower() == wanted), None) or \
            next((i for i in items if wanted in i["label"].lower()), None)
        if not match:
            raise PhoneError(f"Nothing on screen says “{x}”. Run `phone.py ui` to see what's there.")
        x, y = match["x"], match["y"]
    shell("input", "tap", str(int(float(x))), str(int(float(y))))
    return f"Tapped {int(float(x))},{int(float(y))}."


def type_text(text):
    # adb's input text needs spaces as %s and some characters escaped
    safe = re.sub(r"([\\\"'`$&|;<>()\[\]{}*?!#~])", r"\\\1", text).replace(" ", "%s")
    shell("input", "text", safe)
    return "Typed."


KEYCODES = {"back": 4, "home": 3, "recents": 187, "enter": 66, "delete": 67, "volume_up": 24, "volume_down": 25,
            "power": 26, "play_pause": 85, "next": 87, "previous": 88, "search": 84, "menu": 82, "tab": 61}


def key(name):
    code = KEYCODES.get(name.lower())
    if code is None:
        raise PhoneError(f"Unknown key. Use one of: {', '.join(KEYCODES)}")
    shell("input", "keyevent", str(code))
    return f"Pressed {name}."


def swipe(direction):
    size = re.search(r"(\d+)x(\d+)", shell("wm", "size"))
    w, h = (int(size.group(1)), int(size.group(2))) if size else (1080, 2400)
    cx, cy = w // 2, h // 2
    moves = {"up": (cx, int(h * 0.75), cx, int(h * 0.25)), "down": (cx, int(h * 0.25), cx, int(h * 0.75)),
             "left": (int(w * 0.8), cy, int(w * 0.2), cy), "right": (int(w * 0.2), cy, int(w * 0.8), cy)}
    if direction not in moves:
        raise PhoneError("Swipe up, down, left or right.")
    shell("input", "swipe", *map(str, moves[direction]), "300")
    return f"Swiped {direction}."


def apps(filter_text=""):
    out = shell("pm", "list", "packages", "-3")
    pkgs = sorted(l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("package:"))
    common = ["com.android.chrome", "com.google.android.youtube", "com.google.android.gm", "com.whatsapp",
              "com.spotify.music", "com.android.settings", "com.google.android.apps.maps",
              "com.google.android.calendar", "com.google.android.dialer", "com.google.android.apps.messaging",
              "com.android.camera", "com.google.android.GoogleCamera", "com.google.android.apps.photos"]
    pkgs += [p for p in common if p not in pkgs]
    if filter_text:
        pkgs = [p for p in pkgs if filter_text.lower() in p.lower()]
    return pkgs


def open_app(name):
    target = name.strip()
    if "." not in target:   # a name like "Spotify": find the package
        squashed = re.sub(r"\s+", "", target.lower())
        candidates = [p for p in apps() if squashed in p.lower().replace(".", "")]
        if not candidates:
            raise PhoneError(f"Couldn't find an app called {name}. Try `phone.py apps`.")
        target = min(candidates, key=len)
    out = shell("monkey", "-p", target, "-c", "android.intent.category.LAUNCHER", "1")
    if "No activities found" in out:
        raise PhoneError(f"{target} can't be opened directly.")
    return f"Opened {target}."


def open_link(url):
    shell("am", "start", "-a", "android.intent.action.VIEW", "-d", url)
    return "Opened the link on your phone."


def battery():
    out = shell("dumpsys", "battery")
    level = re.search(r"level: (\d+)", out)
    plugged = re.search(r"(AC|USB|Wireless) powered: true", out)
    return f"Phone battery {level.group(1) if level else '?'}%{' (charging)' if plugged else ''}."


def status():
    lines = []
    try:
        found = devices() if Path(adb_path()).exists() or shutil.which("adb") else []
        lines.append(f"Android phone: {'connected (' + found[0] + ')' if found else 'not connected'}")
    except Exception:
        lines.append("Android phone: not set up")
    lines.append("Notifications: send with `phone.py notify` (works on iPhone and Android with the ntfy app)")
    return "\n".join(lines)


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "notify":
            title = link = None
            words = []
            i = 0
            while i < len(rest):
                if rest[i] == "--title" and i + 1 < len(rest):
                    title, i = rest[i + 1], i + 2
                elif rest[i] == "--link" and i + 1 < len(rest):
                    link, i = rest[i + 1], i + 2
                else:
                    words.append(rest[i])
                    i += 1
            print(notify(" ".join(words), title, link))
        elif cmd == "status":
            print(status())
        elif cmd == "screen":
            print(screen())
        elif cmd == "ui":
            items = ui_elements()
            for it in items:
                flag = " [field]" if it["editable"] else (" [tap]" if it["tap"] else "")
                label = it["label"] or f"({it['id'] or 'unlabelled'})"
                print(f"{it['x']},{it['y']}  {label}{flag}")
            if not items:
                print("(nothing readable on screen - try `phone.py screen`)")
        elif cmd == "tap":
            print(tap(*rest[:2]) if len(rest) >= 2 and rest[0].replace(".", "").isdigit() else tap(" ".join(rest)))
        elif cmd == "type":
            print(type_text(" ".join(rest)))
        elif cmd == "key":
            print(key(rest[0] if rest else ""))
        elif cmd == "swipe":
            print(swipe(rest[0] if rest else ""))
        elif cmd == "open":
            print(open_app(" ".join(rest)))
        elif cmd == "link":
            print(open_link(rest[0]))
        elif cmd == "apps":
            print("\n".join(apps(" ".join(rest))))
        elif cmd == "battery":
            print(battery())
        elif cmd == "connect":
            print(connect(rest[0] if rest else None))
        else:
            print(__doc__)
            return 2
    except PhoneError as exc:
        print(f"Phone: {exc}")
        return 1
    except subprocess.TimeoutExpired:
        print("Phone: it didn't respond in time (is it unlocked and on the same Wi-Fi?)")
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
