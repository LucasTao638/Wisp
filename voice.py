"""Voice in (push-to-talk + local Whisper) and voice out (Microsoft neural voices, or built-in Windows voices).

Test a voice:   py -V:3.13 voice.py "Good evening. All systems are online."
"""
import asyncio
import json
import os
import collections
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

import sysplat

SAMPLE_RATE = 16000


class Recorder:
    """Records from the default microphone between start() and stop(). .level = current loudness 0..1"""

    def __init__(self):
        import numpy as np
        import sounddevice as sd  # imported here so typing-only mode works without a mic
        self._np, self._sd = np, sd
        self._chunks = []
        self._stream = None
        self.level = 0.0

    def _callback(self, data, *_):
        self._chunks.append(data.copy())
        self.level = min(1.0, float(self._np.sqrt(self._np.mean(data ** 2))) * 12)

    def start(self):
        self._chunks = []
        self._stream = self._sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                            callback=self._callback)
        self._stream.start()

    def stop(self):
        self.level = 0.0
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._chunks:
            return self._np.zeros(0, dtype="float32")
        return self._np.concatenate(self._chunks).flatten()


class Transcriber:
    """Speech-to-text with faster-whisper. Runs on your CPU, free, works offline after first download."""

    def __init__(self, model_name="base.en", language="en"):
        from faster_whisper import WhisperModel
        self.language = language
        if language != "en" and model_name.endswith(".en"):  # ".en" models only understand English
            model_name = "small"
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
        self._lock = threading.Lock()   # the mic and the phone can both ask at once

    def transcribe(self, audio):
        with self._lock:
            return self._transcribe(audio)

    def _transcribe(self, audio):
        if self.language == "zh":
            # The prompt nudges Whisper towards Simplified characters and punctuation.
            segments, _ = self.model.transcribe(audio, language="zh", vad_filter=True, beam_size=1,
                                                without_timestamps=True, condition_on_previous_text=False,
                                                initial_prompt="以下是普通话的句子，使用简体中文。")
            return to_simplified("".join(s.text.strip() for s in segments).strip())
        segments, _ = self.model.transcribe(audio, language="en", vad_filter=True, beam_size=1,
                                            without_timestamps=True, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()


# Common Traditional -> Simplified characters Whisper sometimes produces (not a full converter).
_T2S = str.maketrans("們個這說話時間鐘點們設計鬧響後臺開關幫記讓請問麼為還沒會對嗎錯誤電腦網頁裡聽寫讀發給線視頻"
                     "鬆龍鳥歡氣動學習書車東門見長風飛馬魚麼於與從來過們國實現應該當覺經幾頭樂應",
                     "们个这说话时间钟点们设计闹响后台开关帮记让请问么为还没会对吗错误电脑网页里听写读发给线视频"
                     "松龙鸟欢气动学习书车东门见长风飞马鱼么于与从来过们国实现应该当觉经几头乐应")


def to_simplified(text):
    return text.translate(_T2S)


# ---------------- Wisp's "composed AI" voice ----------------
def _shift(value, amount, unit):
    """'+8%' shifted by -5 -> '+3%'."""
    try:
        n = int(str(value).replace(unit, "").strip() or 0) + amount
    except ValueError:
        n = amount
    return f"{n:+d}{unit}"


def ai_voice_effect(x, sr):
    """Gives the neural voice a subtle synthetic, composed quality - like an AI speaking through a good
    speaker system - while keeping every word clear. x: mono float32 samples. Returns processed samples."""
    import numpy as np
    x = x.astype(np.float32)
    # 1. clean low end: remove a ~110 Hz moving average (a fast, gentle high-pass)
    n = max(1, int(sr / 110))
    csum = np.cumsum(np.concatenate([np.zeros(n, dtype=np.float64), x.astype(np.float64)]))
    x = (x - ((csum[n:] - csum[:-n]) / n)).astype(np.float32)

    def delayed(sig, seconds, gain):
        d = int(sr * seconds)
        out = np.zeros(len(sig) + d, dtype=np.float32)
        out[d:] = sig * gain
        return out

    tail = int(sr * 0.35)
    y = np.zeros(len(x) + tail, dtype=np.float32)
    y[:len(x)] += x
    # 2. a faint metallic edge: a very short echo (comb) a few milliseconds behind
    edge = delayed(x, 0.0048, 0.22)
    y[:len(edge)] += edge[:len(y)]
    # 3. a small sense of space: early reflections, then a soft decaying tail
    for secs, gain in ((0.017, 0.13), (0.029, 0.10), (0.043, 0.075), (0.061, 0.055), (0.083, 0.04)):
        r = delayed(x, secs, gain)
        y[:len(r)] += r[:len(y)]
    fb = np.zeros_like(y)
    d = int(sr * 0.047)
    for start in range(d, len(y), d):   # feedback comb for the tail, very quiet (a block at a time)
        end = min(start + d, len(y))
        fb[start:end] = y[start - d:end - d] * 0.05 + fb[start - d:end - d] * 0.45
    y += fb
    # 4. level it out without clipping
    peak = float(np.max(np.abs(y))) or 1.0
    return (y / peak * 0.89).astype(np.float32)


def ai_voice(mp3_path):
    """The mp3 from the neural voice -> a processed wav (cached). Falls back to the mp3 if anything fails."""
    wav_path = mp3_path[:-4] + ".ai.wav"
    if os.path.exists(wav_path):
        return wav_path
    try:
        import av
        import numpy as np
        with av.open(mp3_path) as container:
            stream = container.streams.audio[0]
            sr = stream.rate or 24000
            chunks = [frame.to_ndarray() for frame in container.decode(stream)]
        samples = np.concatenate([c.reshape(c.shape[0], -1).mean(axis=0) if c.ndim > 1 else c for c in chunks])
        if samples.dtype.kind == "i":
            samples = samples / 32768.0
        y = ai_voice_effect(samples, sr)
        _write_wav(wav_path, y, sr)
        return wav_path
    except Exception as exc:
        print(f"(voice effect skipped: {exc})")
        return mp3_path


def _write_wav(path, samples, sr):
    import wave
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    tmp = path + ".part"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm)
    os.replace(tmp, path)


