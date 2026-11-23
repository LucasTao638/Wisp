"""Background jobs: tasks that run in their own process while you keep using your PC.

Each job gets jobs/<id>.json (status + result) and jobs/<id>.log (live progress).
You get a Windows notification when a job finishes.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import brain

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
JOBS.mkdir(exist_ok=True)

BACKGROUND_NOTE = (
    "[BACKGROUND JOB] You are running in the background. The user is NOT watching and "
    "can't answer questions, so don't ask any: make sensible choices and list them at the end. "
    "Don't use the mouse or keyboard on the user's screen. Save any files you make in the "
    "output folder unless the task says where. Finish with a short summary and a SAY: line.\n\n"
    "Task: "
)

DETACHED = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW


def _path(job_id, ext="json"):
    return JOBS / f"{job_id}.{ext}"


def _save(job):
    _path(job["id"]).write_text(json.dumps(job, indent=2), encoding="utf-8")


def load(job_id):
    return json.loads(_path(job_id).read_text(encoding="utf-8"))


def start_job(task):
    job_id = time.strftime("%Y%m%d-%H%M%S")
    _save({"id": job_id, "task": task, "status": "queued",
           "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    kwargs = {"creationflags": DETACHED} if sys.platform == "win32" else {"start_new_session": True}
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", job_id],
                     cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, **kwargs)
    return job_id


def list_jobs(limit=10):
    jobs = []
    for f in sorted(JOBS.glob("*.json"), reverse=True)[:limit]:
        try:
            jobs.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return jobs


def notify(title, message):
    try:
        from win11toast import notify as toast
        toast(title, message)
    except Exception:
        print(f"[{title}] {message}")


def run_job(job_id):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    job = load(job_id)
    job["status"] = "running"
    _save(job)
    log = _path(job_id, "log").open("a", encoding="utf-8")

    def on_event(kind, text):
        log.write(f"{time.strftime('%H:%M:%S')} {kind.upper()}: {text}\n")
        log.flush()

    try:
        res = brain.run_claude(BACKGROUND_NOTE + job["task"], cfg, on_event=on_event, background=True)
        say, body = brain.split_say(res["text"])
        job.update(status="done" if res["ok"] else "failed", result=body, say=say,
                   error=res["error"], session_id=res["session_id"])
    except Exception as exc:  # keep a record even if something breaks
        job.update(status="failed", error=str(exc), say="The background job failed.")
    job["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save(job)
    log.close()
    notify(f"Wisp job {job['status']}", job.get("say") or job["task"][:100])


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "run":
    run_job(sys.argv[2])
