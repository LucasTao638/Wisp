"""Gives Claude extra context when you mention your screen or clipboard.

  "what's on my screen?"  "explain this error"  "summarise this page"  "what am I looking at?"
      -> takes a screenshot (Wisp's own windows are hidden from it) and tells Claude where it is
  "summarise what I copied"  "translate my clipboard"  "fix the grammar in what I copied"
      -> passes along the text (or image) you copied
"""
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHOTS = ROOT / "workspace" / "output" / "screens"

_SCREEN = re.compile(
    r"\b(my screen|the screen|on screen|on my monitor|this screen|screenshot|what am i looking at|"
    r"what('?s| is) (this|that)( (error|page|thing|window|message|code|word|picture|image))?\s*$|"
    r"what does (this|that) (mean|say|error mean)|look at (this|my)|see (this|my screen)|"
    r"this (error|page|window|message|website|site|article|video|code|question|problem|tab)|"
    r"(explain|summari[sz]e|read|translate|solve|answer) (this|what'?s on)|help me with this)\b")
_CLIPBOARD = re.compile(r"\b(clipboard|what i('?ve| have| just)? copied|copied (text|image|this)|"
                        r"the (text|thing|stuff) i copied|i just copied)\b")


def wants_screen(text):
    t = re.sub(r"[?!.]+$", "", text.lower().strip())
    return bool(_SCREEN.search(t)) and not wants_clipboard(text)


def wants_clipboard(text):
    return bool(_CLIPBOARD.search(text.lower()))


# ---------- screenshots ----------
def take_screenshot(max_width=1800):
    """Saves a screenshot of all monitors and returns its path."""
    from PIL import ImageGrab
    SHOTS.mkdir(parents=True, exist_ok=True)
    img = ImageGrab.grab(all_screens=True)
    if img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)))
    path = SHOTS / f"screen_{time.strftime('%Y%m%d_%H%M%S')}.png"
    img.save(path)
    old = sorted(SHOTS.glob("screen_*.png"))[:-20]  # keep the last 20
    for f in old:
        try:
            f.unlink()
        except OSError:
            pass
    return path


def hide_from_screenshots(tk_window):
    """Stop a window appearing in screenshots and screen recordings (Windows 10 2004+)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetAncestor(tk_window.winfo_id(), 2) or tk_window.winfo_id()
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)  # WDA_EXCLUDEFROMCAPTURE
    except Exception:
        pass


# ---------- clipboard ----------
def clipboard_text():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    for _ in range(5):  # another app may have the clipboard open for a moment
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


def clipboard_image():
    """If an image is copied, save it and return the path."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
    except Exception:
        return None
    if img is None or isinstance(img, list):
        return None
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"clipboard_{time.strftime('%Y%m%d_%H%M%S')}.png"
    img.save(path)
    return path


# ---------- add the context to a request ----------
def enrich(text):
    """Returns (prompt for Claude, short note for the UI or None)."""
    if wants_clipboard(text):
        clip = clipboard_text()
        if clip and clip.strip():
            clip = clip.strip()
            cut = len(clip) > 30000
            clip = clip[:30000]
            note = f"[The user copied this text to their clipboard{' (cut off, it was very long)' if cut else ''}:]\n" \
                   f"<clipboard>\n{clip}\n</clipboard>\n" \
                   "[If they want a result they can paste, put it on their clipboard with PowerShell Set-Clipboard " \
                   "and say you've done it.]\n\n"
            return note + text, "Reading your clipboard…"
        image = clipboard_image()
        if image:
            rel = os.path.relpath(image, ROOT / "workspace")
            return f"[The user copied an image. It's saved at {rel} - open it with the Read tool.]\n\n{text}", \
                "Looking at the image you copied…"
        return f"[The user mentioned their clipboard, but it's empty.]\n\n{text}", None
    if wants_screen(text):
        try:
            shot = take_screenshot()
        except Exception as exc:
            return f"[The user is asking about their screen, but the screenshot failed: {exc}]\n\n{text}", None
        rel = os.path.relpath(shot, ROOT / "workspace")
        return (f"[The user is asking about what's on their screen. A screenshot was just taken and saved at {rel} - "
                f"open it with the Read tool and look at it before answering. Wisp's own windows are hidden "
                f"from it.]\n\n{text}"), "Looking at your screen…"
    return text, None
