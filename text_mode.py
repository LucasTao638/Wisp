"""Wisp - text version (handy for troubleshooting). The normal app is app.py.

Hold F9 to talk, or type. Start with "in the background" to run a background job.
"""
import sys

import app_info
import background

app_info.ensure_files()
from core import Assistant

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HELP = """Commands:
  /new         start a fresh conversation (memory is kept)
  /jobs        list background jobs
  /bg <task>   run a task in the background
  /stop        stop the current task and the talking
  /quit        exit
Anything else you type (or say) is sent to Claude."""


def emit(kind, text):
    if kind == "user":
        print(f"You: {text}")
    elif kind == "tool":
        print(f"   > {text}")
    elif kind == "reply":
        print("\n" + text)
    elif kind == "say":
        print(f"\nWisp: {text}\n")
    elif kind in ("info", "error"):
        print(f"({text})")
    elif kind == "status" and text in ("listening", "thinking"):
        print(f"[{text}...]")


def show_jobs():
    jobs = background.list_jobs()
    if not jobs:
        print("No background jobs yet.")
    for job in jobs:
        print(f"  {job['id']}  [{job['status']:>7}]  {job['task'][:70]}")
        if job.get("say"):
            print(f"      -> {job['say']}")


def main():
    print("=== Wisp ===")
    assistant = Assistant(emit)
    assistant.start()
    print(HELP)
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        cmd = line.split(" ", 1)[0]
        if cmd == "/quit":
            break
        elif cmd == "/new":
            assistant.new_chat()
        elif cmd == "/jobs":
            show_jobs()
        elif cmd == "/stop":
            assistant.stop()
        elif cmd == "/help":
            print(HELP)
        elif line:
            assistant.submit(line)
    assistant.shutdown()


if __name__ == "__main__":
    main()
