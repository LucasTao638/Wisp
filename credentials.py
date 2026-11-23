"""Stores your Anthropic API key encrypted, using Windows' own protection (DPAPI).

The key is saved in secrets.bin and can only be decrypted by YOUR Windows account on THIS PC.
It never goes in config.json, the log, or anything that gets shared.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILE = ROOT / "secrets.bin"


def _dpapi(data, encrypt):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), "Wisp" if encrypt else None, None, None, None, 0x1, ctypes.byref(blob_out))
    if not ok:
        raise OSError("Windows couldn't encrypt/decrypt the key")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def save_api_key(key):
    key = (key or "").strip()
    if not key:
        FILE.unlink(missing_ok=True)
        return
    data = key.encode()
    if sys.platform == "win32":
        FILE.write_bytes(b"DPAPI" + _dpapi(data, True))
    else:  # only used when testing on other systems
        FILE.write_bytes(b"PLAIN" + data)


def load_api_key():
    try:
        raw = FILE.read_bytes()
    except OSError:
        return None
    try:
        if raw.startswith(b"DPAPI"):
            return _dpapi(raw[5:], False).decode()
        if raw.startswith(b"PLAIN"):
            return raw[5:].decode()
    except (OSError, UnicodeDecodeError):
        return None
    return None


def has_api_key():
    return bool(load_api_key())


def masked():
    key = load_api_key()
    return f"{key[:10]}…{key[-4:]}" if key and len(key) > 16 else ("set" if key else "not set")


def check_api_key(key):
    """Ask Anthropic whether the key works. Returns (ok, message)."""
    key = (key or "").strip()
    if not key.startswith("sk-ant-"):
        return False, "That doesn't look like an Anthropic API key (they start with sk-ant-)."
    req = urllib.request.Request("https://api.anthropic.com/v1/models?limit=1",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            json.loads(res.read() or b"{}")
        return True, "Key works."
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "Anthropic rejected that key. Check you copied all of it."
        return False, f"Anthropic replied with an error ({e.code}). Try again in a moment."
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, "Couldn't reach Anthropic. Check your internet connection."
