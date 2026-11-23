"""Global hotkeys that work while other apps are focused.

Windows: the 'keyboard' package.   macOS: 'pynput' (needs Accessibility / Input Monitoring permission:
System Settings > Privacy & Security - macOS asks the first time).

Key names use the same style everywhere: "f9", "alt_r" (Right Option/Alt), "ctrl+shift+space", "ctrl+alt+j".
"""
import sys
import threading

IS_MAC = sys.platform == "darwin"

_listener = None
_holds = {}      # key name -> (on_press, on_release)
_combos = {}     # "ctrl+shift+space" -> fn
_down = set()
_lock = threading.Lock()
_pressed_combo = set()


def _norm(name):
    name = name.lower().strip()
    return {"option": "alt", "opt": "alt", "right option": "alt_r", "right alt": "alt_r", "command": "cmd",
            "control": "ctrl", "return": "enter", "esc": "escape"}.get(name, name)


# ---------- Windows ----------
def _win_hold(key, on_press, on_release):
    import keyboard
    keyboard.on_press_key(key, lambda _: on_press())
    keyboard.on_release_key(key, lambda _: on_release())


def _win_combo(combo, fn):
    import keyboard
    keyboard.add_hotkey(combo, fn)


# ---------- macOS ----------
# Mac physical key codes -> letters/digits. Holding Option/Ctrl changes the *character* a key types
# (Option+J types "∆"), so letters are matched by which key it is instead.
_MAC_VK = {0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v", 11: "b", 12: "q",
           13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6", 23: "5",
           25: "9", 26: "7", 28: "8", 29: "0", 31: "o", 32: "u", 34: "i", 35: "p", 37: "l", 38: "j", 40: "k",
           45: "n", 46: "m"}


def _key_name(key):
    """pynput key -> our name."""
    from pynput import keyboard as kb
    if isinstance(key, kb.KeyCode):
        if key.vk in _MAC_VK:
            return _MAC_VK[key.vk]
        return (key.char or "").lower() if key.char else f"vk{key.vk}"
    name = key.name  # e.g. "alt_r", "f9", "space", "cmd", "ctrl_l"
    return name


def _mods_of(name):
    for mod in ("ctrl", "alt", "shift", "cmd"):
        if name == mod or name.startswith(mod + "_"):
            return mod
    return None


def _ensure_mac_listener():
    global _listener
    if _listener:
        return
    from pynput import keyboard as kb

    def pressed(key):
        name = _key_name(key)
        with _lock:
            _down.add(name)
            mods = {_mods_of(n) for n in _down if _mods_of(n)}
        if name in _holds:
            _holds[name][0]()
        for combo, fn in _combos.items():
            parts = [_norm(p) for p in combo.split("+")]
            want_mods = {p for p in parts if p in ("ctrl", "alt", "shift", "cmd")}
            main = [p for p in parts if p not in want_mods]
            if main and main[0] == name and want_mods == mods and combo not in _pressed_combo:
                _pressed_combo.add(combo)
                threading.Thread(target=fn, daemon=True).start()

    def released(key):
        name = _key_name(key)
        with _lock:
            _down.discard(name)
        _pressed_combo.clear()
        if name in _holds:
            _holds[name][1]()

    _listener = kb.Listener(on_press=pressed, on_release=released)
    _listener.daemon = True
    _listener.start()


# ---------- public ----------
def on_hold(key, on_press, on_release):
    """Call on_press when the key goes down and on_release when it comes up (push-to-talk)."""
    key = _norm(key)
    if IS_MAC:
        _holds[key] = (on_press, on_release)
        _ensure_mac_listener()
    else:
        _win_hold(key, on_press, on_release)


def add_hotkey(combo, fn):
    combo = "+".join(_norm(p) for p in combo.split("+"))
    if IS_MAC:
        _combos[combo] = fn
        _ensure_mac_listener()
    else:
        _win_combo(combo, fn)


def watch_keys(names, fn):
    """Call fn() whenever one of these keys is pressed (used for small things like 'any scroll key')."""
    if IS_MAC:
        for n in names:
            _holds.setdefault(_norm(n), (fn, lambda: None))
        _ensure_mac_listener()
    else:
        import keyboard
        keyboard.on_press(lambda e: e.name in names and fn())


def label(key):
    """A friendly name for showing in the UI."""
    key = _norm(key)
    nice = {"alt_r": "Right Option" if IS_MAC else "Right Alt", "alt": "Option" if IS_MAC else "Alt",
            "cmd": "Cmd", "ctrl": "Ctrl", "shift": "Shift", "space": "Space"}
    return " + ".join(nice.get(p, p.upper() if len(p) <= 3 else p.title()) for p in key.split("+"))