# ---------------- knowing when you've finished talking ----------------
_TRAILING_EN = {"and", "or", "but", "so", "because", "then", "the", "a", "an", "to", "of", "with", "for", "in", "on",
                "at", "from", "about", "like", "um", "uh", "er", "erm", "hmm", "if", "when", "that", "which", "my",
                "your", "is", "are", "can", "could", "would", "please", "also", "plus", "and then", "as well as"}
_TRAILING_ZH = ("然后", "还有", "和", "跟", "就是", "那个", "这个", "嗯", "呃", "因为", "所以", "但是", "而且", "或者",
                "如果", "的", "把", "给", "帮我", "再")


def complete_sentence(text):
    """A clearly finished request: ends with . ? ! (or 。？！) and has a few words."""
    t = (text or "").strip()
    if not t or sounds_unfinished(t, "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in t) else "en"):
        return False
    if t.endswith(("?", "？", "!", "！", "。")):
        return len(t) >= 4
    return t.endswith(".") and len(t.split()) >= 3 and not t.endswith("...")


def sounds_unfinished(text, lang="en"):
    """True if a sentence was clearly cut off mid-thought ("open Spotify and...")."""
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith(("...", "…", ",", "，", "、", "-", "—")):
        return True
    if lang == "zh":
        return t.rstrip("。.！!？? ").endswith(_TRAILING_ZH)
    words = re.sub(r"[^a-z' ]", " ", t.lower()).split()
    if not words:
        return False
    return words[-1] in _TRAILING_EN or " ".join(words[-2:]) in _TRAILING_EN


# ---------------- wake word ("hey jarvis") ----------------
class WakeListener:
    """Listens all the time for a wake word using openWakeWord (free, runs on your PC, nothing is sent
    anywhere). After the wake word, it records until you've finished talking, then hands over the audio.

    is_paused():            return True to ignore the wake word (e.g. while hidden or push-to-talk is on)
    on_wake():              called when the wake word is heard
    on_command(audio, text): called with the recorded request (float32 numpy array, 16 kHz) and, if
                            check_finished was given, what was said (otherwise text is None)
    on_nothing():           called if you said the wake word and then nothing
    check_finished(audio):  optional - returns (finished, text). Used when you pause, to keep listening
                            if the sentence was cut off ("turn on the lights and...")
    can_barge_in():         optional - return True while Wisp is talking AND you use headphones: then just
                            starting to talk interrupts Wisp (on_barge_in is called) and it listens
    """

    CHUNK = 1280  # 80 ms at 16 kHz - what openWakeWord expects
    EARLY_PAUSE = 0.7  # seconds of quiet before a quick "is that a complete sentence?" check
    MAX_SECONDS = 30

    def __init__(self, model_name, threshold, end_pause, is_paused, on_wake, on_command, on_nothing,
                 check_finished=None, can_barge_in=None, on_barge_in=None):
        self.model_name, self.threshold = model_name, float(threshold)
        self.end_pause = float(end_pause)  # seconds of quiet that means "I've finished talking"
        self.is_paused, self.on_wake = is_paused, on_wake
        self.on_command, self.on_nothing = on_command, on_nothing
        self.check_finished = check_finished
        self.can_barge_in, self.on_barge_in = can_barge_in, on_barge_in
        self.quick_finish = True     # answer after a short pause when it's clearly a complete sentence
        self.min_speech = 0.0        # a follow-up needs at least this much talking (ignores coughs, clicks, TV)
        self.level = 0.0
        self.capturing = False
        self._listen_request = None  # set by listen_now() to open the mic without the wake word

    def load(self):
        """Load the wake word model (downloads it the first time). Raises if openWakeWord isn't installed."""
        import openwakeword
        from openwakeword.model import Model
        try:
            openwakeword.utils.download_models(model_names=[self.model_name])
        except TypeError:
            openwakeword.utils.download_models()
        self.model = Model(wakeword_models=[self.model_name], inference_framework="onnx")

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self.capturing = False
        self._listen_request = None

    def listen_now(self, timeout=6.0, min_speech=0.0):
        """Open the mic for a reply without needing the wake word (e.g. after a question)."""
        self._pending_min_speech = float(min_speech)
        self._listen_request = float(timeout)

    def _begin_capture(self, timeout):
        self.capturing = True
        self._recorded, self._heard, self._silent = [], False, 0.0
        self._speech = 0.0          # seconds that sounded like talking
        self._extensions = 0        # times we kept listening because the sentence wasn't finished
        self._early_checked = False
        self._started, self._timeout = time.time(), timeout

    def _pause_needed(self):
        """How long a pause means 'finished'. Longer after a very short phrase (you may be thinking),
        and longer again once a sentence has been cut off."""
        pause = self.end_pause
        if self._speech < 1.0:
            pause += 0.6
        return pause + 1.0 * self._extensions

    def _run(self):
        import numpy as np
        import sounddevice as sd
        chunks = queue.Queue()
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=self.CHUNK,
                                callback=lambda data, *_: chunks.put(data[:, 0].copy()))
        noise = 0.01
        last_wake = 0.0
        step = self.CHUNK / SAMPLE_RATE
        preroll = collections.deque(maxlen=8)   # the last ~0.6 s, so the start of a barge-in isn't lost
        barge = 0.0
        with stream:
            while True:
                chunk = chunks.get()
                audio = chunk.astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(audio ** 2)))

                if not self.capturing and self._listen_request is not None:
                    self._begin_capture(self._listen_request)  # follow-up: listen straight away
                    self.min_speech = getattr(self, "_pending_min_speech", 0.0)
                    self._listen_request = None
                    self._reset_model()

                if not self.capturing:
                    preroll.append(audio)
                    if self.can_barge_in and self.can_barge_in():
                        # Wisp is talking and you wear headphones: you starting to talk interrupts it
                        barge = barge + step if rms > max(0.02, noise * 4.0) else max(0.0, barge - step)
                        if barge >= 0.3:
                            barge = 0.0
                            self._begin_capture(6.0)
                            self._recorded = list(preroll)
                            self._heard, self._speech = True, 0.3
                            self.min_speech = 0.0
                            self._reset_model()
                            if self.on_barge_in:
                                self.on_barge_in()
                        continue
                    barge = 0.0
                    noise = noise * 0.97 + rms * 0.03  # track background noise
                    if self.is_paused():
                        continue
                    scores = self.model.predict(chunk)
                    if max(scores.values(), default=0) >= self.threshold and time.time() - last_wake > 2:
                        last_wake = time.time()
                        self._reset_model()
                        self._begin_capture(6.0)
                        self.min_speech = 0.0
                        self.on_wake()
                    continue

                # recording the request (after the wake word, or a follow-up)
                self._recorded.append(audio)
                self.level = min(1.0, rms * 12)
                loud = max(0.012, noise * 3.0)    # clearly talking
                quiet = max(0.008, noise * 1.8)   # clearly not talking
                if rms > loud:
                    self._heard, self._silent = True, 0.0
                    self._speech += step
                elif rms < quiet:
                    self._silent += step
                    noise = noise * 0.98 + rms * 0.02  # keep learning the room while you pause
                else:
                    self._silent += step / 2  # in between (breathing, a soft word): counts as half a pause
                elapsed = time.time() - self._started
                too_long = elapsed > self.MAX_SECONDS
                # quick check after a short pause: if it's clearly a finished sentence, don't keep waiting
                if (self.check_finished and self.quick_finish and self._heard and not self._early_checked
                        and self._extensions == 0
                        and self._speech >= 0.8 and self._silent >= self.EARLY_PAUSE):
                    self._early_checked = True
                    finished, text = self.check_finished(np.concatenate(self._recorded))
                    if finished and complete_sentence(text):
                        self._finish(np.concatenate(self._recorded), text)
                        continue
                paused = self._heard and self._silent > self._pause_needed()
                gave_up = not self._heard and elapsed > self._timeout
                if not (paused or too_long or gave_up):
                    continue

                if gave_up or (self._speech < self.min_speech and not too_long):
                    self._finish(None, None)   # nothing (or just a cough / a click) - close quietly
                    continue
                recording = np.concatenate(self._recorded)
                text = None
                if self.check_finished and not too_long:
                    finished, text = self.check_finished(recording)
                    if not finished and self._extensions < 2:
                        self._extensions += 1   # "open Spotify and..." - keep listening
                        self._silent = 0.0
                        continue
                self._finish(recording, text)

    def _finish(self, recording, text):
        self.capturing, self.level = False, 0.0
        self._reset_model()
        if recording is not None:
            self.on_command(recording, text)
        else:
            self.on_nothing()

    def _reset_model(self):
        try:
            self.model.reset()
        except Exception:
            pass


