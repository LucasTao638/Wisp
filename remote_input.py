"""Mouse and keyboard on this computer, driven from the phone's live screen view.

Coordinates arrive as fractions of the screen (0..1), so the phone doesn't need to know the resolution.
Uses pynput (works on Windows and Mac; on a Mac, Wisp needs the Accessibility permission).
"""
import sys
import threading

_lock = threading.Lock()
SCREEN_POINTS = None   # (width, height) in the units the mouse uses - set by the app at startup (needed on Mac)

KEYS = {"enter": "enter", "backspace": "backspace", "esc": "esc", "tab": "tab", "space": "space",
        "up": "up", "down": "down", "left": "left", "right": "right", "delete": "delete",
        "home": "home", "end": "end", "page_up": "page_up", "page_down": "page_down",
        "win": "cmd", "cmd": "cmd"}


def _screen_size():
    """Size of the main screen in mouse units."""
    if SCREEN_POINTS:
        return SCREEN_POINTS
    if sys.platform == "win32":
        import ctypes
        u = ctypes.windll.user32
        return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    return 1440, 900


def handle(cmd):
    """cmd: {"type": "click", "x": 0.5, "y": 0.5, "button": "left"|"right", "double": false}
            {"type": "scroll", "dy": -3}      (negative = down)
            {"type": "type", "text": "hello"}
            {"type": "key", "key": "enter", "mods": ["ctrl"]}"""
    from pynput import keyboard, mouse
    kind = cmd.get("type")
    with _lock:
        if kind == "click":
            w, h = _screen_size()
            x = max(0.0, min(1.0, float(cmd.get("x", 0)))) * (w - 1)
            y = max(0.0, min(1.0, float(cmd.get("y", 0)))) * (h - 1)
            m = mouse.Controller()
            m.position = (int(x), int(y))
            button = mouse.Button.right if cmd.get("button") == "right" else mouse.Button.left
            m.click(button, 2 if cmd.get("double") else 1)
        elif kind == "scroll":
            mouse.Controller().scroll(0, int(cmd.get("dy", 0)))
        elif kind == "type":
            keyboard.Controller().type(str(cmd.get("text", ""))[:2000])
        elif kind == "key":
            kb = keyboard.Controller()
            name = KEYS.get(str(cmd.get("key", "")).lower())
            if not name:
                return False
            mods = [getattr(keyboard.Key, m) for m in cmd.get("mods", []) if m in ("ctrl", "shift", "alt", "cmd")]
            for m in mods:
                kb.press(m)
            kb.tap(getattr(keyboard.Key, name))
            for m in reversed(mods):
                kb.release(m)
        else:
            return False
    return True
