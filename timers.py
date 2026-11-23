"""Timers, reminders and alarms. Saved in timers.json, so they survive restarts.

Simple voice commands are handled instantly (no waiting for Claude):
  "set a timer for 10 minutes"         "5 minute timer for the pasta"
  "remind me in 20 minutes to check the oven"     "remind me to stretch in an hour"
  "set an alarm for 7am"               "wake me up at 6:30"     "remind me at 5pm to call mum"
  "how long is left on my timer"       "what timers do I have"
  "cancel my timer"                    "cancel all timers"

Claude can also use it from the command line for anything more complicated:
  python timers.py add --in 600 --label "Check the oven"
  python timers.py add --at "17:30" --label "Call mum" --kind reminder
  python timers.py list
  python timers.py cancel 3        |   python timers.py cancel all
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "timers.json"


# ---------- storage ----------
def load():
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save(items):
    tmp = STORE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(items, indent=2), encoding="utf-8")
    os.replace(tmp, STORE)


def add(seconds=None, at=None, label="", kind="timer"):
    items = load()
    due = at if at is not None else time.time() + seconds
    item = {"id": max([i["id"] for i in items], default=0) + 1, "kind": kind, "label": label.strip(),
            "due": due, "length": seconds, "created": time.time()}
    items.append(item)
    save(items)
    return item


def cancel(which="all"):
    items = load()
    if which == "all":
        save([])
        return items
    gone = [i for i in items if str(i["id"]) == str(which)]
    save([i for i in items if str(i["id"]) != str(which)])
    return gone


def upcoming():
    return sorted(load(), key=lambda i: i["due"])


# ---------- words ----------
def say_duration(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if s and not h:
        parts.append(f"{s} second{'s' if s != 1 else ''}")
    return " and ".join(parts) if parts else "0 seconds"


def clock(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _zh():
    import i18n
    return i18n.is_zh()


def say_time(ts):
    if _zh():
        import lang_zh
        return lang_zh.say_time(ts)
    t = dt.datetime.fromtimestamp(ts)
    text = t.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ").lower()
    if t.date() != dt.date.today():
        text += " tomorrow" if t.date() == dt.date.today() + dt.timedelta(days=1) else t.strftime(" on %A")
    return text


def describe(item):
    if _zh():
        import lang_zh
        return lang_zh.describe(item)
    name = item["label"] or {"timer": "timer", "alarm": "alarm", "reminder": "reminder"}[item["kind"]]
    left = item["due"] - time.time()
    if item["kind"] == "timer":
        return f"{name}: {say_duration(left)} left"
    return f"{name} at {say_time(item['due'])}"


# ---------- understanding what you said ----------
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
        "twenty five": 25, "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60,
        "ninety": 90, "couple of": 2, "a couple of": 2, "few": 3, "a few": 3}
_NUM_WORDS = "|".join(sorted((re.escape(k) for k in _NUM), key=len, reverse=True))
_UNIT = {"h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
         "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
         "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1}
_DUR = re.compile(rf"(\d+(?:\.\d+)?|{_NUM_WORDS})[\s-]*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b")


def parse_duration(text):
    """'1 hour 30 minutes' -> 5400. Also 'half an hour', 'an hour and a half'. Returns (seconds, matched_text)."""
    t = text.lower()
    if re.search(r"\bhalf an hour\b", t):
        return 1800, "half an hour"
    total, spans = 0, []
    for m in _DUR.finditer(t):
        n = m.group(1)
        value = float(n) if n[0].isdigit() else _NUM[n]
        total += value * _UNIT[m.group(2)]
        spans.append(m.group(0))
    if total and re.search(r"\band a half\b", t):
        unit = 3600 if "hour" in t else 60
        total += unit / 2
        spans.append("and a half")
    return (int(total), " ".join(spans)) if total else (None, "")


def parse_clock(text, prefer_morning=False):
    """'7am', '6:30', '5:15 pm', '19:00' -> the next time that happens (timestamp)."""
    m = re.search(r"\b(?:at|for)\s+(\d{1,2})(?::|\.)?(\d{2})?\s*(am|pm|a\.m\.|p\.m\.)?\b", text.lower())
    if not m:
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b", text.lower())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    ampm = (m.group(3) or "").replace(".", "")
    if hour > 23 or minute > 59:
        return None
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    now = dt.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if not ampm and prefer_morning and hour < 12:  # "wake me up at 6:30" means the morning
        return (target if target > now else target + dt.timedelta(days=1)).timestamp()
    if not ampm and hour <= 12:  # "at 6:30" with no am/pm: pick the next 6:30 (morning or evening)
        for candidate in (target, target + dt.timedelta(hours=12), target + dt.timedelta(days=1)):
            if candidate > now:
                return candidate.timestamp()
    if target <= now:
        target += dt.timedelta(days=1)
    return target.timestamp()


def _label_after(text, *removals):
    """What's left once the command words are removed - e.g. 'to check the oven' -> 'Check the oven'."""
    t = text
    for r in removals:
        if r:
            t = t.replace(r, " ")
    t = re.sub(r"^.*?\b(remind me|set (?:a |an )?(?:timer|alarm|reminder)|timer|alarm)\b", " ", t)
    filler = r"(in|for|at|to|that|about|called|named|of|please|the|a|an|my)"
    previous = None
    while previous != t:  # peel off leftover little words at both ends
        previous = t
        t = re.sub(rf"^\s*{filler}\b\s*", "", t.strip())
        t = re.sub(rf"\s+{filler}\s*$", "", t.strip())
    t = re.sub(r"\s{2,}", " ", t).strip(" ,.")
    return t[:1].upper() + t[1:] if t else ""


