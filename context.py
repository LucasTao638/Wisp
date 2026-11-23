"""Gives Claude extra context when you mention your screen or clipboard.

  "what's on my screen?"  "explain this error"  "summarise this page"  "what am I looking at?"
      -> takes a screenshot (Wisp's own windows are hidden from it) and tells Claude where it is
  "summarise what I copied"  "translate my clipboard"  "fix the grammar in what I copied"
      -> passes along the text (or image) you copied
"""
import os
import re
import time
from pathlib import Path

import sysplat

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
    from PIL import Image
    SHOTS.mkdir(parents=True, exist_ok=True)
    raw = SHOTS / "_raw.png"
    with screenshot_guard():  # on Mac, Wisp's own windows are hidden for a moment
        sysplat.screenshot(raw)
    img = Image.open(raw)
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
    """Keep a window out of screenshots (Windows). On Mac, screenshot_guard hides Wisp briefly instead."""
    sysplat.hide_from_screenshots(tk_window)


class _NoGuard:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# The UI replaces this on Mac with something that hides Wisp's windows while the screenshot is taken.
screenshot_guard = _NoGuard


# ---------- clipboard ----------
def clipboard_text():
    return sysplat.clipboard_text()


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
                   f"[If they want a result they can paste, put it on their clipboard: {sysplat.clipboard_hint()}, " \
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
