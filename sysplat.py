"""Everything that works differently on Windows and macOS, in one place.

The rest of Wisp calls these functions and doesn't need to care which system it's on.
"""
import os
import re
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
OS_NAME = "Windows" if IS_WIN else "macOS" if IS_MAC else "Linux"

NO_WINDOW = 0x08000000 if IS_WIN else 0                       # CREATE_NO_WINDOW
DETACHED = (0x00000008 | 0x00000200) if IS_WIN else 0         # DETACHED_PROCESS | NEW_PROCESS_GROUP


def popen_detached(cmd, cwd=None):
    """Start a program that keeps running after Wisp closes."""
    kwargs = {"creationflags": DETACHED} if IS_WIN else {"start_new_session": True}
    return subprocess.Popen(cmd, cwd=cwd, close_fds=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)


def python_gui_exe():
    """The Python to start Wisp's window with (pythonw on Windows, so there's no console)."""
    exe = sys.executable
    if IS_WIN:
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        return w if os.path.exists(w) else exe
    return exe


def _osascript(script, timeout=10):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------- opening things ----------
def open_target(target):
    """Open a file, folder, website, protocol link (steam:, spotify:) or app."""
    target = os.path.expandvars(os.path.expanduser(str(target)))
    if IS_WIN:
        os.startfile(target)
    elif IS_MAC:
        is_path_or_link = ("://" in target or target.endswith(":") or os.path.exists(target) or "/" in target
                           or bool(re.match(r"^[a-zA-Z][\w.+-]+:\S", target)))  # e.g. x-apple.systempreferences:...
        if is_path_or_link:
            subprocess.run(["open", target if not target.endswith(":") else target + "//"], check=True,
                           capture_output=True)
        else:
            subprocess.run(["open", "-a", target], check=True, capture_output=True)
    else:
        subprocess.Popen(["xdg-open", target])


def close_app(name):
    """Politely close an app (by program name)."""
    if IS_WIN:
        exe = name.removesuffix(".exe") + ".exe"
        subprocess.run(["taskkill", "/IM", exe], capture_output=True, creationflags=NO_WINDOW)
    elif IS_MAC:
        _osascript(f"quit app {_quote(name)}")


def show_desktop():
    if IS_WIN:
        import ctypes
        u = ctypes.windll.user32
        u.keybd_event(0x5B, 0, 0, 0)
        u.keybd_event(0x44, 0, 0, 0)
        u.keybd_event(0x44, 0, 2, 0)
        u.keybd_event(0x5B, 0, 2, 0)
    elif IS_MAC:  # hide every app except Finder
        _osascript('tell application "System Events" to set visible of (every process whose visible is true '
                   'and name is not "Finder") to false')


def lock_screen():
    if IS_WIN:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    elif IS_MAC:  # Ctrl+Cmd+Q
        _osascript('tell application "System Events" to keystroke "q" using {control down, command down}')


# ---------- media and volume ----------
MEDIA_ACTIONS = ("play_pause", "next", "previous", "volume_up", "volume_down", "mute_pc")
_WIN_KEYS = {"play_pause": (0xB3, 1), "next": (0xB0, 1), "previous": (0xB1, 1),
             "volume_up": (0xAF, 3), "volume_down": (0xAE, 3), "mute_pc": (0xAD, 1)}


def media(action, times=None):
    """play_pause / next / previous / volume_up / volume_down / mute_pc."""
    if action not in MEDIA_ACTIONS:
        return False
    if IS_WIN:
        import ctypes
        vk, default = _WIN_KEYS[action]
        for _ in range(times or default):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        return True
    if IS_MAC:
        if action in ("volume_up", "volume_down"):
            step = 6 * (times or 1) * (1 if action == "volume_up" else -1)
            _osascript(f"set volume output volume ((output volume of (get volume settings)) + {step})")
        elif action == "mute_pc":
            _osascript("set volume output muted (not (output muted of (get volume settings)))")
        else:
            verb = {"play_pause": "playpause", "next": "next track", "previous": "previous track"}[action]
            # whichever music app is running: Spotify first, then Apple Music
            _osascript(f'if application "Spotify" is running then\n tell application "Spotify" to {verb}\n'
                       f'else\n tell application "Music" to {verb}\nend if')
        return True
    return False


# ---------- notifications and sounds ----------
def notify(title, message):
    try:
        if IS_WIN:
            from win11toast import notify as toast
            toast(title, message)
        elif IS_MAC:
            _osascript(f"display notification {_quote(message)} with title {_quote(title)}")
        else:
            print(f"[{title}] {message}")
    except Exception:
        print(f"[{title}] {message}")


