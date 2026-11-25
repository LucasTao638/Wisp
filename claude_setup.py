"""Finding, installing and checking Claude Code (Wisp's brain), so nobody has to type commands.

- find_claude(): finds Claude Code even when it isn't on PATH (apps started from the Start Menu, Finder or
  the Dock don't see a PATH change until you log out and in again).
- install_claude(): runs Anthropic's official installer in the background, with no console window.
- check_ready(): asks Claude Code to say "OK" with a tiny request, to prove it's installed AND signed in.
- status_card(): the "Claude Code" box used by the setup screen and Settings.

Can also be run from a terminal:  python claude_setup.py   (prints the status, installs if missing)
"""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
NO_WINDOW = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW

WIN_INSTALL = "irm https://claude.ai/install.ps1 | iex"
UNIX_INSTALL = "curl -fsSL https://claude.ai/install.sh | bash"


def _candidates():
    home = Path.home()
    if IS_WIN:
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [home / ".local" / "bin" / "claude.exe",            # official installer
                appdata / "npm" / "claude.cmd",                      # npm install -g
                local / "Programs" / "claude" / "claude.exe",
                local / "Microsoft" / "WinGet" / "Links" / "claude.exe"]
    return [home / ".local" / "bin" / "claude",                      # official installer
            home / ".claude" / "local" / "claude",                   # older "migrate-installer" location
            Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude"),   # Homebrew / npm
            home / ".npm-global" / "bin" / "claude"]


def find_claude():
    """Full path to Claude Code, or None."""
    found = shutil.which("claude")
    if found:
        return found
    for path in _candidates():
        if path.is_file():
            return str(path)
    return None


def _ensure_on_path(folder):
    """Make 'claude' work in new terminals too (handy, but Wisp itself doesn't need it)."""
    folder = str(folder)
    try:
        if IS_WIN:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    current, kind = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    current, kind = "", winreg.REG_EXPAND_SZ
                parts = [p for p in current.split(";") if p]
                if not any(os.path.normcase(p.rstrip("\\")) == os.path.normcase(folder) for p in parts):
                    winreg.SetValueEx(key, "Path", 0, kind, ";".join(parts + [folder]))
        else:
            line = f'export PATH="{folder}:$PATH"'
            for name in (".zshrc", ".bash_profile"):
                rc = Path.home() / name
                text = rc.read_text(encoding="utf-8") if rc.exists() else ""
                if folder not in text:
                    with open(rc, "a", encoding="utf-8") as f:
                        f.write(f"\n# Added by Wisp so the 'claude' command works\n{line}\n")
    except Exception:
        pass
    if folder not in os.environ.get("PATH", ""):
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")


def install_claude(on_line=None):
    """Install Claude Code with Anthropic's official installer. Returns (ok, message)."""
    if IS_WIN:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", WIN_INSTALL]
    else:
        cmd = ["/bin/bash", "-c", UNIX_INSTALL]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        tail = []
        for line in proc.stdout:
            line = line.strip()
            if line:
                tail = (tail + [line])[-6:]
                if on_line:
                    on_line(line)
        proc.wait(timeout=900)
    except Exception as e:
        return False, f"The installer couldn't run: {e}"
    path = find_claude()
    if not path:
        return False, "Claude Code didn't install. " + (tail[-1] if tail else "Check your internet connection.")
    _ensure_on_path(Path(path).parent)
    return True, "Claude Code is installed."


def _run(args, env=None, timeout=90):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=timeout, env=env, creationflags=NO_WINDOW)


def version():
    path = find_claude()
    if not path:
        return None
    try:
        out = _run([path, "--version"], timeout=30).stdout.strip()
        return out.split()[0] if out else "?"
    except Exception:
        return "?"


def check_ready(api_key=None):
    """Send Claude Code one tiny request. Returns (state, message), state being
    'ready', 'missing' (not installed), 'signed_out', 'no_credit' or 'error'."""
    path = find_claude()
    if not path:
        return "missing", "Claude Code isn't installed yet."
    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    try:
        r = _run([path, "-p", "Reply with just the word OK.", "--max-turns", "1", "--model", "haiku"],
                 env=env, timeout=120)
    except subprocess.TimeoutExpired:
        return "error", "Claude Code didn't answer in time. Check your internet connection and try again."
    except Exception as e:
        return "error", f"Couldn't start Claude Code: {e}"
    out = (r.stdout + "\n" + r.stderr).strip()
    low = out.lower()
    if r.returncode == 0 and "ok" in low:
        return "ready", "Connected. Claude is ready."
    if any(s in low for s in ("/login", "not logged in", "please log in", "invalid api key", "authentication",
                              "unauthorized", "401")):
        return "signed_out", "Claude Code isn't signed in yet."
    if any(s in low for s in ("credit", "billing", "usage limit", "quota")):
        return "no_credit", "Claude Code is signed in, but there's no credit left: " + out.splitlines()[-1][:160]
    last = out.splitlines()[-1][:200] if out else f"exit code {r.returncode}"
    return "error", "Claude Code replied with an error: " + last