def strip_wake_words(text):
    """Remove 'hey jarvis' if Whisper also caught it at the start."""
    return re.sub(r"^\s*(hey|hi|okay|ok|yo)?[\s,]*(jarvis|mycroft|wisp)[\s,.!?:-]*", "", text, flags=re.IGNORECASE).strip()


# ---------------- speaking ----------------
class Speaker:
    """Text-to-speech that can be cut off at any time with stop().

    engine "edge":    free Microsoft neural voices (natural-sounding, needs internet)
    engine "windows": the voices built into Windows (robotic, but works offline)
    If the neural voice fails (e.g. no internet) it falls back to the Windows voice.
    """

    def __init__(self, cfg):
        self.engine = cfg.get("voice_engine", "edge")
        self.edge_voice = cfg.get("edge_voice", "en-GB-RyanNeural")
        self.edge_rate = cfg.get("edge_rate", "+0%")
        self.edge_pitch = cfg.get("edge_pitch", "+0Hz")
        # "ai": Wisp's own composed, slightly deeper voice with a subtle synthetic edge; "natural": plain
        self.style = cfg.get("voice_style", "ai")
        if self.style == "ai":
            self.edge_rate = _shift(self.edge_rate, -5, "%")
            self.edge_pitch = _shift(self.edge_pitch, -6, "Hz")
        # the offline fallback voice: a Windows SAPI voice name, or a macOS 'say' voice (e.g. "Daniel")
        self.system_voice = cfg.get("mac_voice" if sysplat.IS_MAC else "windows_voice", "Daniel" if sysplat.IS_MAC else "")
        self.windows_rate = int(cfg.get("voice_rate", 1))
        self.speaking = False
        self._generation = 0
        self._jobs = queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()

    def speak(self, text, on_done=None, on_start=None):
        """Speak in the background. on_done() runs if it finishes without being stopped;
        on_start() runs when the first sound plays."""
        self.stop()
        self._on_start = on_start
        self._jobs.put((self._generation, text, on_done))

    def stop(self):
        self._generation += 1

    # Everything below runs on the speaker's own thread.
    def _loop(self):
        while True:
            gen, text, on_done = self._jobs.get()
            if gen != self._generation:
                continue
            finished = False
            if text and (sysplat.IS_WIN or sysplat.IS_MAC):
                self.speaking = True
                try:
                    finished = (self.engine == "edge" and self._speak_edge(text, gen)) \
                        or (gen == self._generation and self._speak_system(text, gen))
                except Exception as exc:
                    print(f"(voice error: {exc})")
                self.speaking = False
            else:
                finished = True
            if finished and on_done and gen == self._generation:
                on_done()

    # ----- neural voice: split into sentences, prepare the next while the first plays, cache phrases -----
    CACHE = os.path.join(tempfile.gettempdir(), "wisp_voice_cache")

    def precache(self, phrases):
        """Prepare common phrases in the background so they play instantly later."""
        if self.engine != "edge" or not (sysplat.IS_WIN or sysplat.IS_MAC):
            return

        def run():
            for p in phrases:
                try:
                    self._synth(p)
                except Exception:
                    return
        threading.Thread(target=run, daemon=True).start()

    def _synth(self, text):
        """Turn text into an mp3 (or reuse a cached one). Returns the file path."""
        import hashlib
        import edge_tts
        os.makedirs(self.CACHE, exist_ok=True)
        key = hashlib.sha1(f"{self.edge_voice}|{self.edge_rate}|{self.edge_pitch}|{text}".encode()).hexdigest()
        path = os.path.join(self.CACHE, key + ".mp3")
        if not os.path.exists(path):
            tmp = path + f".{threading.get_ident()}.part"
            communicate = edge_tts.Communicate(text, self.edge_voice, rate=self.edge_rate, pitch=self.edge_pitch)
            asyncio.run(communicate.save(tmp))
            os.replace(tmp, path)
            self._prune_cache()
        if self.style == "ai":
            return ai_voice(path)
        return path

    def _prune_cache(self, keep=300):
        try:
            files = sorted((os.path.join(self.CACHE, f) for f in os.listdir(self.CACHE)
                            if f.endswith((".mp3", ".wav"))),
                           key=os.path.getmtime)
            for f in files[:-keep]:
                os.remove(f)
        except OSError:
            pass

    @staticmethod
    def _sentences(text):
        # English sentences end with . ! ? and a space; Chinese ones with 。！？ (no space)
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|(?<=[\u3002\uff01\uff1f])", text) if p.strip()]
        merged = []
        for p in parts:  # keep very short bits ("Done." / "好的。") with the next sentence
            short = 25 if p.isascii() else 8
            if merged and len(merged[-1]) < short:
                merged[-1] += ("" if not p.isascii() else " ") + p
            else:
                merged.append(p)
        merged = merged or [text]
        first = merged[0]
        if len(first) > 90:   # a long first sentence: start speaking at its first comma instead
            m = re.search(r"^(.{25,80}?[,;:\uff0c\uff1b])\s*(.+)$", first)
            if m:
                merged[0:1] = [m.group(1), m.group(2)]
        return merged

    def _speak_edge(self, text, gen):
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            print("(edge-tts isn't installed - using the Windows voice. Run setup.bat to install it.)")
            self.engine = "windows"
            return False
        parts = self._sentences(text)
        files = [None] * len(parts)
        ready = [threading.Event() for _ in parts]

        def prepare():  # runs alongside playback, so sentence 2 is ready by the time 1 finishes
            for i, part in enumerate(parts):
                if gen != self._generation:
                    break
                try:
                    files[i] = self._synth(part)
                except Exception as exc:
                    files[i] = exc
                ready[i].set()
            for event in ready:
                event.set()
        threading.Thread(target=prepare, daemon=True).start()

        for i in range(len(parts)):
            ready[i].wait(20)
            if gen != self._generation:
                return True
            if not isinstance(files[i], str):
                if i == 0:
                    print(f"(neural voice unavailable: {files[i]} - using the Windows voice)")
                    return False
                return True
            if i == 0 and getattr(self, "_on_start", None):
                try:
                    self._on_start()
                except Exception:
                    pass
            self._play(files[i], gen)
        return True

    def _play(self, path, gen):
        sysplat.AudioPlayer(path).play(lambda: gen != self._generation)

    def _speak_system(self, text, gen):
        """The built-in offline voice (Windows SAPI / macOS say)."""
        cmd, stdin_text = sysplat.system_voice_command(text, self.system_voice, self.windows_rate)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin_text else subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                creationflags=sysplat.NO_WINDOW)
        if stdin_text:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        while proc.poll() is None:
            if gen != self._generation:
                proc.kill()
                return True
            time.sleep(0.05)
        return True


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "config.json"), encoding="utf-8") as f:
        config = json.load(f)
    sample = " ".join(sys.argv[1:]) or "Good evening. All systems are online and ready."
    done = threading.Event()
    s = Speaker(config)
    print(f"Speaking with {config.get('voice_engine')} voice "
          f"{config.get('edge_voice') if config.get('voice_engine', 'edge') == 'edge' else (config.get('mac_voice', 'Daniel') if sysplat.IS_MAC else config.get('windows_voice')) or 'default'}...")
    s.speak(sample, on_done=done.set)
    done.wait(60)