def chime(kind="alert", repeats=1):
    """'alert' (timers etc.), 'wake' (heard the wake phrase) or 'blip' (mic reopened). Doesn't block."""
    def play():
        for _ in range(repeats):
            if IS_WIN:
                import winsound
                notes = {"alert": ((880, 120), (1175, 120), (1568, 220)), "wake": ((1175, 90),),
                         "blip": ((988, 70),)}[kind]
                for freq, ms in notes:
                    winsound.Beep(freq, ms)
            elif IS_MAC:
                sound = {"alert": "Glass", "wake": "Tink", "blip": "Pop"}[kind]
                subprocess.run(["afplay", f"/System/Library/Sounds/{sound}.aiff"], capture_output=True)
            time.sleep(0.15)
    threading.Thread(target=play, daemon=True).start()


# ---------- clipboard and screenshots ----------
def clipboard_text():
    if IS_MAC:
        try:
            return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout
        except Exception:
            return None
    if not IS_WIN:
        return None
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return None
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def clipboard_hint():
    """How Claude should put a result on the clipboard, on this system."""
    if IS_MAC:
        return "pipe it into pbcopy (e.g. printf '%s' 'text' | pbcopy, or pbcopy < file)"
    return ("run PowerShell Set-Clipboard -Value '...' (for long text write it to a file in output/ and use "
            "Get-Content file -Raw | Set-Clipboard)")


def screenshot(path):
    """Save a screenshot of all screens to path."""
    if IS_MAC:
        subprocess.run(["screencapture", "-x", str(path)], check=True, capture_output=True, timeout=15)
        return
    from PIL import ImageGrab
    ImageGrab.grab(all_screens=True).save(path)


def hide_from_screenshots(tk_window):
    """Windows can exclude a window from screenshots; on Mac, Wisp hides its windows around a capture instead."""
    if not IS_WIN:
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetAncestor(tk_window.winfo_id(), 2) or tk_window.winfo_id()
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)  # WDA_EXCLUDEFROMCAPTURE
    except Exception:
        pass


# ---------- audio playback (for the neural voice) ----------
class AudioPlayer:
    """Plays an mp3 and can be stopped. Windows: built-in MCI. Mac: afplay."""

    def __init__(self, path):
        self.path, self.proc, self.alias = str(path), None, None

    def play(self, should_stop):
        """Blocks until finished or should_stop() returns True."""
        if IS_WIN:
            import ctypes
            buf = ctypes.create_unicode_buffer(256)
            mci = lambda cmd: (ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, 0), buf.value)[1]
            alias = f"wisp{threading.get_ident() % 100000}_{int(time.time() * 1000) % 100000}"
            mci(f'open "{self.path}" type mpegvideo alias {alias}')
            mci(f"play {alias}")
            time.sleep(0.05)
            while not should_stop() and mci(f"status {alias} mode") == "playing":
                time.sleep(0.03)
            mci(f"stop {alias}")
            mci(f"close {alias}")
            return
        player = ["afplay", self.path] if IS_MAC else ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", self.path]
        try:
            self.proc = subprocess.Popen(player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            return
        while self.proc.poll() is None:
            if should_stop():
                self.proc.kill()
                return
            time.sleep(0.03)


def system_voice_command(text, voice_name="", rate=1):
    """The built-in offline voice: Windows SAPI or macOS 'say'. Returns (command, stdin_text)."""
    if IS_MAC:
        cmd = ["say"]
        if voice_name:
            cmd += ["-v", voice_name]
        cmd += ["-r", str(int(185 + 15 * int(rate)))]
        return cmd + ["--", text], None
    select = f"try {{ $s.SelectVoice('{voice_name}') }} catch {{}};" if voice_name else ""
    script = ("Add-Type -AssemblyName System.Speech;$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
              f"$s.Rate = {int(rate)};{select}$s.Speak([Console]::In.ReadToEnd())")
    return ["powershell", "-NoProfile", "-Command", script], text


# ---------- starting Wisp itself ----------
MAC_APP = os.path.expanduser("~/Applications/Wisp.app")


def launch_wisp(root, startup=False):
    """Start Wisp in the background (used for restarts and updates).
    On Mac it goes through Wisp.app, so macOS permissions (microphone etc.) stay attached to "Wisp"."""
    args = ["--startup"] if startup else []
    if IS_MAC and os.path.isdir(MAC_APP):
        return popen_detached(["open", "-n", "-a", MAC_APP] + (["--args"] + args if args else []))
    return popen_detached([python_gui_exe(), os.path.join(str(root), "app.py")] + args, cwd=str(root))
