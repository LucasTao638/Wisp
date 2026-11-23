"""Routines: one phrase does several things.

Make them by just saying what you want:
  "when I say movie night, open Netflix, turn the volume down and mute notifications"
  "whenever I say I'm home, play my music and tell me my reminders"
  "add 'open Spotify' to my gaming mode routine"        "rename study mode to homework time"
Manage them:
  "what routines do I have"      "delete the movie night routine"      "forget what to do when I say I'm home"
(Claude writes them into routines.json for you. You can still edit that file by hand if you like.)

Steps a routine can use (instant ones first; "ask" hands something to Claude):
  {"say": "text"}                     say something
  {"open": "steam:"}                  open an app, file, folder or website (anything you could type in Win+R)
  {"close": "chrome"}                 close an app (program name, without .exe)
  {"minimise_all": true}              show the desktop
  {"timer": 25, "label": "Pasta"}     start a timer (minutes)
  {"focus_session": 25, "rounds": 4}  start a focus session        {"stop_focus_session": true}
  {"media": "play_pause" | "next" | "previous" | "mute"}
  {"volume": "up" | "down", "steps": 5}
  {"mute_jarvis": true | false}
  {"lock_pc": true}
  {"wait": 2}                         wait some seconds
  {"ask": "instruction for Claude"}   anything that needs thinking, the web, or clicking around in apps
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import sysplat

ROOT = Path(__file__).resolve().parent
FILE = ROOT / "routines.json"

DEFAULTS = {
    "gaming mode": {
        "triggers": ["gaming mode", "game mode", "time to game", "let's game", "游戏模式", "开始打游戏"],
        "steps": [
            {"say": "Gaming mode. Launching Steam and Discord."},
            {"stop_focus_session": True},
            {"open": "steam:"},
            {"open": "discord:"},
        ],
    },
    "study mode": {
        "triggers": ["study mode", "homework mode", "time to study", "time to do homework", "学习模式", "写作业模式"],
        "steps": [
            {"say": "Study mode. Starting a 25 minute focus session."},
            {"minimise_all": True},
            {"focus_session": 25, "rounds": 4},
        ],
    },
    "goodnight": {
        "triggers": ["goodnight", "good night", "i'm going to bed", "bedtime", "晚安", "我要睡觉了"],
        "steps": [
            {"say": "Goodnight. Pausing your music and locking the PC."},
            {"media": "play_pause"},
            {"wait": 3},
            {"lock_pc": True},
        ],
    },
}


# ---------- the file ----------
def load():
    if not FILE.exists():
        save(DEFAULTS)
        return json.loads(json.dumps(DEFAULTS))
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"(routines.json has a mistake in it: {exc})")
        return {}


def save(routines):
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(routines, indent=2), encoding="utf-8")
    os.replace(tmp, FILE)


def check():
    """Is routines.json valid? Returns a list of problems (empty = fine)."""
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        return [f"routines.json isn't valid JSON: {exc}"]
    problems = []
    known = {"say", "open", "close", "minimise_all", "timer", "label", "focus_session", "rounds", "break",
             "stop_focus_session", "media", "volume", "steps", "mute_jarvis", "lock_pc", "wait", "ask"}
    for name, r in data.items():
        if not isinstance(r, dict) or not isinstance(r.get("steps"), list):
            problems.append(f"'{name}' needs a list of steps")
            continue
        for step in r["steps"]:
            unknown = set(step) - known if isinstance(step, dict) else {"(not an object)"}
            if unknown:
                problems.append(f"'{name}' has a step I don't know: {', '.join(sorted(unknown))}")
    return problems


# ---------- matching what you said ----------
def _norm(text):
    text = re.sub(r"^(hey |ok |okay )?(jarvis|wisp|sidekick)[, ]+", "", text.lower().strip())
    text = re.sub(r"^(please |can you |could you |start |activate |turn on |run |begin |go |do )+", "", text)
    text = re.sub(r"^(请|帮我|启动|开启|开始|运行|执行|进入)+", "", text)
    return re.sub(r"[^a-z0-9' \u4e00-\u9fff]+", " ", text).strip()


def find(text):
    """The routine this phrase starts, as (name, routine) - or None."""
    t = _norm(text)
    for name, routine in load().items():
        for trigger in [name] + routine.get("triggers", []):
            trig = _norm(trigger)
            if trig and (t == trig or re.fullmatch(rf"{re.escape(trig)}( (now|please|mode|on|time|routine))*", t)):
                return name, routine
    return None


def _find_by_mention(t):
    """Which routine does this sentence mention (by name or one of its trigger phrases)?"""
    routines = load()
    best = None
    for name, r in routines.items():
        for phrase in [name] + r.get("triggers", []):
            p = _norm(phrase)
            found = (p in t) if not p.isascii() else re.search(rf"\b{re.escape(p)}\b", t)  # Chinese has no spaces
            if p and found and (not best or len(p) > len(best[1])):
                best = (name, p)
    return best[0] if best else None


# ---------- plain-English descriptions ----------
def _thing(target):
    target = str(target)
    if re.match(r"https?://", target):
        return urlparse(target).netloc.removeprefix("www.")
    if target.endswith(":"):
        return target[:-1].replace("-", " ").title()
    return os.path.basename(target.rstrip("\\/")) or target


_ZH_STEPS = {"say": "说「{v}」", "open": "打开{v}", "close": "关闭{v}", "timer": "开始{v}分钟计时",
             "focus_session": "开始{v}分钟专注", "ask": "让 Claude「{v}」"}
_ZH_FLAGS = {"minimise_all": "显示桌面", "stop_focus_session": "结束专注", "lock_pc": "锁定电脑"}
_ZH_MEDIA = {"play_pause": "播放/暂停音乐", "next": "下一首", "previous": "上一首", "mute": "静音"}


def _describe_step_zh(step):
    for key, fmt in _ZH_STEPS.items():
        if key in step:
            value = _thing(step[key]) if key == "open" else (f"{step[key]:g}" if isinstance(step[key], (int, float)) else step[key])
            return fmt.format(v=value)
    for key, text in _ZH_FLAGS.items():
        if step.get(key):
            return text
    if "media" in step:
        return _ZH_MEDIA.get(step["media"], step["media"])
    if "volume" in step:
        return "调高音量" if step["volume"] == "up" else "调低音量"
    if "mute_jarvis" in step:
        return "静音 Wisp" if step["mute_jarvis"] else "取消静音"
    return "执行操作"


def describe_step(step):
    import i18n
    if i18n.is_zh():
        return _describe_step_zh(step)
    if "say" in step:
        return f"says “{step['say']}”"
    if "open" in step:
        return f"opens {_thing(step['open'])}"
    if "close" in step:
        return f"closes {step['close'].title()}"
    if step.get("minimise_all"):
        return "shows the desktop"
    if "timer" in step:
        return f"starts a {step['timer']:g} min timer" + (f" ({step['label']})" if step.get("label") else "")
    if "focus_session" in step:
        return f"starts a {step['focus_session']:g} min focus session"
    if step.get("stop_focus_session"):
        return "stops any focus session"
    if "media" in step:
        return {"play_pause": "plays/pauses music", "next": "skips the song", "previous": "goes back a song",
                "mute": "mutes the PC"}.get(step["media"], step["media"])
    if "volume" in step:
        return f"turns the volume {step['volume']}"
    if "mute_jarvis" in step:
        return "mutes Wisp" if step["mute_jarvis"] else "unmutes Wisp"
    if step.get("lock_pc"):
        return "locks the PC"
    if "wait" in step:
        return f"waits {step['wait']:g}s"
    if "ask" in step:
        return f"asks Claude to “{step['ask']}”"
    return "does something"


def describe(routine):
    steps = [s for s in routine.get("steps", []) if "wait" not in s]
    actions = [s for s in steps if "say" not in s]
    parts = [describe_step(s) for s in (actions or steps)]  # the spoken line is left out if it does other things
    import i18n
    if i18n.is_zh():
        return "、".join(parts) if parts else "暂无操作"
    if not parts:
        return "does nothing yet"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------- voice commands about routines ----------
_CREATE = re.compile(r"\b(when(ever)?|if|once|any ?time) i (say|tell you|type)\b|"
                     r"\b(make|create|add|set up|setup|new|build) (me )?(a |an )?(new )?routine\b|"
                     r"\b(change|edit|update|modify|rename|fix|improve) (my |the |that )?.{0,40}\broutine\b|"
                     r"\badd .{1,80} to (my |the )?.{0,40}\broutine\b|\bremove .{1,80} from (my |the )?.{0,40}\broutine\b")


def handle_command(text):
    """List / delete routines instantly. Returns what to say, or None."""
    t = _norm(text)
    if re.search(r"\b(what|which|list|show|tell me)\b.*\broutines\b|\bmy routines\b$", t):
        routines = load()
        if not routines:
            return 'You don\'t have any routines. Try: "when I say movie night, open Netflix".'
        names = list(routines)
        listed = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        return f"You have {len(names)} routine{'s' if len(names) != 1 else ''}: {listed}."
    if re.search(r"\b(delete|remove|forget|get rid of|cancel|scrap)\b", t) and \
            re.search(r"\broutine\b|\bwhen i say\b", t) and not re.search(r"\bfrom (my |the )?.*routine\b", t):
        name = _find_by_mention(t)
        if not name:
            return "I couldn't tell which routine you meant. Say “what routines do I have” to hear them."
        routines = load()
        routines.pop(name, None)
        save(routines)
        return f"Deleted the {name} routine."
    return None


def builder_prompt(text, force=False):
    """If you're asking to create or change a routine, the instructions for Claude to do it. Else None."""
    t = _norm(text)
    edits_existing = re.search(r"\b(rename|change|edit|update|modify|tweak)\b|\badd .+ to\b|\bremove .+ from\b", t) \
        and _find_by_mention(t)
    if not (force or _CREATE.search(text.lower()) or edits_existing):
        return None
    current = json.dumps(load(), indent=2)
    return f"""[ROUTINE BUILDER] The user wants to create or change a routine: a phrase that, when they say it, makes Wisp do several things straight away.

What they said: “{text}”

Current routines in ../routines.json:
{current}

Do this:
1. Work out the trigger phrase they want and what should happen. If they're changing or renaming an existing routine, edit that one.
2. Edit ../routines.json. Each routine is "name": {{"triggers": [...], "steps": [...]}}.
   - name: short and lowercase (e.g. "movie night").
   - triggers: the exact phrase they said, plus 2-3 natural variations, lowercase, no punctuation, in the language
     they spoke (e.g. Chinese triggers for a Chinese request). Never use a trigger that would hijack an ordinary request (like "open spotify") unless they asked for exactly that.
   - steps: use these instant steps wherever possible:
     {{"say": "text"}}, {{"open": "app: / file / https://url"}}, {{"close": "program name without .exe"}}, {{"minimise_all": true}},
     {{"timer": minutes, "label": "..."}}, {{"focus_session": minutes, "rounds": n}}, {{"stop_focus_session": true}},
     {{"media": "play_pause|next|previous|mute"}}, {{"volume": "up|down", "steps": n}}, {{"mute_jarvis": true|false}},
     {{"lock_pc": true}}, {{"wait": seconds}}
   - For anything that needs thinking, the web, a specific playlist, or clicking around in an app, add {{"ask": "clear instruction"}} (it's passed to you when the routine runs). Put "ask" steps last.
   - Start with a short {{"say": ...}} so the user hears it working (in your calm butler style).
   - For apps, use their Windows protocol or exe name if you know it (steam:, spotify:, discord:, ms-settings:, notepad, chrome). If unsure whether an app is installed, check (e.g. look in the Start Menu folders) before writing the step.
3. Run: python ../routines.py check   and fix any problems it reports.
4. In the SAY line, confirm in one sentence what will happen and what phrase starts it. Don't run the routine now."""


