"""Instant shortcuts: simple commands handled straight away, without asking Claude.

"open spotify", "launch calculator", "open youtube", "google best pizza near me"
Anything more complicated (e.g. "open notepad and type hello") still goes to Claude.
Add your own apps and websites to APPS and SITES below.
"""
import os
import re
import urllib.parse
import webbrowser

# What you say -> what Windows should run (program name, or a special "app:" link)
APPS = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer",
    "settings": "ms-settings:", "task manager": "taskmgr", "paint": "mspaint",
    "command prompt": "cmd", "terminal": "wt", "powershell": "powershell",
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "outlook": "outlook", "spotify": "spotify:", "steam": "steam:", "discord": "discord:",
    "camera": "microsoft.windows.camera:", "snipping tool": "ms-screenclip:",
    "clock": "ms-clock:", "calendar": "outlookcal:", "store": "ms-windows-store:",
}

SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "google drive": "https://drive.google.com",
    "google docs": "https://docs.google.com", "netflix": "https://www.netflix.com",
    "reddit": "https://www.reddit.com", "github": "https://github.com",
    "claude": "https://claude.ai", "chatgpt": "https://chatgpt.com",
    "instagram": "https://www.instagram.com", "twitter": "https://x.com", "x": "https://x.com",
}

_OPEN = re.compile(r"^(?:hey |ok |okay )?(?:can you |could you |please )*(?:open|launch|start|run|bring up)\s+(?:up\s+)?(?:the\s+|my\s+)?(.+?)(?:\s+app)?(?:\s+for me)?(?:\s+please)?$")
_GOOGLE = re.compile(r"^(?:can you |please )*google\s+(.+)$")


def _clean(text):
    return re.sub(r"[.!?,]+$", "", text.strip().lower()).strip()


def try_shortcut(text):
    """Do the command instantly if it's a simple one. Returns what to say, or None for Claude."""
    t = _clean(text)
    if " and " in t or " then " in t:
        return None  # multi-step: let Claude handle it

    match = _GOOGLE.match(t)
    if match:
        query = match.group(1)
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(query))
        return f"Googling {query}."

    match = _OPEN.match(t)
    if not match:
        return None
    name = match.group(1).strip()
    if name in SITES:
        webbrowser.open(SITES[name])
        return f"Opening {name}."
    if re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", name):  # looks like a website, e.g. "bbc.com"
        webbrowser.open("https://" + name)
        return f"Opening {name}."
    if name in APPS:
        try:
            os.startfile(APPS[name])  # Windows only
            return f"Opening {name}."
        except (OSError, AttributeError):
            return None  # not installed or not found - let Claude try another way
    return None