def open_sign_in():
    """Open Claude Code in its own window, where Anthropic's sign-in runs. Returns (ok, message)."""
    path = find_claude()
    if not path:
        return False, "Install Claude Code first."
    try:
        if IS_WIN:
            safe = path.replace("'", "''")
            subprocess.Popen(["powershell", "-NoProfile", "-NoExit", "-Command",
                              f"$host.UI.RawUI.WindowTitle = 'Claude Code sign-in'; & '{safe}'"],
                             creationflags=0x00000010)  # CREATE_NEW_CONSOLE
        elif IS_MAC:
            quoted = "'" + path.replace("'", "'\\''") + "'"
            script = quoted.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{script}"',
                              "-e", 'tell application "Terminal" to activate'])
        else:
            subprocess.Popen(["x-terminal-emulator", "-e", path])
        return True, ""
    except Exception as e:
        return False, f"Couldn't open Claude Code: {e}"


# ---------- the shared "Claude Code" box (setup screen + Settings) ----------
def status_card(parent, f, accent, get_api_key, on_ready=None):
    """A box showing whether Claude Code is installed and connected, with Install / Test buttons."""
    import tkinter as tk
    import ui_kit as ui
    from i18n import L

    card = tk.Frame(parent, bg=ui.CARD, padx=14, pady=10)
    top = tk.Frame(card, bg=ui.CARD)
    top.pack(fill="x")
    title = tk.Label(top, bg=ui.CARD, fg=ui.TEXT, font=f["body"], anchor="w")
    title.pack(side="left")
    buttons = tk.Frame(top, bg=ui.CARD)
    buttons.pack(side="right")
    status = tk.Label(card, bg=ui.CARD, fg=ui.DIM, font=f["small"], anchor="w", justify="left", wraplength=500)
    status.pack(fill="x", pady=(6, 0))
    busy = {"on": False}

    def safe(fn):  # update the window from a worker thread
        try:
            card.after(0, fn)
        except Exception:
            pass

    def set_status(text, colour=None):
        safe(lambda: status.winfo_exists() and status.config(text=text, fg=colour or ui.DIM))

    def show_buttons(*specs):
        def draw():
            if not buttons.winfo_exists():
                return
            for w in buttons.winfo_children():
                w.destroy()
            for label, fn, primary in specs:
                kw = {"bg": accent, "fg": "#031018", "hover": accent} if primary else {}
                ui.FlatButton(buttons, label, fn, font=f["small"], **kw).pack(side="left", padx=(6, 0))
        safe(draw)

    def refresh():
        path = find_claude()
        if path:
            v = version()  # runs a program, so do it here on the worker thread, not in the window
            safe(lambda: title.winfo_exists() and title.config(
                text=L(f"✓ Claude Code installed ({v})", f"✓ 已安装 Claude Code（{v}）")))
            show_buttons((L("Test connection", "测试连接"), test, True))
        else:
            safe(lambda: title.winfo_exists() and title.config(text=L("Claude Code isn't installed",
                                                                         "尚未安装 Claude Code")))
            set_status(L("Wisp needs it to think. One click installs it (about a minute).",
                         "Wisp 需要它来思考。点一下即可安装（大约一分钟）。"))
            show_buttons((L("Install it for me", "帮我安装"), install, True))

    def install():
        if busy["on"]:
            return
        busy["on"] = True
        show_buttons()
        set_status(L("Installing Claude Code… (about a minute)", "正在安装 Claude Code……（大约一分钟）"))

        def work():
            ok, msg = install_claude(lambda line: set_status(L("Installing… ", "正在安装…… ") + line[:90]))
            busy["on"] = False
            if ok:
                set_status(L("✓ Installed.", "✓ 安装完成。"), ui.GREEN)
            else:
                set_status("✗ " + msg, ui.RED)
            threading.Thread(target=refresh, daemon=True).start()
        threading.Thread(target=work, daemon=True).start()

    def test():
        if busy["on"]:
            return
        busy["on"] = True
        set_status(L("Testing… (a few seconds)", "正在测试……（几秒钟）"))

        def work():
            state, msg = check_ready(get_api_key())
            busy["on"] = False
            texts = {
                "ready": L("✓ Connected. Claude is ready.", "✓ 已连接，Claude 已就绪。"),
                "signed_out": L("Not connected yet. Follow one of the two options, then test again.",
                                "尚未连接。请按照两种方式之一完成设置，然后再测试。"),
            }
            colour = ui.GREEN if state == "ready" else ui.RED
            set_status(texts.get(state, "✗ " + msg), colour)
            if state == "ready" and on_ready:
                safe(on_ready)
        threading.Thread(target=work, daemon=True).start()

    card.refresh = lambda: threading.Thread(target=refresh, daemon=True).start()
    card.test = test
    title.config(text=L("Checking Claude Code…", "正在检查 Claude Code……"))
    card.refresh()
    return card


if __name__ == "__main__":
    print("Claude Code:", find_claude() or "not found")
    if not find_claude():
        print("Installing…")
        print(install_claude(print)[1])
    state, msg = check_ready()
    print(state, "-", msg)
