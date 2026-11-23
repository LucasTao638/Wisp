"""Focus sessions (Pomodoro): focus time and breaks, announced out loud.

  "start a focus session"   4 rounds of 25 min focus with 5 min breaks (every 4th break is longer)
  "pomodoro"                same
  "focus for 50 minutes"    one 50 minute round
  "how long is left in my session"     "stop the focus session"

Command line (Claude uses these too):
  python focus.py session [--focus 25] [--break 5] [--rounds 4]  |  python focus.py stop  |  python focus.py status
"""
import argparse
import datetime as dt
import json
import os
import re
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "focus.json"


# ---------- saved state ----------
def get_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(state):
    tmp = STATE.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    os.replace(tmp, STATE)


def _update(**changes):
    state = get_state()
    state.update(changes)
    _save(state)


def add_focus_minutes(minutes):
    state = get_state()
    stats = state.setdefault("stats", {})
    today = dt.date.today().isoformat()
    before = stats.get(today, 0)
    stats[today] = round((before if isinstance(before, (int, float)) else 0) + minutes, 1)
    for old in sorted(stats)[:-14]:  # keep two weeks
        stats.pop(old, None)
    _save(state)


def focus_minutes_today():
    value = get_state().get("stats", {}).get(dt.date.today().isoformat(), 0)
    return value if isinstance(value, (int, float)) else 0


# ---------- sessions ----------
def session_phase():
    s = get_state().get("session")
    return s.get("phase") if s else None


def start_session(focus_min=25, break_min=5, rounds=4):
    _update(session={"phase": "focus", "round": 1, "rounds": int(rounds), "focus_min": float(focus_min),
                     "break_min": float(break_min), "ends": time.time() + focus_min * 60, "started": time.time()})


def stop_session():
    s = get_state().get("session")
    _update(session=None)
    return s


def session_text():
    s = get_state().get("session")
    if not s:
        return None
    m, sec = divmod(int(max(0, s["ends"] - time.time())), 60)
    label = "Focus" if s["phase"] == "focus" else "Break"
    return f"{label} {m}:{sec:02d}  ·  round {s['round']} of {s['rounds']}"


def advance_session():
    """Move to the next phase if the current one is over. Returns a message to announce, or None."""
    s = get_state().get("session")
    if not s or time.time() < s["ends"]:
        return None
    if s["phase"] == "focus":
        add_focus_minutes(s["focus_min"])
        if s["round"] >= s["rounds"]:
            _update(session=None)
            total = int(s["focus_min"] * s["rounds"])
            return f"Session complete. {s['rounds']} round{'s' if s['rounds'] != 1 else ''}, {total} minutes of focus. Well done."
        long_break = s["round"] % 4 == 0
        length = s["break_min"] * (3 if long_break else 1)
        s.update(phase="break", ends=time.time() + length * 60)
        _update(session=s)
        return f"Time for a {int(length)} minute {'long ' if long_break else ''}break. Step away from the screen."
    s.update(phase="focus", round=s["round"] + 1, ends=time.time() + s["focus_min"] * 60)
    _update(session=s)
    return f"Break's over. Round {s['round']} of {s['rounds']}, {int(s['focus_min'])} minutes. Let's go."


class SessionService:
    """Checks once a second whether it's time to switch between focus and break."""

    def __init__(self, on_change):
        self.on_change = on_change

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(1.0)
            try:
                message = advance_session()
                if message:
                    self.on_change(message)
            except Exception as exc:
                print(f"(focus session error: {exc})")


# ---------- understanding what you said ----------
def handle_command(text):
    """Returns what to say, or None if this isn't a focus session command."""
    from timers import parse_duration
    t = re.sub(r"[?!.]+$", "", text.strip().lower())
    t = re.sub(r"^(hey |ok |okay )?(jarvis|wisp|sidekick)[, ]+", "", t)
    t = re.sub(r"^(can you |could you |please )+", "", t)
    about_session = re.search(r"\b(pomodoro|focus session|study session|focus mode|focus for|deep work)\b", t) \
        or re.search(r"\b(my|the|this) (focus |study )?session\b", t)
    if not about_session:
        if re.search(r"\bhow (long|much).*(focus|focused|studied)\b.*\btoday\b", t):
            m = int(focus_minutes_today())
            return f"You've done {m} minute{'s' if m != 1 else ''} of focus today." if m else "No focus sessions today yet."
        return None
    if re.search(r"\b(stop|end|cancel|finish|quit)\b", t):
        return "Focus session ended." if stop_session() else "There's no focus session running."
    if re.search(r"\b(how long|time left|left in|status)\b", t):
        return session_text() or "There's no focus session running."
    minutes = (parse_duration(t)[0] or 0) / 60 or 25
    rounds = 1 if re.search(r"\bfocus for\b", t) else 4
    m = re.search(r"(\d+)\s*(rounds|sessions|pomodoros)", t)
    if m:
        rounds = int(m.group(1))
    start_session(minutes, 5, rounds)
    more = f", {rounds} rounds with 5 minute breaks" if rounds > 1 else ""
    return f"Focus session started: {int(minutes)} minutes{more}."


def _cli():
    p = argparse.ArgumentParser(description="Wisp focus sessions")
    sub = p.add_subparsers(dest="cmd", required=True)
    se = sub.add_parser("session")
    se.add_argument("--focus", type=float, default=25)
    se.add_argument("--break", dest="brk", type=float, default=5)
    se.add_argument("--rounds", type=int, default=4)
    sub.add_parser("stop")
    sub.add_parser("status")
    args = p.parse_args()
    if args.cmd == "session":
        start_session(args.focus, args.brk, args.rounds)
    elif args.cmd == "stop":
        stop_session()
    print(session_text() or "No focus session running.")


if __name__ == "__main__":
    _cli()
