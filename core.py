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
import threading
import time
from pathlib import Path

import background
import brain
import context
import focus
import routines
import i18n
import shortcuts
import sysplat
import telemetry
import timers
from voice import Speaker

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


DEFAULT_ACKS = ["One moment.", "Right away.", "On it.", "Just a moment."]
t = i18n.t


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
        i18n.load_language()
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
        self._stop_gen = 0            # goes up every time you interrupt, so a stopped request stays quiet

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
            self.emit("info", t("app_control_missing"))
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
        sysplat.chime("alert", repeats)

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

    def stop(self, quiet=False):
        """Interrupt: stop talking, stop listening, cancel the current task and anything waiting."""
        self._stop_gen += 1
        self.speaker.stop()
        was_busy = self.busy.is_set()
        while True:                      # drop requests that were waiting their turn
            try:
                self.requests.get_nowait()
            except queue.Empty:
                break
        if self.wake and self.wake.capturing:
            self.wake.cancel()
        if self.recording:
            self.recording = False
            self._recorder.stop()
        if was_busy:
            self.session.stop()  # ends Claude Code and anything it started; restarts on the next request
        if not quiet:
            self.emit("info", t("stopped"))
        self.emit("status", "ready")

    def new_chat(self):
        self.session.reset()
        self._save_session()
        threading.Thread(target=self._warm_up, daemon=True).start()
        self.emit("info", t("new_chat"))

    def set_muted(self, muted):
        self.muted = muted
        if muted:
            self.speaker.stop()

    # ---------- requests ----------
    def submit(self, text, source="pc", spoken=False):
        text = text.strip()
        if not text:
            return
        if text.startswith("/bg "):
            text = "in the background " + text[4:]
        if spoken and self.is_stop_phrase(text):     # "stop", "never mind", "别说了"...
            self.stop()
            return
        self.emit("user", text)
        if self.busy.is_set():
            if spoken and self.cfg.get("talking_interrupts", True):
                self.stop(quiet=True)   # you started a new request by talking: drop the old one
                self.emit("info", t("stopped"))
            else:
                self.emit("info", t("queued"))
        self.requests.put((text, source))

    @staticmethod
    def is_stop_phrase(text):
        words = re.sub(r"[^\w' ]", " ", text.lower()).split()
        phrase = " ".join(w for w in words if w not in ("jarvis", "wisp", "hey", "please", "ok", "okay"))
        return phrase in ("stop", "stop it", "stop that", "stop talking", "cancel", "cancel that", "never mind",
                          "nevermind", "be quiet", "quiet", "shut up", "that's enough", "thats enough", "enough",
                          "forget it", "hold on", "wait", "abort") \
            or text.strip("。.！! ") in ("停", "停下", "停止", "别说了", "算了", "取消", "等一下", "安静")

    def _worker(self):
        while True:
            text, self.source = self.requests.get()
            try:
                self._handle(text)
            except Exception as exc:
                self.emit("error", t("error_generic", error=exc))
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
        self._say(t("briefing_offer", name=(", " if not i18n.is_zh() else "，") + name if name else ""))

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
                when = t("usage_limit_when", time=time.strftime("%H:%M", time.localtime(int(m.group(1)))))
            else:
                m = re.search(r"resets?\s+(?:at\s+)?([0-9:]+\s*[ap]m)", low)
                if m:
                    when = t("usage_limit_when", time=m.group(1))
            return t("usage_limit", when=when)
        if "not logged in" in low or "login" in low or "authenticat" in low or "/login" in low:
            return t("not_logged_in")
        if "network" in low or "connection" in low or "timed out" in low or "enotfound" in low:
            return t("no_internet")
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
            if self.cfg.get("wake_chime", True):
                sysplat.chime("blip")  # a soft, short blip: "I'm listening"
            time.sleep(0.15)  # let the chime finish so it isn't recorded
            if self.speaker.speaking or self.busy.is_set() or self.is_listening:
                return
            self.emit("status", "listening")
            self.wake.listen_now(self.cfg.get("follow_up_seconds", 6))
        threading.Thread(target=go, daemon=True).start()

    @staticmethod
    def feedback_request(text):
        """'I have a suggestion: ...' / 'send feedback ...' -> the feedback text (may be empty), else None."""
        m = re.match(r"^(?:hey |ok )?(?:jarvis|wisp)?[, ]*(?:i (?:have|want to (?:give|send|leave)|'d like to (?:give|send|leave)) "
                     r"(?:a |some )?(?:suggestion|feedback|idea for (?:you|wisp))|send (?:some )?feedback|"
                     r"report a (?:bug|problem)|give feedback|feedback)\b[:,.\s-]*(.*)$", text.strip(), re.IGNORECASE)
        return m.group(1).strip() if m else None

    def background_task_from(self, text):
        lowered = text.lower().strip()
        for prefix in self.cfg.get("background_prefixes", []):
            if lowered.startswith(prefix):
                return re.sub(r"^[\s,:.\-]+", "", text.strip()[len(prefix):]) or None
        return None

    def _handle(self, text):
        zh = i18n.is_zh()
        if zh:
            import lang_zh

        # an answer to "Would you like your briefing?"
        offer = getattr(self, "pending_offer", None)
        self.pending_offer = None
        if offer and time.time() < offer[1]:
            words = re.sub(r"[^a-z ]", "", text.lower()).strip()
            said_yes = re.fullmatch(r"(yes|yeah|yep|yup|sure|ok|okay|please|go ahead|go on|yes please|sure thing|"
                                    r"do it|go for it|absolutely|of course)( please| thanks| thank you)?", words)
            said_no = re.fullmatch(r"(no|nope|nah|not now|no thanks|no thank you|maybe later|later|skip( it)?)", words)
            if said_yes or (zh and lang_zh.is_yes(text)):
                text = self._briefing_prompt()
                telemetry.feature("briefing")
            elif said_no or (zh and lang_zh.is_no(text)):
                self._say(t("very_well"))
                return

        plain = re.sub(r"[^a-z' ]", "", text.lower()).strip()
        if re.fullmatch(r"(good morning|morning|brief me|(give me )?(my |the )?(morning |daily )?briefing|"
                        r"what'?s (on )?(my day|today)( looking like)?)", plain) or (zh and lang_zh.is_briefing(text)):
            text = self._briefing_prompt()
            telemetry.feature("briefing")

        internal = text.startswith("[MORNING BRIEFING]")  # our own prompt: straight to Claude

        # "I have a suggestion: ..." -> open the feedback form, filled in (you check it, then press Send)
        if not internal:
            feedback_text = self.feedback_request(text) if not zh else (
                lang_zh.wants_feedback(text) if lang_zh.wants_feedback(text) is not None else self.feedback_request(text))
            if feedback_text is not None:
                if self.ui_action:
                    self.ui_action(("feedback", feedback_text))
                    self._say(t("feedback_opened"))
                    return

        task = None if internal else (self.background_task_from(text) or (zh and lang_zh.background_task(text)) or None)
        if task:
            job_id = background.start_job(task)
            telemetry.feature("background_job")
            self._say(t("background_started", job=job_id))
            return

        found = None if internal else routines.find(text)
        if found:
            name, routine = found
            self.emit("tool", f"Routine  {name}")
            telemetry.feature("routine")
            routines.run(routine, self)
            self.emit("status", self._idle_status())
            return

        if not internal and self.cfg.get("instant_shortcuts", True) and zh:
            quick = lang_zh.handle_command(text)  # Chinese timers, focus, routines list/delete, open apps
            if quick:
                telemetry.feature(quick[1])
                self._say(quick[0])
                return

        if not internal:
            reply = routines.handle_command(text)  # "what routines do I have", "delete the X routine"
            if reply:
                self._say(reply)
                return
            build = routines.builder_prompt(text, force=bool(zh and lang_zh.wants_routine_builder(text)))
            if build:  # "when I say X, do Y" -> Claude writes the routine
                self.emit("tool", f"Routine  {t('routine_building')}")
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
            self.emit("info", t("conversation_reset"))

        self.busy.set()
        gen = self._stop_gen
        self.emit("status", "thinking")
        telemetry.feature("ask_claude")
        started = time.time()
        spoken_early = []

        def on_event(kind, detail):
            if kind == "tool":
                self.emit("tool", detail)
            elif kind == "say" and gen == self._stop_gen:
                # The spoken line arrived while Claude is still writing - say it right away.
                spoken_early.append(detail)
                self._say(detail)

        self._schedule_ack(spoken_early, gen)
        try:
            result = self.session.ask(text, on_event=on_event)
        finally:
            self.busy.clear()
        if gen != self._stop_gen:   # you interrupted it: no error message, no reply
            self._save_session()
            if self.requests.empty():
                self.emit("status", "ready")
            return
        self.last_used = time.time()
        self._save_session()
        took = t("took", seconds=f"{time.time() - started:.1f}")
        friendly = self._friendly_error(result) if not result["ok"] else None
        if friendly or not result["text"]:
            message = friendly or t("something_wrong")
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

    def _schedule_ack(self, spoken_early, gen):
        """If Claude is taking a while, say a short 'One moment' so you know it heard you."""
        delay = self.cfg.get("thinking_ack_after", 2.0)
        phrases = self.cfg.get("thinking_acks", DEFAULT_ACKS)
        if not delay or not phrases or self.muted or not self._speak_here():
            return

        def ack():
            if self.busy.is_set() and gen == self._stop_gen and not spoken_early and not self.speaker.speaking \
                    and not self.is_listening:
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
            self.emit("info", t("loading_speech", model=self.cfg["whisper_model"]))
            self._transcriber = Transcriber(self.cfg["whisper_model"], i18n.LANG)
            self._recorder = Recorder()
        except Exception as exc:
            self.emit("info", t("voice_off", error=exc))
            self.emit("voice", "off")
            return
        self.voice_ready = True
        self.emit("voice", "on")
        self.speaker.precache(self.cfg.get("thinking_acks", DEFAULT_ACKS) + [t("yes"), t("didnt_catch")])
        try:
            import hotkeys
            talk_key = self.cfg.get("talk_key", "f9")
            hotkeys.on_hold(talk_key, lambda: self.hotkeys_active and self.start_listening(), self.stop_listening)
            hotkeys.add_hotkey(self.cfg.get("stop_key", "f10"), self.stop)
            self.emit("info", t("voice_ready", key=hotkeys.label(talk_key)))
        except Exception as exc:
            self.emit("info", t("hotkeys_off", error=exc))
        self._start_wake_word()

    def _start_wake_word(self):
        name = self.cfg.get("wake_word", "hey_jarvis")
        if not name:
            return
        from voice import WakeListener
        listener = WakeListener(
            name, self.cfg.get("wake_sensitivity", 0.5), self.cfg.get("finished_talking_pause", 1.2),
            is_paused=lambda: self.recording or not self.wake_enabled or not self.wake_allowed,
            on_wake=self._on_wake,
            on_command=lambda audio, text: self._transcribe_and_submit(audio, wake=True, text=text),
            check_finished=self._check_finished if self.cfg.get("wait_for_unfinished", True) else None,
            on_nothing=lambda: self.emit("status", "thinking" if self.busy.is_set() else "ready"),
        )
        try:
            listener.load()
            listener.start()
        except ImportError:
            self.emit("info", t("wake_missing"))
            return
        except Exception as exc:
            self.emit("info", t("wake_off", error=exc))
            return
        self.wake = listener
        self.emit("info", t("wake_ready", phrase=name.replace("_", " ").title()))

    def _on_wake(self):
        telemetry.feature("wake_word")
        self.speaker.stop()
        self.emit("status", "listening")
        self.emit("wake", "")
        if self.cfg.get("wake_chime", True):
            sysplat.chime("wake")

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

    def _check_finished(self, audio):
        """Called when you pause: have you actually finished? (runs on the listening thread)"""
        from voice import sounds_unfinished, strip_wake_words
        try:
            text = strip_wake_words(self._transcriber.transcribe(audio))
        except Exception:
            return True, None
        if text:
            self.emit("hearing", text)   # shows what's been heard so far
        return not sounds_unfinished(text, i18n.LANG), text

    def _transcribe_and_submit(self, audio, wake=False, text=None):
        def transcribe():
            said = text if text is not None else self._transcriber.transcribe(audio)
            if wake:
                from voice import strip_wake_words
                said = strip_wake_words(said)
            if said:
                self.submit(said, spoken=True)
            else:
                self.emit("info", t("didnt_catch"))
                self.emit("status", "thinking" if self.busy.is_set() else "ready")
        threading.Thread(target=transcribe, daemon=True).start()
