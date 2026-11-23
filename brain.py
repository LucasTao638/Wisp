"""The 'brain': runs Claude Code in headless mode (claude -p) using your Claude Pro login.

Claude Code already has the hard parts built in - a planning/to-do loop, web search,
web page reading, file tools and sub-agents. We plug Windows app control into it via
the free Windows-MCP server and stream its progress back to the voice front-end.
"""
import json
import re
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "workspace"
MCP_CONFIG = WORKSPACE / "mcp.json"
SETTINGS = WORKSPACE / ".claude" / "settings.json"

# Pre-approved tools. In headless mode there's no pop-up to approve things,
# so anything not listed here is blocked. Dangerous commands are still denied
# by the "deny" list in workspace/.claude/settings.json.
ALLOWED_TOOLS = [
    "WebSearch", "WebFetch", "Read", "Edit", "Write", "Glob", "Grep",
    "TodoWrite", "Task", "ToolSearch", "Bash", "PowerShell", "mcp__windows-mcp",
]
for _folder in ("output", "projects"):
    (WORKSPACE / _folder).mkdir(parents=True, exist_ok=True)

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def find_exe(name):
    """Find an executable on PATH, or in the default per-user install folder."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in (Path.home() / ".local" / "bin" / f"{name}.exe",
                      Path.home() / ".local" / "bin" / name):
        if candidate.exists():
            return str(candidate)
    return None


def write_mcp_config():
    """Write workspace/mcp.json with the full path to uvx (avoids PATH problems on Windows)."""
    servers = {}
    env = {"ANONYMIZED_TELEMETRY": "false"}
    installed = find_exe("windows-mcp")  # from: uv tool install windows-mcp --python 3.13
    uvx = find_exe("uvx")
    if installed:
        servers["windows-mcp"] = {"command": installed, "args": ["serve"], "env": env}
    elif uvx:
        servers["windows-mcp"] = {"command": uvx, "args": ["--python", "3.13", "windows-mcp", "serve"], "env": env}
    MCP_CONFIG.write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")
    return bool(servers)


def build_command(cfg, session_id=None, background=False, live=False):
    claude = find_exe("claude")
    if not claude:
        raise RuntimeError("Claude Code isn't installed or isn't on PATH. Run setup.bat first.")
    cmd = [claude, "-p",
           "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(MCP_CONFIG),
           "--settings", str(SETTINGS),
           "--permission-mode", "acceptEdits",
           "--allowedTools", ",".join(ALLOWED_TOOLS)]
    if live:
        # Keep the process open and feed it one message at a time (no restart per request),
        # and stream the reply word by word so speaking can start before Claude has finished.
        cmd += ["--input-format", "stream-json", "--include-partial-messages"]
    for folder in cfg.get("extra_folders", []):
        folder = os.path.expanduser(folder)
        if os.path.isdir(folder):
            cmd += ["--add-dir", folder]
    model = cfg.get("background_model") if background else cfg.get("model")
    if model:
        cmd += ["--model", model]
    if background and not cfg.get("background_can_use_mouse", False):
        # Stop background jobs grabbing your mouse/keyboard while you're working.
        cmd += ["--disallowedTools", "mcp__windows-mcp"]
    if session_id:
        cmd += ["--resume", session_id]
    return cmd


def _env():
    env = os.environ.copy()
    # Use the Anthropic API key saved in Wisp's setup (stored encrypted). That's the supported way
    # for apps like Wisp to use Claude. Without one, Claude Code uses however you've set it up yourself.
    import credentials
    key = credentials.load_api_key()
    if key:
        env["ANTHROPIC_API_KEY"] = key
    # Give MCP servers (Windows-MCP) up to 60s to start - the first start can be slow.
    env.setdefault("MCP_TIMEOUT", "60000")
    # Load the app-control tools up front, so Claude doesn't spend a step searching for them.
    env.setdefault("ENABLE_TOOL_SEARCH", "false")
    return env


def _start(cmd):
    proc = subprocess.Popen(
        cmd, cwd=WORKSPACE, env=_env(),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=NO_WINDOW,
    )
    stderr_lines = []
    threading.Thread(target=lambda: stderr_lines.extend(proc.stderr), daemon=True).start()
    return proc, stderr_lines


def _summarise_tool_input(tool_input):
    if not isinstance(tool_input, dict):
        return ""
    for key in ("query", "url", "file_path", "path", "command", "pattern",
                "description", "name", "text", "app"):
        value = tool_input.get(key)
        if value:
            value = str(value).replace("\n", " ")
            return value[:90] + ("..." if len(value) > 90 else "")
    return ""


_SAY_LINE = re.compile(r"^[\s*_>]*SAY:[\s*_]*(.+?)[\s*_]*$", re.IGNORECASE)


class _SayWatcher:
    """Spots a 'SAY:' line while the reply is still streaming in, so it can be spoken straight away."""

    def __init__(self, on_event):
        self.on_event, self.buffer, self.spoken = on_event, "", set()

    def reset(self):
        self.buffer = ""

    def feed(self, text, final=False):
        self.buffer += text
        lines = self.buffer.split("\n")
        complete = lines if final else lines[:-1]  # the last line may still be growing
        for line in complete:
            m = _SAY_LINE.match(line)
            if m and m.group(1) not in self.spoken:
                self.spoken.add(m.group(1))
                self.on_event("say", m.group(1))


def _read_turn(proc, result, on_event):
    """Read Claude's output until the end of one turn. Returns True if a turn finished."""
    last_text = ""
    say = _SayWatcher(on_event)
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = msg.get("type")
        if msg.get("session_id"):
            result["session_id"] = msg["session_id"]
        if kind == "stream_event":
            event = msg.get("event", {})
            etype = event.get("type")
            if etype == "message_start":
                say.reset()
            elif etype == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                say.feed(event["delta"].get("text", ""))
            elif etype == "content_block_stop":
                say.feed("", final=True)
                say.reset()
            continue
        if kind == "assistant":
            for block in msg.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    on_event("tool", f"{block.get('name', '?')}  {_summarise_tool_input(block.get('input'))}")
                elif block.get("type") == "text" and block.get("text", "").strip():
                    last_text = block["text"]
                    on_event("text", last_text)
        elif kind == "result":
            result["text"] = msg.get("result") or last_text
            result["ok"] = not msg.get("is_error", False) and msg.get("subtype") == "success"
            if not result["ok"]:
                result["error"] = msg.get("subtype", "error")
            return True
    result["text"] = result["text"] or last_text
    return False