# ---------- running a routine ----------
def run(routine, assistant):
    """Do each step (on Wisp's worker thread)."""
    import focus
    import timers
    for step in routine.get("steps", []):
        try:
            if "say" in step:
                assistant.say_now(step["say"])
            elif "open" in step:
                sysplat.open_target(step["open"])
            elif "close" in step:
                sysplat.close_app(step["close"])
            elif step.get("minimise_all"):
                sysplat.show_desktop()
            elif "timer" in step:
                timers.add(seconds=float(step["timer"]) * 60, label=step.get("label", ""), kind="timer")
            elif "focus_session" in step:
                focus.start_session(step["focus_session"], step.get("break", 5), step.get("rounds", 4))
            elif step.get("stop_focus_session"):
                focus.stop_session()
            elif "media" in step or "volume" in step:
                key = step.get("media") or f"volume_{step['volume']}"
                sysplat.media({"mute": "mute_pc"}.get(key, key), step.get("steps"))
            elif "mute_jarvis" in step:
                assistant.set_muted(bool(step["mute_jarvis"]))
            elif step.get("lock_pc"):
                sysplat.lock_screen()
            elif "wait" in step:
                time.sleep(min(30, float(step["wait"])))
            elif "ask" in step:
                assistant.submit(step["ask"], source=assistant.source)
        except Exception as exc:
            assistant.emit("info", f"Routine step failed ({describe_step(step)}): {exc}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        problems = check()
        print("\n".join(problems) if problems else "routines.json is valid.")
        for name, r in load().items():
            print(f"- {name} (say: {', '.join(r.get('triggers', [])) or name}): {describe(r)}")
        sys.exit(1 if problems else 0)
    print(__doc__)
