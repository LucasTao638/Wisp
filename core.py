"""Wisp's engine, shared by the app window (app.py) and the text version (text_mode.py).

The front end gives the Assistant an emit(kind, text) function and gets told what's happening:
  "user"    something you said or typed     "tool"   a step Claude is taking
  "reply"   Claude's written answer          "say"    the short spoken answer
  "status"  ready / listening / thinking / speaking / starting
  "info"    a notice                         "error"  something went wrong
  "voice"   "on" or "off" (whether the microphone is usable)
"""
import json
import queue
import random
import re
import sys
import threading
import time
from pathlib import Path

import background
import brain
import context
import focus
import routines
import shortcuts
import telemetry
import timers
from voice import Speaker

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


DEFAULT_ACKS = ["One moment.", "Right away.", "On it.", "Just a moment."]


def _later(seconds, fn):
    """Run fn after a delay without keeping Wisp alive after you quit."""
    t = threading.Timer(seconds, fn)
    t.daemon = True
    t.start()


def _same(a, b):
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return norm(a) == norm(b)


class Assistant:
    def __init__(self, emit):
        self.cfg = load_config()
        self._listeners = [emit]      # the UI, plus the phone remote if it's on
        self.source = "pc"            # where the current request came from: "pc" or "phone"
        self.ui_action = None         # set by the UI, so the phone can e.g. open the HUD
        self.requests = queue.Queue()
        self.busy = threading.Event()
        self.speaker = Speaker(self.cfg)
        self.muted = not self.cfg.get("speak_replies", True)
        self.voice_ready = False
        self.recording = False
        self.hotkeys_active = True  # the UI turns this off while Wisp is hidden
        self._rec_started = 0.0
        self._recorder = self._transcriber = None
        self.wake = None
        self.wake_enabled = True  # can be switched off from the menu
        self.wake_allowed = True  # the UI turns this off during fullscreen games if configured
        self.last_used = 0.0
        self.session = brain.LiveSession(self.cfg, self._load_session())
        self.pending_offer = None

    def emit(self, kind, text):
        for listener in list(self._listeners):
            try:
                listener(kind, text)
            except Exception as exc:
                print(f"(listener error: {exc})")

    def add_listener(self, fn):
        self._listeners.append(fn)

    def _speak_here(self):
        """Speak out loud on the PC? Not for requests from your phone (unless you want that)."""
        return self.source == "pc" or self.cfg.get("phone_replies_on_pc", False)

    # ---------- conversation state ----------
    def _load_session(self):
        """Pick up the last conversation, unless it's been idle too long (then start fresh)."""
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        self.last_used = state.get("last_used", 0)
        if self._conversation_expired():
            return None
        return state.get("session_id")

    def _read_state(self):
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_session(self, **extra):
        state = self._read_state()
        state.update(session_id=self.session.session_id, last_used=self.last_used, **extra)
        STATE.write_text(json.dumps(state), encoding="utf-8")

    def _conversation_expired(self):
        hours = self.cfg.get("new_conversation_after_hours", 3)
        return bool(hours) and self.last_used and time.time() - self.last_used > hours * 3600

    # ---------- start / stop ----------
    def start(self):
        if not brain.write_mcp_config():
            self.emit("info", "App control (Windows-MCP) isn't installed, so I can't click around in apps. Run setup.bat.")
        self.emit("status", "starting")
        telemetry.start(self.cfg)
        threading.Thread(target=self._warm_up, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._start_voice, daemon=True).start()
        timers.TimerService(self._timer_fired).start()
        focus.SessionService(self._session_change).start()
        if self.cfg.get("morning_briefing", True):
            _later(8, self._maybe_offer_briefing)

    # ---------- timers, reminders, alarms ----------
    def _timer_fired(self, item):
        message = timers.fired_message(item)
        self.emit("alert", message)
        background.notify("Wisp", message)
        repeats = 3 if item["kind"] == "alarm" else 1
        self._chime(repeats)
        time.sleep(0.6 * repeats)
        self.speaker.speak(message)  # timers speak even when muted - that's the point of them

    def _chime(self, repeats=1):
        if sys.platform != "win32":
            return
        import winsound

        def play():
            for _ in range(repeats):
                for freq, ms in ((880, 120), (1175, 120), (1568, 220)):
                    winsound.Beep(freq, ms)
                time.sleep(0.15)
        threading.Thread(target=play, daemon=True).start()

    def next_timer(self):
        """(label, seconds left) for the soonest timer, for the HUD - or None."""
        items = timers.upcoming()
        if not items:
            return None
        item = items[0]
        name = item["label"] or item["kind"].title()
        return name, item["due"] - time.time(), item["kind"]

    # ---------- focus sessions ----------
    def _session_change(self, message):
        self.emit("alert", message)
        background.notify("Wisp", message)
        self._chime(1)
        time.sleep(0.6)
        self.speaker.speak(message)  # like timers, these speak even when muted

    def _warm_up(self):
        try:
            self.session.warm_up()
        except Exception as exc:
            self.emit("error", str(exc))
        if not self.busy.is_set():
            self.emit("status", "ready")

    def shutdown(self):
        self.speaker.stop()
        self.session.stop()

    def stop(self):
        """Stop talking, and cancel the current task if there is one."""
        self.speaker.stop()
        if self.busy.is_set():
            self.session.stop()  # restarts automatically on the next request
            self.emit("info", "Stopped.")

    def new_chat(self):
        self.session.reset()
        self._save_session()
        threading.Thread(target=self._warm_up, daemon=True).start()
        self.emit("info", "Started a fresh conversation. (Things saved to memory are kept.)")

    def set_muted(self, muted):
        self.muted = muted
        if muted:
            self.speaker.stop()

    # ---------- requests ----------
    def submit(self, text, source="pc"):
        text = text.strip()
        if not text:
            return
        if text.startswith("/bg "):
            text = "in the background " + text[4:]
        self.emit("user", text)
        if self.busy.is_set():
            self.emit("info", "Queued - I'll do it after the current task.")
        self.requests.put((text, source))

    def _worker(self):
        while True:
            text, self.source = self.requests.get()
            try:
                self._handle(text)
            except Exception as exc:
                self.emit("error", f"Error: {exc}")
                self.emit("status", "ready")

    def _idle_status(self):
        return "thinking" if self.busy.is_set() else "ready"

    def _say(self, text):
        self.emit("say", text)
        if not self.muted and text and self._speak_here():
            self.emit("status", "speaking")

            def done():
                self.emit("status", self._idle_status())
                if self._is_question(text) and self.source == "pc":
                    self._follow_up()
            self.speaker.speak(text, on_done=done)
        else:
            self.emit("status", self._idle_status())

    def say_now(self, text):
        """Say something and wait until it's been said (used by routines)."""
        self.emit("say", text)
        if self.muted or not self._speak_here():
            return
        done = threading.Event()
        self.emit("status", "speaking")
        self.speaker.speak(text, on_done=done.set)
        done.wait(30)
        self.emit("status", self._idle_status())

    # ---------- morning briefing ----------
    def _maybe_offer_briefing(self):
        """The first time Wisp runs each morning, offer a briefing (the mic opens for your answer)."""
        hour = time.localtime().tm_hour
        today = time.strftime("%Y-%m-%d")
        if not (5 <= hour < 12) or self._read_state().get("last_briefing") == today or self.busy.is_set():
            return
        self._save_session(last_briefing=today)
        self.pending_offer = ("briefing", time.time() + 90)
        name = self.cfg.get("user_name")
        self._say(f"Good morning{', ' + name if name else ''}. Would you like your briefing?")

    def _briefing_prompt(self):
        now = time.localtime()
        lines = [f"Today is {time.strftime('%A %d %B %Y', now)}, it's {time.strftime('%I:%M %p', now).lstrip('0')}."]
        upcoming = [i for i in timers.upcoming() if i["due"] - time.time() < 24 * 3600]
        if upcoming:
            lines.append("Timers/reminders in the next 24 hours: " + "; ".join(timers.describe(i) for i in upcoming))
        finished = [j for j in background.list_jobs(limit=10)
                    if j.get("finished") and j["finished"][:10] >= time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))]
        if finished:
            lines.append("Background jobs finished recently: " + "; ".join(f"{j['task'][:60]} ({j['status']})" for j in finished))
        if focus.session_text():
            lines.append(f"Focus session running: {focus.session_text()}")
        return ("[MORNING BRIEFING] Give the user a short spoken morning briefing (about 4 sentences in the SAY line, "
                "details below it): greet them; today's weather for their city if MEMORY.md says where they live "
                "(search the web for today's forecast); anything in memory that matters today; then the local info "
                "below. If you don't know their city, skip the weather and ask which city they're in so you can "
                "remember it.\n\nLocal info:\n- " + "\n- ".join(lines))

    # ---------- usage limits and errors ----------
    @staticmethod
    def _friendly_error(result):
        raw = f"{result.get('error', '')} {result.get('text', '')}"
        low = raw.lower()
        if "limit" in low and ("usage" in low or "reached" in low or "reset" in low or "rate" in low):
            m = re.search(r"\|(\d{10})\b", raw)
            when = ""
            if m:
                when = f" It resets at {time.strftime('%I:%M %p', time.localtime(int(m.group(1)))).lstrip('0')}."
            else:
                m = re.search(r"resets?\s+(?:at\s+)?([0-9:]+\s*[ap]m)", low)
                if m:
                    when = f" It resets at {m.group(1)}."
            return ("You've hit your Claude usage limit, so I can't think for a bit." + when +
                    " Timers, routines and quick commands still work.")
        if "not logged in" in low or "login" in low or "authenticat" in low or "/login" in low:
            return "Claude Code isn't logged in. Open Command Prompt, type claude, and log in again."
        if "network" in low or "connection" in low or "timed out" in low or "enotfound" in low:
            return "I couldn't reach Claude. Check your internet connection."
        return None

    @staticmethod
    def _is_question(text):
        return text.strip().strip("\"'”’)").endswith("?")

    def _follow_up(self):
        """Wisp asked something: open the mic so you can just answer (closes again if you say nothing)."""
        if not self.cfg.get("follow_up_listening", True) or not self.wake or self.recording \
                or not self.wake_allowed:
            return

        def go():
            for _ in range(600):  # if Claude is still finishing the written part, wait for it (max 60s)
                if not self.busy.is_set():
                    break
                time.sleep(0.1)
            if self.busy.is_set() or self.speaker.speaking or self.is_listening:
                return
            if self.cfg.get("wake_chime", True) and sys.platform == "win32":
                import winsound
                winsound.Beep(988, 70)  # a soft, short blip: "I'm listening"
            time.sleep(0.15)  # let the chime finish so it isn't recorded
            if self.speaker.speaking or self.busy.is_set() or self.is_listening:
                return
            self.emit("status", "listening")
            self.wake.listen_now(self.cfg.get("follow_up_seconds", 6))
        threading.Thread(target=go, daemon=True).start()

    def background_task_from(self, text):
        lowered = text.lower().strip()
        for prefix in self.cfg.get("background_prefixes", []):
            if lowered.startswith(prefix):
                return re.sub(r"^[\s,:.\-]+", "", text.strip()[len(prefix):]) or None
        return None

    def _handle(self, text):
        # an answer to "Would you like your briefing?"
        offer = getattr(self, "pending_offer", None)
        self.pending_offer = None
        if offer and time.time() < offer[1]:
            t = re.sub(r"[^a-z ]", "", text.lower()).strip()
            if re.fullmatch(r"(yes|yeah|yep|yup|sure|ok|okay|please|go ahead|go on|yes please|sure thing|do it|"
                            r"go for it|absolutely|of course)( please| thanks| thank you)?", t):
                text = self._briefing_prompt()
                telemetry.feature("briefing")
            elif re.fullmatch(r"(no|nope|nah|not now|no thanks|no thank you|maybe later|later|skip( it)?)", t):
                self._say("Very well.")
                return

        if re.fullmatch(r"(good morning|morning|brief me|(give me )?(my |the )?(morning |daily )?briefing|"
                        r"what'?s (on )?(my day|today)( looking like)?)", re.sub(r"[^a-z' ]", "", text.lower()).strip()):
            text = self._briefing_prompt()
            telemetry.feature("briefing")

        internal = text.startswith("[MORNING BRIEFING]")  # our own prompt: straight to Claude
        task = None if internal else self.background_task_from(text)
        if task:
            job_id = background.start_job(task)
            telemetry.feature("background_job")
            self._say(f"Okay, I'm working on that in the background. Job {job_id}.")
            return

        found = None if internal else routines.find(text)
        if found:
            name, routine = found
            self.emit("tool", f"Routine  {name}")
            telemetry.feature("routine")
            routines.run(routine, self)
            self.emit("status", self._idle_status())
            return

        if not internal:
            reply = routines.handle_command(text)  # "what routines do I have", "delete the X routine"
            if reply:
                self._say(reply)
                return
            build = routines.builder_prompt(text)  # "when I say X, do Y" -> Claude writes the routine
            if build:
                self.emit("tool", "Routine  setting it up")
                telemetry.feature("routine_created")
                text, internal = build, True

        if self.cfg.get("instant_shortcuts", True) and not internal:
            quick = None
            for kind, handler in (("timer", timers.handle_command), ("focus_session", focus.handle_command),
                                  ("shortcut", shortcuts.try_shortcut)):
                quick = handler(text)
                if quick:
                    telemetry.feature(kind)
                    break
            if quick:
                self._say(quick)
                return

        # mentions of your screen or clipboard: give Claude a screenshot / what you copied
        text, note = (text, None) if internal else context.enrich(text)
        if note:
            self.emit("tool", note)
            telemetry.feature("clipboard" if "clipboard" in note.lower() or "copied" in note.lower() else "screen")

        if self._conversation_expired():
            self.session.reset()
            self.emit("info", "It's been a while, so I started a fresh conversation. (Memory is kept.)")

        self.busy.set()
        self.emit("status", "thinking")
        telemetry.feature("ask_claude")
        started = time.time()
        spoken_early = []

        def on_event(kind, detail):
            if kind == "tool":
                self.emit("tool", detail)
            elif kind == "say":
                # The spoken line arrived while Claude is still writing - say it right away.
                spoken_early.append(detail)
                self._say(detail)

        self._schedule_ack(spoken_early)
        try:
            result = self.session.ask(text, on_event=on_event)
        finally:
            self.busy.clear()
        self.last_used = time.time()
        self._save_session()
        took = f"took {time.time() - started:.1f}s"
        friendly = self._friendly_error(result) if not result["ok"] else None
        if friendly or not result["text"]:
            message = friendly or "Something went wrong, sorry. The details are in wisp.log."
            print(f"(Claude error: {result.get('error')} | {result.get('text', '')[:500]})")
            self.emit("error", message)
            if not self.muted and self._speak_here():
                self.speaker.speak(message)
            self.emit("status", "ready")
            return
        spoken, body = brain.split_say(result["text"])
        self.emit("reply", body)
        self.emit("info", took)
        if spoken_early and _same(spoken, spoken_early[-1]):
            if not self.speaker.speaking:
                self.emit("status", "ready")
            return  # already said it
        self._say(spoken)

    def _schedule_ack(self, spoken_early):
        """If Claude is taking a while, say a short 'One moment' so you know it heard you."""
        delay = self.cfg.get("thinking_ack_after", 2.0)
        phrases = self.cfg.get("thinking_acks", DEFAULT_ACKS)
        if not delay or not phrases or self.muted or not self._speak_here():
            return

        def ack():
            if self.busy.is_set() and not spoken_early and not self.speaker.speaking:
                self.speaker.speak(random.choice(phrases))
        _later(delay, ack)

    # ---------- for animations ----------
    @property
    def mic_level(self):
        if self.wake and self.wake.capturing:
            return self.wake.level
        return self._recorder.level if (self._recorder and self.recording) else 0.0

    @property
    def is_listening(self):
        return self.recording or bool(self.wake and self.wake.capturing)

    @property
    def is_speaking(self):
        return self.speaker.speaking

    def toggle_listening(self):
        if self.wake and self.wake.capturing:
            self.wake.cancel()
            self.emit("status", "thinking" if self.busy.is_set() else "ready")
        elif self.recording:
            self.stop_listening()
        else:
            self.start_listening()

    # ---------- voice ----------
    def _start_voice(self):
        try:
            from voice import Recorder, Transcriber
            self.emit("info", f"Loading speech model '{self.cfg['whisper_model']}' (the first run downloads it)...")
            self._transcriber = Transcriber(self.cfg["whisper_model"])
            self._recorder = Recorder()
        except Exception as exc:
            self.emit("info", f"Voice is off ({exc}). You can still type.")
            self.emit("voice", "off")
            return
        self.voice_ready = True
        self.emit("voice", "on")
        self.speaker.precache(self.cfg.get("thinking_acks", DEFAULT_ACKS) + ["Yes?", "Didn't catch that."])
        try:
            import keyboard
            talk_key = self.cfg.get("talk_key", "f9")
            keyboard.on_press_key(talk_key, lambda _: self.hotkeys_active and self.start_listening())
            keyboard.on_release_key(talk_key, lambda _: self.stop_listening())
            keyboard.add_hotkey(self.cfg.get("stop_key", "f10"), self.stop)
            self.emit("info", f"Voice ready: hold {talk_key.upper()} (or the mic button) to talk.")
        except Exception as exc:
            self.emit("info", f"Hotkeys are off ({exc}). Use the mic button instead.")
        self._start_wake_word()

    def _start_wake_word(self):
        name = self.cfg.get("wake_word", "hey_jarvis")
        if not name:
            return
        from voice import WakeListener
        listener = WakeListener(
            name, self.cfg.get("wake_sensitivity", 0.5), self.cfg.get("end_of_speech_pause", 0.8),
            is_paused=lambda: self.recording or not self.wake_enabled or not self.wake_allowed,
            on_wake=self._on_wake,
            on_command=lambda audio: self._transcribe_and_submit(audio, wake=True),
            on_nothing=lambda: self.emit("status", "thinking" if self.busy.is_set() else "ready"),
        )
        try:
            listener.load()
            listener.start()
        except ImportError:
            self.emit("info", "Wake word is off: run  py -V:3.13 -m pip install openwakeword")
            return
        except Exception as exc:
            self.emit("info", f"Wake word is off ({exc}).")
            return
        self.wake = listener
        self.emit("info", f"Say \u201c{name.replace('_', ' ').title()}\u201d any time to talk.")

    def _on_wake(self):
        telemetry.feature("wake_word")
        self.speaker.stop()
        self.emit("status", "listening")
        self.emit("wake", "")
        if self.cfg.get("wake_chime", True) and sys.platform == "win32":
            import winsound
            threading.Thread(target=lambda: winsound.Beep(1175, 90), daemon=True).start()

    def start_listening(self):
        if not self.voice_ready or self.recording:
            return  # also ignores key auto-repeat
        if self.wake and self.wake.capturing:
            self.wake.cancel()
        self.speaker.stop()
        telemetry.feature("push_to_talk")
        self.recording = True
        self._rec_started = time.time()
        self._recorder.start()
        self.emit("status", "listening")

    def stop_listening(self):
        if not self.recording:
            return
        self.recording = False
        audio = self._recorder.stop()
        if time.time() - self._rec_started < 0.4:
            self.emit("status", "thinking" if self.busy.is_set() else "ready")
            return

        self._transcribe_and_submit(audio)

    def _transcribe_and_submit(self, audio, wake=False):
        def transcribe():
            text = self._transcriber.transcribe(audio)
            if wake:
                from voice import strip_wake_words
                text = strip_wake_words(text)
            if text:
                self.submit(text)
            else:
                self.emit("info", "Didn't catch that.")
                self.emit("status", "thinking" if self.busy.is_set() else "ready")
        threading.Thread(target=transcribe, daemon=True).start()
