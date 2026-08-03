"""BMO voice mixin - text-to-speech (Piper/espeak-ng) + speech-to-text (vosk)."""

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile

import bmo_secure as secure

class VoiceMixin:
    _VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

    _VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"

    def _tts_bin(self):
            return shutil.which("espeak-ng") or shutil.which("espeak")

    def _tts_available(self):
            return self._tts_bin() is not None

    def _clean_speech(self, text):
            t = re.sub(r"^\s*BMO:\s*", "", text)
            t = re.sub(r"\u2588", "", t)
            t = re.sub(r"[*_`#>|]", "", t)
            t = re.sub(r"https?://\S+|www\.\S+", " link ", t)
            t = re.sub(r"[\u2665\u2764\u2765\u2766\u2661]", "", t)
            t = re.sub(r"\s+", " ", t)
            return t.strip()

    _VOICES = {
            "en": "en-us+f3",
            "ar": "ar+f2",
            "fr": "fr+f3",
            "es": "es+f3",
        }

    def _detect_lang(self, text):
            if re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]", text):
                return "ar"
            t = text.lower()
            if (re.search(r"[ñ¿¡áíóúü]", text) or
                    re.search(r"\b(hola|gracias|amigo|qué|cómo|está|por|para|una|bienvenido|juego|hasta|también|buenos|noche|días)\b", t)):
                return "es"
            if (re.search(r"[àâçéèêëîïôùûœæ]", text) or
                    re.search(r"\b(bonjour|merci|comment|salut|oui|non|pour|avec|très|j'aime|vous|mon|ma|mes)\b", t)):
                return "fr"
            return "en"

    def _speak(self, text, force=False):
            if not force and not self.voice_on:
                return
            if not self._tts_available():
                return
            if not self._speak_thread or not self._speak_thread.is_alive():
                self._speak_thread = threading.Thread(target=self._speak_loop, daemon=True)
                self._speak_thread.start()
            self._speak_queue.put(text)

    def _speak_loop(self):
            while True:
                text = self._speak_queue.get()
                if text is None:
                    return
                self._say(text)

    def _say(self, text):
            try:
                with self._voice_lock:
                    clean = self._clean_speech(text)
                    if not clean:
                        return
                    lang = self._detect_lang(clean)
                    if lang == "en" and self._ensure_piper_model():
                        self._play_piper(clean)
                        return
                    bin_ = self._tts_bin()
                    if not bin_:
                        return
                    voice = self.voice_variant if lang == "en" else self._VOICES.get(lang, self.voice_variant)
                    subprocess.run([bin_, "-v", voice,
                                    "-p", str(self.voice_pitch),
                                    "-s", str(self.voice_speed), clean],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=120)
            except Exception:
                pass

    _PIPER_VOICE = "en_US-amy-medium"

    _PIPER_URL_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium"

    def _piper_dir(self):
            return os.path.join(self.data_dir, "piper")

    def _piper_model(self):
            return os.path.join(self._piper_dir(), self._PIPER_VOICE + ".onnx")

    def _piper_player(self):
            return shutil.which("aplay") or shutil.which("paplay")

    def _piper_ready(self):
            try:
                import piper  # noqa
                return os.path.exists(self._piper_model()) and self._piper_player() is not None
            except Exception:
                return False

    def _ensure_piper_model(self):
            if os.path.exists(self._piper_model()):
                return True
            try:
                import piper  # noqa
            except Exception:
                self._put("  BMO: my human voice needs piper-tts (pip install piper-tts)")
                return False
            if self._piper_player() is None:
                return False
            self._put(("__voice_start__", None))
            try:
                os.makedirs(self._piper_dir(), exist_ok=True)
                for ext in (".onnx", ".onnx.json"):
                    urllib.request.urlretrieve(self._PIPER_URL_BASE + ext,
                                               os.path.join(self._piper_dir(), self._PIPER_VOICE + ext))
                return True
            except Exception as e:
                self._put("  BMO: couldn't download my voice (%s) - using my old voice" % e)
                return False
            finally:
                self._put(("__voice_stop__", None))

    def _play_piper(self, text):
            try:
                if self._piper_voice is None:
                    import piper
                    self._piper_voice = piper.PiperVoice.load(self._piper_model())
                v = self._piper_voice
                rate = int(getattr(v.config, "sample_rate", 22050))
                player = self._piper_player()
                if not player:
                    return
                sox = None
                if self.voice_kid and shutil.which("sox"):
                    cents = max(0, min(1200, int(self.voice_kid_cents)))
                    sox = subprocess.Popen(
                        ["sox", "-t", "raw", "-r", str(rate), "-e", "signed", "-b", "16", "-c", "1", "-",
                         "-t", "raw", "-r", str(rate), "-e", "signed", "-b", "16", "-c", "1", "-",
                         "pitch", "+%d" % cents],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL)
                p = subprocess.Popen([player, "-q", "-f", "S16_LE", "-r", str(rate), "-c", "1"],
                                     stdin=sox.stdout if sox else subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if sox:
                    sox.stdout.close()
                try:
                    src = sox.stdin if sox else p.stdin
                    for chunk in v.synthesize(text):
                        src.write(chunk.audio_int16_bytes
                                  if hasattr(chunk, "audio_int16_bytes") else chunk)
                except (BrokenPipeError, OSError):
                    pass
                try:
                    (sox.stdin if sox else p.stdin).close()
                except Exception:
                    pass
                for proc in ([sox, p] if sox else [p]):
                    try:
                        proc.wait(timeout=60)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
            except Exception:
                pass

    def cmd_voice(self, arg=""):
            a = (arg or "").strip().lower()
            parts = a.split(None, 1)
            if a == "off":
                self.voice_on = False
                self.memory["voice"] = False
                self._save_memory()
                self.append_output("  BMO: okay, I'll stay quiet now... but I'm still here \u2665")
            elif a == "on":
                self.voice_on = True
                self.memory["voice"] = True
                self._save_memory()
                self.append_output("  BMO: my voice is back on! \u2665")
            elif a == "test":
                was = self.voice_on
                self.voice_on = True
                self.append_output("  BMO: Testing, testing, 1 2 3! Can you hear me? \u2665")
                self.voice_on = was
            elif parts and parts[0] == "pitch" and len(parts) > 1:
                try:
                    self.voice_pitch = max(0, min(99, int(parts[1])))
                    self.memory["voice_pitch"] = self.voice_pitch
                    self._save_memory()
                    self.append_output(f"  BMO: my pitch is now {self.voice_pitch}. (/voice test) \u2665")
                except Exception:
                    self.append_output("  BMO: pitch needs a number 0-99 (higher = squeakier!)")
            elif parts and parts[0] == "speed" and len(parts) > 1:
                try:
                    self.voice_speed = max(80, min(450, int(parts[1])))
                    self.memory["voice_speed"] = self.voice_speed
                    self._save_memory()
                    self.append_output(f"  BMO: my speed is now {self.voice_speed} wpm. (/voice test) \u2665")
                except Exception:
                    self.append_output("  BMO: speed needs a number 80-450")
            elif parts and parts[0] == "variant" and len(parts) > 1:
                self.voice_variant = parts[1].strip()
                self.memory["voice_variant"] = self.voice_variant
                self._save_memory()
                self.append_output(f"  BMO: voice variant set to {self.voice_variant}. (/voice test) \u2665")
            elif parts and parts[0] == "kid" and len(parts) > 1:
                sub = parts[1].strip().lower()
                if sub in ("on", "off"):
                    self.voice_kid = (sub == "on")
                    self.memory["voice_kid"] = self.voice_kid
                    self._save_memory()
                    self.append_output(f"  BMO: kid voice {'on' if self.voice_kid else 'off'}! (/voice test) \u2665")
                else:
                    try:
                        self.voice_kid_cents = max(0, min(1200, int(sub)))
                        self.memory["voice_kid_cents"] = self.voice_kid_cents
                        self._save_memory()
                        self.append_output(f"  BMO: kid voice shift set to {self.voice_kid_cents} cents. (/voice test) \u2665")
                    except Exception:
                        self.append_output("  BMO: /voice kid on|off|<cents 0-1200> (higher = smaller voice!)")
            elif a == "kid":
                self.voice_kid = not self.voice_kid
                self.memory["voice_kid"] = self.voice_kid
                self._save_memory()
                self.append_output(f"  BMO: kid voice {'on' if self.voice_kid else 'off'}! (/voice test) \u2665")
            else:
                state = "on" if self.voice_on else "off"
                kid = "kid" if self.voice_kid else "adult"
                self.append_output(f"  BMO: voice {state} | {kid} (+{self.voice_kid_cents}c) | {self.voice_variant} | pitch {self.voice_pitch} | {self.voice_speed} wpm")
                self.append_output("    languages: English, Arabic, Français, Español")
                self.append_output("    /voice on|off|test   /voice pitch <0-99>")
                self.append_output("    /voice speed <80-450>   /voice variant <name>")
                self.append_output("    /voice kid on|off|<cents>")

    def _vosk_dir(self):
            return os.path.join(self.data_dir, "vosk-model")

    def _vosk_available(self):
            try:
                import vosk  # noqa
                return True
            except Exception:
                return False

    def _get_vosk_model(self):
            model_dir = self._vosk_dir()
            model_path = os.path.join(model_dir, self._VOSK_MODEL_NAME)
            if os.path.isdir(model_path):
                return model_path
            if not self._vosk_available():
                self._put("  BMO: voice listening needs vosk - install it: pip install vosk")
                return None
            self._put(("__ears_start__", None))
            try:
                os.makedirs(model_dir, exist_ok=True)
                zpath = os.path.join(model_dir, "model.zip")
                urllib.request.urlretrieve(self._VOSK_MODEL_URL, zpath)
                with zipfile.ZipFile(zpath) as z:
                    secure.safe_extract_zip(z, model_dir)
                try:
                    os.remove(zpath)
                except Exception:
                    pass
                return model_path
            except Exception as e:
                self._put("  BMO: couldn't download my ears (%s) - try again later" % e)
                return None
            finally:
                self._put(("__ears_stop__", None))

    def mic_press(self, event=None):
            if self.saver_active:
                self.exit_saver()
            if self._listening or self._rec_proc is not None or self._processing:
                return
            if not self._vosk_available():
                self.append_output("  BMO: I can't listen yet - install vosk: pip install vosk")
                return
            self._listening = True
            self._rec_start = time.time()
            self._set_mic_state(True)
            threading.Thread(target=self._start_record, daemon=True).start()

    def mic_release(self, event=None):
            if not self._listening:
                return
            self._listening = False
            self._rec_short = (time.time() - self._rec_start) < 0.4
            self._set_mic_state(False)
            self._processing = True
            threading.Thread(target=self._finish_record, daemon=True).start()

    def _set_mic_state(self, recording):
            try:
                btn = self.mic_btn
                if recording:
                    btn.btn_color = "#FF5B7A"
                    btn.btn_hover = "#FF5B7A"
                    btn.btn_text = "REC"
                else:
                    btn.btn_color = "#F20553"
                    btn.btn_hover = "#C00445"
                    btn.btn_text = "MIC"
                btn.btn_text_color = "#FFFFFF"
                self.draw_round_btn(btn)
            except Exception:
                pass

    def _start_record(self):
            try:
                tmp = os.path.join(tempfile.gettempdir(), "bmo_rec_%d.wav" % os.getpid())
                self._rec_file = tmp
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
                if shutil.which("arecord"):
                    proc = subprocess.Popen(
                        ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1",
                         "-t", "wav", tmp],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif shutil.which("parecord"):
                    proc = subprocess.Popen(
                        ["parecord", "--channels=1", "--rate=16000", "--format=s16le", tmp],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self._put("  BMO: no recorder found - I need arecord or parecord to listen")
                    self._put(("__mic_stop__", None))
                    self._listening = False
                    return
                self._rec_proc = proc
                self._put(("__silent__", "  BMO: listening... hold to talk, release to send \u2665"))
            except Exception as e:
                self._tlog("record start failed: %s" % e)
                self._put("  BMO: could not start recording (%s)" % e)
                self._put(("__mic_stop__", None))
                self._rec_proc = None
                self._listening = False

    def _finish_record(self):
            deadline = time.time() + 2
            while self._rec_proc is None and time.time() < deadline:
                time.sleep(0.02)
            proc = self._rec_proc
            self._rec_proc = None
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            tmp = self._rec_file
            self._rec_file = None
            if self._rec_short:
                self._put("  BMO: that was too quick! hold the MIC button while you talk \u2665")
                self._processing = False
                return
            if not tmp or not os.path.exists(tmp) or os.path.getsize(tmp) < 1000:
                self._processing = False
                return
            text = self._transcribe(tmp)
            text = self._fix_transcript(text)
            try:
                os.remove(tmp)
            except Exception:
                pass
            self._put(("__transcribed__", text))
            self._processing = False

    def _fix_transcript(self, text):
            if not text:
                return text
            t = " " + text.lower().strip() + " "
            for bad, good in (
                (" be more ", " BMO "),
                (" beemo ", " BMO "),
                (" be em oh ", " BMO "),
                (" be em o ", " BMO "),
                (" bemo ", " BMO "),
                (" be mo ", " BMO "),
                (" bmo ", " BMO "),
                (" living now ", " leaving now "),
                (" living soon ", " leaving soon "),
                (" living today ", " leaving today "),
                (" living tonight ", " leaving tonight "),
                (" living tomorrow ", " leaving tomorrow "),
                (" living bye ", " leaving bye "),
                (" living right now ", " leaving right now "),
                (" thrue ", " through "),
                (" thru ", " through "),
                (" how are your ", " how are you "),
                (" how's your ", " how are you "),
                (" whatsapp ", " what's up "),
            ):
                t = t.replace(bad, good)
            t = re.sub(r"\b(i'?m|i am|im)\s+living\b", "I'm leaving", t)
            return t.strip()

    def _transcribe(self, wav_path):
            try:
                import vosk
                model_path = self._get_vosk_model()
                if not model_path:
                    return ""
                with self._vosk_lock:
                    if self._vosk_model is None:
                        self._vosk_model = vosk.Model(model_path)
                    if self._vosk_rec is None:
                        self._vosk_rec = vosk.KaldiRecognizer(self._vosk_model, 16000)
                    rec = self._vosk_rec
                rec.Reset()
                with open(wav_path, "rb") as f:
                    data = f.read()
                if data[:4] == b"RIFF":
                    i = 12
                    while i < len(data) - 8:
                        cid = data[i:i + 4]
                        csize = int.from_bytes(data[i + 4:i + 8], "little")
                        if cid == b"data":
                            data = data[i + 8:i + 8 + csize]
                            break
                        i += 8 + csize
                if rec.AcceptWaveform(data):
                    return json.loads(rec.Result()).get("text", "").strip()
                return json.loads(rec.FinalResult()).get("text", "").strip()
            except Exception as e:
                self._tlog("transcribe failed: %s" % e)
                return ""

    def _stop_recording(self):
            self._listening = False
            if self._rec_proc is not None:
                try:
                    self._rec_proc.terminate()
                except Exception:
                    pass