def handle_command(text):
    """Handle a timer/reminder/alarm command. Returns what to say, or None if it isn't one."""
    t = re.sub(r"[?!]+$", "", text.strip().lower()).rstrip(".")
    t = re.sub(r"^(hey |ok |okay )?(jarvis|wisp|sidekick)[, ]+", "", t)
    t = re.sub(r"^(can you |could you |please )+", "", t)
    if not re.search(r"\b(timer|timers|alarm|alarms|remind|reminder|reminders|wake me)\b", t):
        return None

    # cancel
    if re.search(r"\b(cancel|stop|delete|remove|clear|turn off)\b", t):
        items = upcoming()
        if not items:
            return "You don't have any timers running."
        if re.search(r"\b(all|every|everything)\b", t) or len(items) == 1:
            cancel("all")
            return "Cancelled." if len(items) == 1 else f"Cancelled all {len(items)}."
        for item in items:  # "cancel the pasta timer"
            if item["label"] and item["label"].lower() in t:
                cancel(item["id"])
                return f"Cancelled {item['label']}."
        kind = "alarm" if "alarm" in t else "reminder" if "remind" in t else "timer"
        match = [i for i in items if i["kind"] == kind] or items
        cancel(match[0]["id"])
        name = match[0]["label"] or match[0]["kind"]
        return f"Cancelled the {name} {match[0]['kind']}." if match[0]["label"] and match[0]["kind"] == "timer" \
            else f"Cancelled {'your ' + name if not match[0]['label'] else name}."

    # status
    if re.search(r"\b(how long|how much time|time left|left on|what timers|what reminders|what alarms|"
                 r"any timers|list (my |the )?(timers|reminders|alarms)|check (my|on|the) (timer|alarm|reminder)s?)\b",
                 t) and not re.search(r"\bremind me (in|to|at|that)\b", t):
        items = upcoming()
        if not items:
            return "You don't have any timers or reminders."
        return "; ".join(describe(i) for i in items[:4]) + "."

    # set an alarm / remind at a time
    if re.search(r"\b(alarm|wake me)\b", t) or (re.search(r"\bremind", t) and re.search(r"\bat\s+\d", t)):
        when = parse_clock(t, prefer_morning=bool(re.search(r"\bwake me\b", t)))
        if when:
            kind = "alarm" if re.search(r"\b(alarm|wake me)\b", t) else "reminder"
            m = re.search(r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?", t)
            label = _label_after(t, m.group(0) if m else "") if kind == "reminder" else ""
            add(at=when, label=label, kind=kind)
            what = f"to {label[:1].lower() + label[1:]}" if label else ""
            return (f"Alarm set for {say_time(when)}." if kind == "alarm"
                    else f"I'll remind you at {say_time(when)} {what}".strip() + ".")

    # set a timer / remind in X
    seconds, matched = parse_duration(t)
    if seconds:
        if re.search(r"\bremind", t):
            label = _label_after(t, matched)
            add(seconds=seconds, label=label, kind="reminder")
            what = f" to {label[:1].lower() + label[1:]}" if label else ""
            return f"I'll remind you in {say_duration(seconds)}{what}."
        if re.search(r"\btimer\b", t):
            label = _label_after(t, matched)
            label = "" if label.lower() in ("", "a", "an", "timer") else label
            add(seconds=seconds, label=label, kind="timer")
            return f"{label + ' timer' if label else 'Timer'} set for {say_duration(seconds)}."
    return None  # something more complicated: let Claude handle it


# ---------- runs inside Wisp: rings when things are due ----------
class TimerService:
    def __init__(self, on_fire):
        self.on_fire = on_fire

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            now = time.time()
            items = load()
            due = [i for i in items if i["due"] <= now]
            if due:
                ids = {i["id"] for i in due}
                save([i for i in load() if i["id"] not in ids])
                for item in due:
                    item["late"] = now - item["due"]
                    try:
                        self.on_fire(item)
                    except Exception as exc:
                        print(f"(timer error: {exc})")
            time.sleep(0.5)


def fired_message(item):
    if _zh():
        import lang_zh
        return lang_zh.fired_message(item)
    late = item.get("late", 0) > 90
    if item["kind"] == "alarm":
        return f"It's {say_time(item['due'])}. This is your alarm." + (" Sorry, I wasn't running when it was due." if late else "")
    if item["kind"] == "reminder":
        label = item["label"][:1].lower() + item["label"][1:] if item["label"] else "you asked me to remind you"
        return f"Reminder: {label}." + (" (A little late, sorry.)" if late else "")
    length = say_duration(item["length"]) if item.get("length") else ""
    for plural in ("hours", "minutes", "seconds"):  # "10 minute timer", not "10 minutes timer"
        length = length.replace(plural, plural[:-1])
    name = f"{item['label']} timer" if item["label"] else f"{length} timer".strip()
    return f"Your {name} is done."


# ---------- command line (for Claude) ----------
def _cli():
    p = argparse.ArgumentParser(description="Wisp timers")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--in", dest="seconds", type=float, help="seconds from now")
    a.add_argument("--at", help='a time like "17:30" / "5:30pm", or "YYYY-MM-DD HH:MM"')
    a.add_argument("--label", default="")
    a.add_argument("--kind", choices=["timer", "reminder", "alarm"], default=None)
    sub.add_parser("list")
    c = sub.add_parser("cancel")
    c.add_argument("which", help='an id from "list", or "all"')
    args = p.parse_args()

    if args.cmd == "add":
        if args.seconds:
            item = add(seconds=args.seconds, label=args.label, kind=args.kind or "timer")
        elif args.at:
            try:
                when = dt.datetime.strptime(args.at, "%Y-%m-%d %H:%M").timestamp()
            except ValueError:
                when = parse_clock("at " + args.at)
            if not when:
                sys.exit(f"Couldn't understand the time {args.at!r}")
            item = add(at=when, label=args.label, kind=args.kind or "reminder")
        else:
            sys.exit("Give --in SECONDS or --at TIME")
        print(f"Added #{item['id']}: {describe(item)}")
    elif args.cmd == "list":
        items = upcoming()
        print("\n".join(f"#{i['id']} {i['kind']}: {describe(i)}" for i in items) or "No timers.")
    elif args.cmd == "cancel":
        gone = cancel(args.which)
        print(f"Cancelled {len(gone)}.")


if __name__ == "__main__":
    _cli()