class LiveSession:
    """One Claude Code process that stays running between requests - much faster than
    starting Claude Code (and the app-control tool) from scratch every time."""

    def __init__(self, cfg, session_id=None):
        self.cfg = cfg
        self.session_id = session_id
        self.proc = None
        self.stderr = []
        self.lock = threading.Lock()

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def warm_up(self):
        """Start Claude Code early, so it's ready before the first request."""
        with self.lock:
            if not self.alive():
                self.proc, self.stderr = _start(build_command(self.cfg, self.session_id, live=True))

    def ask(self, prompt, on_event=None, _retry=True):
        on_event = on_event or (lambda kind, text: None)
        self.warm_up()
        result = {"ok": False, "text": "", "session_id": self.session_id, "error": ""}
        message = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}}
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
            finished = _read_turn(self.proc, result, on_event)
        except (OSError, ValueError, AttributeError):
            finished = False
        if result["session_id"]:
            self.session_id = result["session_id"]
        if finished:
            return result

        # The process ended mid-turn: stopped by the user, crashed, or the old session expired.
        err = "".join(self.stderr).strip()
        self.stop()
        if _retry and not result["text"] and ("session" in err.lower() or "resume" in err.lower()):
            self.session_id = None
            return self.ask(prompt, on_event, _retry=False)
        result["error"] = result["error"] or err[-500:] or "Claude Code stopped."
        return result

    def stop(self):
        proc, self.proc = self.proc, None
        if proc and proc.poll() is None:
            proc.kill()

    def reset(self):
        """Forget the conversation and start fresh."""
        self.stop()
        self.session_id = None


def run_claude(prompt, cfg, session_id=None, on_event=None, background=False):
    """One-off request in its own process (used for background jobs)."""
    on_event = on_event or (lambda kind, text: None)
    proc, stderr_lines = _start(build_command(cfg, session_id=session_id, background=background))
    # The prompt goes in through stdin, which avoids Windows quoting problems.
    proc.stdin.write(prompt)
    proc.stdin.close()
    result = {"ok": False, "text": "", "session_id": session_id, "error": ""}
    _read_turn(proc, result, on_event)
    proc.wait()
    if not result["text"] and not result["ok"]:
        err = "".join(stderr_lines).strip()
        result["error"] = result["error"] or err[-500:] or f"Claude Code exited with code {proc.returncode}"
        if session_id and ("session" in err.lower() or "resume" in err.lower()):
            return run_claude(prompt, cfg, None, on_event, background)
    return result


def split_say(text):
    """Pull out the 'SAY:' line (what gets spoken) from the rest of the reply."""
    say, keep = "", []
    for line in text.splitlines():
        stripped = line.strip().lstrip("*_").strip()
        if stripped.upper().startswith("SAY:"):
            say = stripped[4:].strip().strip("*_").strip()
        else:
            keep.append(line)
    body = "\n".join(keep).strip()
    if not say:
        plain = body.replace("#", "").replace("*", "").strip()
        say = plain[:250].rsplit(" ", 1)[0] + ("..." if len(plain) > 250 else "")
    return say, body
