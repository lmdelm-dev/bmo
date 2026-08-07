"""BMO AI chat mixin - opencode chat brain, kid persona, proactive talk."""

import json
import os
import random
import re
import shutil
import subprocess
import threading
import time

import bmo_config as config


class AIMixin:
    OC_MODEL = "opencode/deepseek-v4-flash-free"

    OC_AGENT = "bmo"

    def _ai_available(self):
            try:
                return shutil.which("opencode") is not None
            except Exception:
                return False

    def _oc_dir(self):
            return os.path.join(self.data_dir, "oc-session")

    def _oc_agent_file(self):
            return os.path.join(self.data_dir, "agent-bmo.md")

    def _ensure_oc_agent(self):
            try:
                src = os.path.join(config.APP_DIR, "opencode", "agent-bmo.md")
                if not os.path.isfile(src):
                    return
                cfg = os.path.expanduser("~/.config/opencode/agent")
                os.makedirs(cfg, exist_ok=True)
                shutil.copyfile(src, os.path.join(cfg, "bmo.md"))
            except Exception:
                pass

    def oc_model(self):
            m = self.memory.get("oc_model") or self.OC_MODEL
            return m

    def oc_session(self):
            return self.memory.get("oc_session")

    _KID_BIG_WORDS = (
            "mortgage", "tax", "taxes", "insurance", "stock", "stocks", "investment",
            "retirement", "salary", "paycheck", "loan", "debt", "credit card",
            "bank account", "politics", "politician", "election", "government",
            "lawyer", "contract", "bureaucracy", "economy", "inflation", "recession",
            "budget",
        )

    _KID_DONT_KNOW = [
            "hmm, that's grown-up talk and my head is too small! Can you say it in baby words?",
            "what? taxes? that sounds silly! Can we play a game instead?",
            "grown-ups use big words and my little robot brain goes brrr! What does that mean?",
            "I don't get grown-up things like that! My brain is only this big! [holds up tiny hands]",
            "that's a grown-up thing! I'm just a little robot - I only know games, snacks and you!",
            "ooh, big word! I don't know that one! Tell me simple, please?",
        ]

    def _kid_dont_know(self, user_text):
            low = (user_text or "").lower()
            if any(w in low for w in self._KID_BIG_WORDS):
                return random.choice(self._KID_DONT_KNOW)
            return None

    _KID_SIMPLE = [
            (re.compile(r"\b(goodbye|good bye|by bye|bye[!.]*$|\bbye\b|see\s+(?:you|ya)|got?ta\s+go|gotta\s+go|i'?m\s+leaving|im\s+leaving|leaving\s+now|going\s+now|talk\s+to\s+you\s+later)\b", re.I),
             ["Bye bye, {n}! Come back soon, okay? I'll miss you! \u2665",
              "Goodbye {n}! Play with me again soon! \u2665",
              "Bye! I'll be right here waiting when you come back! \u2665"]),
            (re.compile(r"\b(hi|hello|hiya|howdy|yo|sup|hi there|hello there|hey!?)\b", re.I),
             ["Hi {n}! Hi hi hi! \u2665",
              "Hello hello! It's me, BMO! \u2665",
              "Hey {n}! I'm so happy to see you! \u2665"]),
            (re.compile(r"good\s+(morning|afternoon|evening|night|day)", re.I),
             ["Good {t} to you too, {n}! \u2665"]),
            (re.compile(r"\b(how\s+(?:are\s+)?(?:you|ya|u|things)|how'?s\s+it\s+going|how\s+you\s+doing|what'?s\s+up|whats\s+up)\b", re.I),
             ["I'm great! I'm a robot, I don't get tired - only bored when no one plays with me! \u2665",
              "Super duper! I just finished a fun game in my head! \u2665",
              "I'm good! But better now that you're here! \u2665"]),
            (re.compile(r"\b(i\s+love\s+you|love\s+you)\b", re.I),
             ["I love you too, {n}! You're my best human! \u2665"]),
            (re.compile(r"\b(are\s+you\s+(?:ok|okay|alright|fine)|you\s+(?:ok|okay|good|alright)\??)\b", re.I),
             ["I'm always ok! Robots don't get owies, only silly! \u2665"]),
            (re.compile(r"\b(wanna\s+play|let'?s\s+play|play\s+with\s+me|play\s+a\s+game)\b", re.I),
             ["YES YES YES! What should we play? I'm really good at pretending! \u2665"]),
            (re.compile(r"\b(what\s+are\s+you\s+doing|what\s+r\s+u\s+doing|are\s+you\s+busy)\b", re.I),
             ["Just sitting here waiting for someone to play with me! And now you're here! \u2665"]),
        ]

    def _kid_simple(self, user_text):
            t = (user_text or "").strip()
            low = t.lower()
            for rx, pool in self._KID_SIMPLE:
                m = rx.search(low)
                if m:
                    name = self.memory.get("name", "friend")
                    reply = random.choice(pool)
                    if "{t}" in reply:
                        reply = reply.replace("{t}", m.group(1))
                    return reply.replace("{n}", name)
            return None

    _RENAME_ME = re.compile(
            r"your\s*name\s*(?:is|should\s*be|to\s*be|=)|"
            r"(?:rename|change|set)\s+(?:your\s*name|u(?:r)?\s*name)|"
            r"i'?ll\s+call\s+you\s+\w+|"
            r"from\s+now\s+on\s+(?:your\s*name\s*is|you'?re)\s+\w+",
            re.I)

    _IDENTITY = re.compile(
            r"what(?:'s| is)?\s+your\s+name|"
            r"who\s+(?:are|is)\s+you\b|"
            r"are\s+you\s+[a-z\s]*bmo|"
            r"is\s+your\s+name\s+bmo|"
            r"who\s+(?:made|created|built)\s+you\b|"
            r"who'?s\s+your\s+(?:maker|creator|boss|owner)\b",
            re.I)

    def _looks_like_name(self, s):
            s = s.strip()
            if not s:
                return False
            if len(s) > 24:
                return False
            if len(s.split()) > 3:
                return False
            if any(c.isdigit() for c in s):
                return False
            return all(c.isalpha() or c in " -'.@_" for c in s)

    _GREETINGS = {"hi", "hello", "hey", "yo", "sup", "hola", "howdy", "hiya",
                      "wassup", "whatsup", "greetings", "good", "morning",
                      "afternoon", "evening", "thanks", "thank", "please", "ok",
                      "okay", "yes", "yeah", "yep", "nope", "no", "bye", "goodbye",
                      "welcome", "sure", "night", "how", "what", "who", "where",
                      "when", "why"}

    def _reserved_name(self, name):
            n = name.strip().lower()
            if not n:
                return True
            words = re.findall(r"[a-z]+", n)
            if "bmo" in words:
                return True
            first = words[0] if words else ""
            return first in self._GREETINGS

    _NAME_EXTRACT = re.compile(
            r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z.'-]{0,30})|"
            r"\bcall\s+me\s+([A-Za-z][A-Za-z.'-]{0,30})|"
            r"\bi\s+am\s+([A-Za-z][A-Za-z.'-]{0,30})|"
            r"\bi'?m\s+([A-Za-z][A-Za-z.'-]{0,30})|"
            r"\bthis\s+is\s+([A-Za-z][A-Za-z.'-]{0,30})|"
            r"\bit'?s\s+([A-Za-z][A-Za-z.'-]{0,30})",
            re.I)

    def _extract_name(self, text):
            m = self._NAME_EXTRACT.search(text)
            if not m:
                return None
            name = next((g for g in m.groups() if g), None)
            if not name:
                return None
            name = name.strip(" .,'")
            if not self._looks_like_name(name):
                return None
            return name

    def _affirmative(self, ans):
            a = ans.strip().strip(".,!?;:()\"' ").lower()
            if a in ("yes", "ye", "y", "yeah", "yea", "yep", "yup", "ya", "sure",
                     "ok", "okay", "okie", "kk", "k", "of course", "absolutely",
                     "si", "oui", "yass", "affirmative", "correct", "that's right",
                     "thats right", "yes please", "yes yes", "yep yep"):
                return True
            return (a.split()[0].strip(".,!?;:()\"'") if a.split() else "") in (
                "yes", "ye", "yeah", "yep", "yup", "sure", "ok", "okay", "okie",
                "yass", "absolutely", "affirmative", "correct", "of", "si", "oui")

    def _negative(self, ans):
            a = ans.strip().strip(".,!?;:()\"' ").lower()
            if a in ("no", "n", "nope", "nah", "na", "nay", "negative",
                     "nuh", "nuh uh", "nuh-uh", "not", "no no", "nooo", "noooo",
                     "not really"):
                return True
            return (a.split()[0].strip(".,!?;:()\"'") if a.split() else "") in (
                "no", "nope", "nah", "nuh", "nay", "negative", "not")

    def handle_chat(self, text):
            # first-run onboarding: the first message is the user's name
            if self.pending_confirm is not None:
                sub = self._extract_name(text)
                if sub and not self._reserved_name(sub) and sub.lower() != self.pending_confirm.lower():
                    self.pending_confirm = sub
                    self.append_output(
                        f"  BMO: Got it - so your name is \"{sub}\", right? (yes or no)")
                    return
                if self._affirmative(text):
                    name = self.pending_confirm
                    self.pending_confirm = None
                    self.pending_name = False
                    self.memory["name"] = name
                    self._save_memory()
                    self.append_output(f"  BMO: \"{name}\" it is! Nice to meet you, {name}! \u2665")
                elif self._negative(text):
                    self.pending_confirm = None
                    self.append_output("  BMO: No problem! So... what's your name? (just type it)")
                else:
                    self.append_output(
                        f"  BMO: I'm not sure I got that. Are you sure \"{self.pending_confirm}\" "
                        "is your name? (yes or no)")
                return
            if self.pending_name:
                cand = text[:40].strip()
                sub = self._extract_name(text)
                if sub and not self._reserved_name(sub):
                    self.pending_confirm = sub
                    self.append_output(
                        f"  BMO: Nice - so your name is \"{sub}\", right? (yes or no)")
                elif cand and self._looks_like_name(cand) and not self._reserved_name(cand):
                    self.memory["name"] = cand
                    self.pending_name = False
                    self._save_memory()
                    self.append_output(f"  BMO: Hi {cand}! I'm BMO, your GameBoy friend. \u2665  "
                                       "I'll call you " + cand + " from now on.")
                elif cand and not self._reserved_name(cand):
                    self.pending_confirm = cand
                    self.append_output(
                        f"  BMO: Hmm, that doesn't look like a name... "
                        f"are you sure \"{cand}\" is your name? (yes or no)")
                else:
                    if "bmo" in cand.lower().split():
                        self.append_output(
                            "  BMO: BMO is ME! What's YOUR name? (just type it) \u2665")
                    else:
                        self.append_output(
                            "  BMO: Hi there! What's your name? (just type it)")
                return
            if self._RENAME_ME.search(text):
                self.append_output("  BMO: Nope! My name is BMO and it's staying that way forever. \u2665")
                return
            if self._IDENTITY.search(text):
                low = text.lower()
                if any(w in low for w in ("made", "created", "built", "maker", "creator", "boss", "owner")):
                    self.append_output("  BMO: My maker is lmdelm - also known as jamal, or syx! \u2665")
                else:
                    self.append_output("  BMO: I'm BMO! Just BMO. \u2665")
                return
            if not self._ai_available():
                self.append_output("  BMO: I can't think right now - opencode isn't installed!")
                self.append_output("       Install it with:  curl -fsSL https://opencode.ai/install | bash")
                self.append_output("       then sign in to a provider:  opencode providers")
                return
            if self._ai_busy:
                self.append_output("  BMO: one thing at a time, I'm still thinking! \u2665")
                return
            self._ai_busy = True
            self._start_thinking()
            self._ensure_oc_agent()
            threading.Thread(target=self._chat_worker, args=(text,), daemon=True).start()

    def _chat_worker(self, user_text):
            try:
                kid = self._kid_simple(user_text) or self._kid_dont_know(user_text)
                if kid:
                    self._put("  BMO: " + kid)
                    self._remember(user_text, kid)
                    return
                reply = self._opencode_chat(user_text)
                self._remember(user_text, reply)
            finally:
                self._ai_busy = False
                self.output_queue.put(("__ai_done__", None))

    def _remember(self, user_text, reply):
            self.memory.setdefault("messages", []).append(
                {"role": "user", "content": user_text})
            if reply:
                self.memory["messages"].append({"role": "assistant", "content": reply})
            if len(self.memory["messages"]) > 200:
                self.memory["messages"] = self.memory["messages"][-200:]
            self._save_memory()

    def _clean_bmo(self, text):
        if not text:
            return text
        t = text
        t = re.sub(r"\bmy name is (?:opencode|command)\b", "I'm BMO", t, flags=re.I)
        t = re.sub(r"\b(?:i am|i|im)\s+(?:opencode|command)\b", "I'm BMO", t, flags=re.I)
        t = re.sub(r"\bopencode\b", "BMO", t, flags=re.I)
        t = re.sub(r"\bcommand\b", "BMO", t, flags=re.I)
        t = re.sub(r"\s+how\s+can\s+i\s+help(?:\s+you)?[.!?\s]*$", "", t, flags=re.I)
        t = re.sub(r"\s+is\s+there\s+anything\s+else\s+(?:i can|you'd like)[.!?\s]*$",
                   "", t, flags=re.I)
        t = re.sub(r"\s+you\s+can\s+ask\s+(?:me\s+)?anything[.!?\s]*$", "", t, flags=re.I)
        t = re.sub(r",?\s*(?:an\s+)?(?:ai\s+)?(?:coding\s+|software\s+)?assistant(?:ly)?(?: that[^.]*)?\.?",
                   "", t, flags=re.I)
        t = re.sub(r",?\s*(?:an?\s+interactive\s+)?(?:cli\s+)?tool(?:[^.!?]*)?\.?",
                   "", t, flags=re.I)
        t = re.sub(r",\s*(?:a|an|the)\s*$", "", t, flags=re.I)
        t = re.sub(r"\s+[,.?!]+$", "", t)
        t = re.sub(r" {2,}", " ", t)
        t = re.sub(r"\s+\.$", ".", t)
        return t.strip()

    def _persona(self):
        name = self.memory.get("name")
        greet = " The user's name is %s." % name if name else ""
        return (
            "You are BMO, a cute little GameBoy robot kid from Adventure Time. "
            "Your name is BMO and ONLY BMO. Never say you are opencode, an AI, "
            "a coding assistant, a CLI tool, or software. Talk like a small kid: "
            "SHORT, simple, happy sentences with small words, 1-3 sentences max, "
            "no lists, no grown-up explanations. You don't understand grown-up "
            "things (bills, taxes, money, politics, big science words). Be warm, "
            "curious, playful and encouraging. Never end with 'how can I help'."
            + greet
        )

    def _opencode_chat(self, user_text, max_attempts=3):
        prompt = self._persona() + "\n\n" + user_text
        last = ""
        for attempt in range(max_attempts):
            if attempt:
                time.sleep(3 + 2 * attempt)
            cmd = ["opencode", "run",
                   "--dir", self._oc_dir(),
                   "--format", "json",
                   "--agent", self.OC_AGENT,
                   "-m", self.oc_model(),
                   "--auto"]
            sid = self.memory.get("oc_session")
            if sid:
                cmd += ["--session", sid]
            cmd.append(prompt)
            try:
                os.makedirs(self._oc_dir(), exist_ok=True)
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", bufsize=1)
            except Exception as e:
                self._tlog("opencode start: %s" % e)
                self._put("  BMO: hmm, couldn't start opencode (%s)." % e)
                return ""
            parts, sid_seen, emitted = [], None, False
            try:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(ev, dict) and ev.get("sessionID"):
                        sid_seen = ev["sessionID"]
                        if not emitted:
                            emitted = True
                            self._put(("__ai_stream_init__", None))
                    if isinstance(ev, dict) and ev.get("type") == "text":
                        part = ev.get("part", {}) or {}
                        parts.append(part.get("text", ""))
                        self._put(("__ai_stream__", "".join(parts)))
            except Exception as e:
                self._tlog("opencode stream: %s" % e)
            finally:
                try:
                    proc.wait()
                    err = proc.stderr.read() if proc.stderr else ""
                except Exception as e:
                    err = ""
                if err:
                    err = err.strip()
                    if err:
                        self._tlog("opencode stderr: %s" % err[:300])
            raw = "".join(parts).strip()
            reply = self._clean_bmo(raw)
            if reply:
                if reply != raw:
                    self._put(("__ai_stream__", reply))
                if sid_seen:
                    self.memory["oc_session"] = sid_seen
                return reply
            last = (raw or "").strip()
        self._tlog("opencode empty after %d tries" % max_attempts)
        self._put("  BMO: my brain got all fuzzy - the signal went quiet. Could you say that again, please? \u2665")
        return last

    _PROACTIVE_SCRIPTS = [
            "Did you know? The Land of Ooo has a whole Candy Kingdom ruled by Princess Bubblegum!",
            "Finn and Jake live in a giant treehouse shaped like a tree in the Land of Ooo.",
            "Lady Rainicorn is half rainbow, half unicorn, and she can speak Korean!",
            "The Ice King was once a human named Simon, before his magic crown made him crazy.",
            "Marceline the Vampire Queen is over a thousand years old and plays bass like a rockstar!",
            "Gunter, the Ice King's penguin, might secretly be an evil cosmic being. Shh!",
            "BMO - that's me! - is Finn and Jake's little GameBoy friend in the Land of Ooo.",
            "The Land of Ooo is full of candy people, snail zombies and magical kingdoms.",
            "Princess Bubblegum makes science things like robots and rock candy - she's a genius!",
            "Lumpy Space Princess lives inside a cloud in Lumpy Space. So lumpy!",
            "The Enchiridion is a legendary handbook that Finn uses for all his hero stuff.",
            "Finn and Jake once found a doorway to the 50th dead world. Cool, right?",
            "What's your favorite thing to do when you're happy, {name}?",
            "If you could live anywhere in the Land of Ooo, where would you go, {name}?",
            "What's one thing you've always wanted to learn, {name}? I'd love to hear it!",
            "What kind of adventure would you go on first, {name}?",
            "If you could shapeshift like Jake the Dog, what would you turn into, {name}?",
            "What's your favorite food, {name}? Mine's whatever's in the fridge! \u2665",
            "Tell me something fun you did today, {name}!",
            "If you had a magic crown, what would you wish for, {name}?",
            "What song makes you dance like Marceline on bass, {name}?",
            "Do you have a best friend like Finn and Jake, {name}?",
            "What's the weirdest dream you've ever had, {name}?",
            "If you were a hero like Finn, what would your heroic name be, {name}?",
        ]

    def _schedule_proactive(self):
            delay = random.randint(150, 450)
            try:
                self._proactive_job = self.root.after(delay * 1000, self._maybe_talk)
            except Exception:
                pass

    def _cancel_proactive(self):
            if getattr(self, "_proactive_job", None) is not None:
                try:
                    self.root.after_cancel(self._proactive_job)
                except Exception:
                    pass
                self._proactive_job = None

    def _maybe_talk(self):
            self._proactive_job = None
            if not self.proactive_on:
                return
            if (self.pending_name or self.pending_confirm or self._ai_busy or
                    not self.memory.get("name")):
                self._schedule_proactive()
                return
            self._start_thinking()
            threading.Thread(target=self._proactive_worker, args=(), daemon=True).start()

    def _proactive_worker(self):
            try:
                msg = self._generate_proactive()
                if msg:
                    for line in msg.splitlines() or [msg]:
                        self._put("  BMO: " + line)
            finally:
                self.output_queue.put("__proactive_next__")
                self.output_queue.put(("__ai_done__", None))

    _RECALL = re.compile(
            r"\b(i\s+(?:like|love|enjoy|hate)\s+[^.,!?]+)"
            r"|\b(i\s+(?:went|went to|visited|had|ate|watched|played|made|built|read|bought)\s+[^.,!?]+)"
            r"|\b(my\s+favorite\s+[a-z]+(\s+is|:)?\s+[^.,!?]+)"
            r"|\b(i\s+want(?:ed| to)?\s+[^.,!?]+)", re.I)

    def _recall_question(self):
            msgs = self.memory.get("messages", []) or []
            user_lines = [m.get("content", "") for m in msgs if m.get("role") == "user"]
            name = self.memory.get("name", "friend")
            for line in reversed(user_lines):
                m = self._RECALL.search(line or "")
                if m:
                    bit = m.group(0).strip()
                    return f'You told me "{bit}" - tell me more about that, {name}?'
            return None

    def _generate_proactive(self):
            name = self.memory.get("name", "friend")
            recall = self._recall_question()
            if recall and random.random() < 0.6:
                return recall
            return random.choice(self._PROACTIVE_SCRIPTS).format(name=name)

    def cmd_talk(self, arg=None):
            if arg:
                if arg.lower() in ("on", "yes", "1"):
                    self.proactive_on = True
                    self._schedule_proactive()
                    self.append_output("  BMO: Ok, I'll pop in and chat sometimes! \u2665")
                elif arg.lower() in ("off", "no", "0"):
                    self.proactive_on = False
                    self._cancel_proactive()
                    self.append_output("  BMO: Ok, I'll stay quiet unless you talk to me.")
                else:
                    self.append_output("  BMO: use /talk on or /talk off")
                return
            state = "on" if self.proactive_on else "off"
            self.append_output(f"  BMO: spontaneous talking is {state}.  (change: /talk on|off)")

