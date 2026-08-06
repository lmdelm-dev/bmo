"""BMO main application - GameBoyTerminal UI + entry point.

Class split across mixins: VoiceMixin (bmo_voice), AIMixin (bmo_ai),
UpdateMixin (bmo_update), ShellMixin (bmo_shell).
"""

import tkinter as tk
import json
import os
import queue
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time

try:
    from Xlib import display
    from Xlib import X
    from Xlib import XK
    _HAS_XLIB = True
except Exception:
    _HAS_XLIB = False

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

import bmo_config as config
import bmo_secure as secure
from bmo_update import UpdateMixin
from bmo_shell import ShellMixin
from bmo_voice import VoiceMixin
from bmo_ai import AIMixin


class GameBoyTerminal(UpdateMixin, ShellMixin, VoiceMixin, AIMixin):

    APP_VERSION = config.APP_VERSION
    UPDATE_URL = config.UPDATE_URL
    UPDATE_TARBALL = config.UPDATE_TARBALL

    def __init__(self):
            self.root = tk.Tk()
            self.root.title("BMO Terminal")
            self.root.geometry("1000x700+150+50")
            if os.name != "nt":
                self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            self.root.configure(bg="#63BDA4")

            self.drag_data = {"x": 0, "y": 0}
            self.resize_data = None
            self._resize_id = None
            self.is_fullscreen = False
            self._scale = 1.0

            self.saver_active = False
            self.saver_state = "normal"
            self.saver_canvas = None
            self._saver_photo = None
            self._saver_jobs = []
            self.last_activity = time.time()
            self.imagedir = os.path.dirname(os.path.abspath(__file__))
            assetdir = os.path.join(self.imagedir, "assets")
            if os.path.isdir(assetdir):
                self.imagedir = assetdir
            self.images = {}
            self.load_images()

            self.cwd = os.path.expanduser("~")
            self.proc = None
            self.output_queue = queue.Queue()
            self.min_queue = queue.Queue()
            self.history = []
            self.history_idx = 0
            self.ansi_re = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

            # AI friend state (opencode brain, online)
            self._ai_busy = False
            self._stream_mark = None
            self.data_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "bmo")
            self.mem_file = os.path.join(self.data_dir, "chat.json")
            self.memory = self._load_memory()
            self.pending_name = not self.memory.get("name")
            self.pending_confirm = None

            self.voice_on = bool(self.memory.get("voice", True))
            try:
                self.voice_pitch = max(0, min(99, int(self.memory.get("voice_pitch", 60))))
                self.voice_speed = max(80, min(450, int(self.memory.get("voice_speed", 155))))
            except Exception:
                self.voice_pitch = 60
                self.voice_speed = 155
            self.voice_variant = self.memory.get("voice_variant", "en-us+f2")
            self.voice_kid = bool(self.memory.get("voice_kid", True))
            try:
                self.voice_kid_cents = max(0, min(1200, int(self.memory.get("voice_kid_cents", 400))))
            except Exception:
                self.voice_kid_cents = 400
            self._piper_voice = None
            self._speak_queue = queue.Queue()
            self._speak_thread = None
            self._voice_lock = threading.Lock()
            self._vosk_lock = threading.Lock()
            self._vosk_model = None
            self._vosk_rec = None
            self._rec_proc = None
            self._rec_file = None
            self._listening = False
            self._processing = False
            self._rec_start = 0
            self._rec_short = False
            self._brain_msg = self._BRAIN_MSG

            self.term_active = False
            self.term_frame = None
            self.term_proc = None
            self.term_pid = None
            self._term_has_content = False
            self.SHORTCUTS = {
                "mo": "opencode",
                "gmo": "w3m -v",
            }
            self.INTERACTIVE = {
                "opencode", "bash", "sh", "zsh", "fish", "dash", "ksh",
                "python", "python2", "python3", "ipython", "node", "npm", "npx", "deno",
                "vim", "nvim", "vi", "nano", "emacs", "emacsclient",
                "htop", "btop", "top", "tmux", "screen", "ranger", "man", "less", "more",
                "cmatrix", "lazygit", "fzf", "mc", "w3m", "lynx",
            }

            self.build_ui()
            self.setup_bindings()
            self.update_prompt()
            self.welcome()
            self.build_saver()
            self.build_term()

            self.root.after(100, self.force_focus)
            self.root.after(50, self._drain_queue)
            self.root.after(1000, self.check_idle)
            self._start_restore_listener()
            self.proactive_on = True
            self._schedule_proactive()
            self._update_declined = None
            self._thinking = False
            self._thinking_job = None
            self._thinking_frame = 0
            self._brain = False
            self._brain_job = None
            self._brain_frame = 0
            self.root.after(15000, self._start_update_check)
            self.root.mainloop()

    def force_focus(self):
            if _HAS_XLIB:
                try:
                    d = display.Display()
                    win = d.create_resource_object("window", self.root.winfo_id())
                    d.set_input_focus(win, X.RevertToParent, X.CurrentTime)
                    d.sync()
                except Exception:
                    pass
            if os.name != "nt":
                try:
                    os.system(f"wmctrl -i -a 0x{self.root.winfo_id():x} >/dev/null 2>&1")
                except Exception:
                    pass
            self.root.focus_force()
            self.input_entry.focus_force()

    def build_ui(self):
            self.body = tk.Frame(self.root, bg="#63BDA4", padx=20, pady=20)
            self.body.pack(fill="both", expand=True)

            self.header = tk.Frame(self.body, bg="#63BDA4", cursor="fleur")
            self.header.pack(fill="x", pady=(0, 10))
            self.header.bind("<Button-1>", self.on_press)
            self.header.bind("<B1-Motion>", self.on_drag)
            self.header.bind("<ButtonRelease-1>", self.on_release)

            self.header_label = tk.Label(self.header, text="BMO",
                                         font=(self._pick_font("Blue Water",
                                                               "DejaVu Sans",
                                                               "Segoe UI"), 20),
                                         bg="#63BDA4", fg="#101E2B")
            self.header_label.pack(side="left")

            self.status_label = tk.Label(self.header, text="", font=("Courier New", 8, "bold"),
                                         bg="#63BDA4", fg="#101E2B")
            self.status_label.pack(side="left", padx=(8, 0))

            self.fullscreen_btn = self.make_round_btn(self.header, "#F2C600", "#C9A400",
                                                      "FS", "#101E2B", self.toggle_fullscreen)

            self.minimize_btn = self.make_round_btn(self.header, "#4A90D9", "#3A74B2",
                                                    "_", "#FFFFFF", self.minimize_btn_click)

            self.close_btn = self.make_round_btn(self.header, "#E1333F", "#B02230",
                                                 "X", "#FFFFFF", self.close_btn_click)
            self.close_btn.pack(side="right")
            self.minimize_btn.pack(side="right")
            self.fullscreen_btn.pack(side="right")

            self.mic_btn = self.make_round_btn(self.header, "#F20553", "#C00445",
                                               "MIC", "#FFFFFF", self.mic_press)
            self.mic_btn.bind("<ButtonRelease-1>", lambda e: self.mic_release())
            self.mic_btn.pack(side="right")
            self.root.bind("<ButtonRelease-1>", lambda e: self.mic_release())

            led = tk.Canvas(self.header, width=12, height=12, bg="#63BDA4", highlightthickness=0)
            led.pack(side="right")
            led.create_oval(1, 1, 11, 11, fill="#F20553", outline="")

            self.out_wrap = tk.Frame(self.body, bg="#407C84", bd=4, highlightthickness=0)
            self.out_wrap.pack(fill="both", expand=True, pady=(0, 8))

            out_scroll = tk.Scrollbar(self.out_wrap, bg="#63BDA4", troughcolor="#D9FFEA",
                                          activebackground="#407C84", bd=0, width=12)
            out_scroll.pack(side="right", fill="y")

            self.output = tk.Text(self.out_wrap, bg="#D9FFEA", fg="#101E2B",
                                      font=("Courier New", 12, "bold"), wrap="word",
                                      state="disabled", padx=10, pady=8,
                                      yscrollcommand=out_scroll.set,
                                      highlightthickness=0, bd=0,
                                      insertofftime=-1, insertwidth=0)
            self.output.pack(fill="both", expand=True)
            out_scroll.config(command=self.output.yview)

            self.in_wrap = tk.Frame(self.body, bg="#407C84", bd=4, highlightthickness=0)
            self.in_wrap.pack(fill="x", pady=(0, 12))

            in_inner = tk.Frame(self.in_wrap, bg="#D9FFEA", bd=0)
            in_inner.pack(fill="x", padx=4, pady=4)

            self.prompt_label = tk.Label(in_inner, text="> ", font=("Courier New", 12, "bold"),
                                             bg="#D9FFEA", fg="#101E2B")
            self.prompt_label.pack(side="left")

            self.input_var = tk.StringVar()
            self.input_entry = tk.Entry(in_inner, textvariable=self.input_var,
                                            font=("Courier New", 12, "bold"), bg="#D9FFEA",
                                            fg="#101E2B", insertbackground="#101E2B",
                                            bd=0, highlightthickness=0)
            self.input_entry.pack(side="left", fill="x", expand=True)
            self.input_entry.bind("<Button-1>", lambda e: self.entry_click())
            in_inner.bind("<Button-1>", lambda e: self.entry_click())
            self.in_wrap.bind("<Button-1>", lambda e: self.entry_click())

    def entry_click(self):
            if self.saver_active:
                self.exit_saver()
                return
            if self.term_active:
                self._focus_embedded_term(6)
                return
            self.input_entry.focus_set()
            self.root.after_idle(self.force_focus)

    def make_round_btn(self, parent, color, hover, text, text_color, command):
            btn = tk.Canvas(parent, bg="#63BDA4", highlightthickness=0, cursor="hand2")
            btn.btn_color = color
            btn.btn_hover = hover
            btn.btn_text = text
            btn.btn_text_color = text_color
            btn.btn_command = command
            btn.bind("<Button-1>", lambda e: btn.btn_command())
            btn.bind("<Enter>", lambda e: self._btn_hover(btn, True))
            btn.bind("<Leave>", lambda e: self._btn_hover(btn, False))
            self.draw_round_btn(btn)
            return btn

    def draw_round_btn(self, btn):
            s = max(12, int(28 * self._scale))
            btn.configure(width=s, height=s)
            btn.delete("all")
            pad = max(1, int(2 * self._scale))
            btn.create_oval(pad, pad, s - pad, s - pad, fill=btn.btn_color, outline="")
            fs = max(5, int(8 * self._scale))
            btn.create_text(s / 2, s / 2 + 1, text=btn.btn_text,
                            font=("Courier New", fs, "bold"), fill=btn.btn_text_color)

    def _btn_hover(self, btn, on):
            for i in btn.find_all():
                if btn.type(i) == "oval":
                    btn.itemconfig(i, fill=btn.btn_hover if on else btn.btn_color)

    def load_images(self):
            if not _HAS_PIL:
                return
            files = {"normal": "face.png", "blink": "blink.png",
                     "left": "face_left.jpg", "right": "face_right.jpg",
                     "sleep": "sleep.png"}
            for key, fn in files.items():
                path = os.path.join(self.imagedir, fn)
                if os.path.exists(path):
                    try:
                        self.images[key] = Image.open(path)
                    except Exception:
                        pass

    def build_saver(self):
            if not _HAS_PIL or not self.images:
                return
            self.saver_canvas = tk.Canvas(self.out_wrap, bg="#D9FFEA",
                                          highlightthickness=0)
            self.saver_canvas.place(x=0, y=0, relwidth=1, relheight=1)
            self.saver_canvas.place_forget()
            self.saver_canvas.bind("<Button-1>", self.exit_saver)

    def _schedule_saver_job(self, delay_ms, callback):
            job = self.root.after(delay_ms, callback)
            self._saver_jobs.append(job)

    def _cancel_saver_jobs(self):
            for job in self._saver_jobs:
                self.root.after_cancel(job)
            self._saver_jobs = []

    def start_saver(self):
            if not _HAS_PIL or not self.images or not self.saver_canvas:
                return
            if self.saver_active:
                return
            self.saver_active = True
            self.saver_state = "sleep"
            self._blinks_left = 0
            self.append_output("  BMO fell asleep... move mouse or press a key to wake up.")
            self.saver_canvas.place(x=0, y=0, relwidth=1, relheight=1)
            self.saver_canvas.focus_set()
            self.root.update_idletasks()
            self.show_saver_image()

    def exit_saver(self, event=None):
            if not self.saver_active:
                return
            self.saver_active = False
            self._cancel_saver_jobs()
            if self.saver_canvas:
                self.saver_canvas.place_forget()
                self.saver_canvas.delete("all")
            self.root.after_idle(self.force_focus)

    def schedule_blink(self):
            self._schedule_saver_job(random.randint(300, 2000), self.do_blink)

    def do_blink(self):
            if not self.saver_active:
                return
            self._blinks_left = random.randint(1, 2)
            self._next_blink()

    def _next_blink(self):
            if not self.saver_active:
                return
            if self._blinks_left > 0:
                self._blinks_left -= 1
                self.show_saver_image(blink=True)
                self._schedule_saver_job(150, self.end_blink)
                self._schedule_saver_job(random.randint(300, 2000), self._next_blink)
            else:
                self.schedule_blink()

    def end_blink(self):
            if self.saver_active:
                self.show_saver_image()

    def schedule_orientation(self):
            self._schedule_saver_job(random.randint(1000, 3000), self.do_look)

    def do_look(self):
            if not self.saver_active:
                return
            self.show_saver_image(look=random.choice(["left", "right", "normal"]))
            self._schedule_saver_job(500, self.end_look)
            self.schedule_orientation()

    def end_look(self):
            if self.saver_active:
                self.show_saver_image()

    def show_saver_image(self, blink=False, look=None):
            cw = self.saver_canvas.winfo_width()
            ch = self.saver_canvas.winfo_height()
            if cw < 10 or ch < 10:
                return
            if look:
                key = look
            elif blink:
                key = "blink"
            else:
                key = self.saver_state or "normal"
            img = self.images.get(key) or self.images.get("normal")
            if img is None:
                return
            try:
                resample = Image.LANCZOS
            except AttributeError:
                resample = Image.Resampling.LANCZOS
            ratio = min(cw / img.width, ch / img.height)
            nw = max(1, int(img.width * ratio))
            nh = max(1, int(img.height * ratio))
            resized = img.resize((nw, nh), resample)
            self._saver_photo = ImageTk.PhotoImage(resized)
            self.saver_canvas.delete("all")
            self.saver_canvas.create_image(cw / 2, ch / 2, image=self._saver_photo)

    def check_idle(self):
            if (not self.saver_active and not self.term_active and not self._thinking
                    and (time.time() - self.last_activity) >= 120):
                self.start_saver()
            self.root.after(1000, self.check_idle)

    def register_activity(self, event=None):
            self.last_activity = time.time()
            if self.saver_active:
                self.exit_saver()

    def build_term(self):
            self.term_frame = tk.Frame(self.out_wrap, bg="#101E2B",
                                       highlightthickness=0, bd=0)
            self.term_frame.place(x=0, y=0, relwidth=1, relheight=1)
            self.term_frame.place_forget()

    def start_term(self, cmdline):
            xterm = shutil.which("xterm")
            if not xterm:
                self.append_output("  Interactive terminal needs 'xterm' (not on PATH).")
                self.append_output("  Install: sudo zypper install xterm")
                return
            if self.term_active:
                return
            self.exit_saver()
            self.term_active = True
            self._term_has_content = False
            self.status_label.configure(text="terminal: launching...")
            self.term_frame.place(x=0, y=0, relwidth=1, relheight=1)
            self.root.update_idletasks()
            self.root.update()
            wid = self.term_frame.winfo_id()
            args = shlex.split(cmdline) if (cmdline and cmdline != "term") else []
            if not args:
                args = [os.environ.get("SHELL", "bash")]
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"
            full = [xterm, "-into", str(wid), "-bw", "0",
                    "-bg", "#101E2B", "-fg", "#D9FFEA",
                    "-e"] + args
            self._tlog("embed xterm into %s: %s" % (wid, full))
            try:
                self.term_proc = subprocess.Popen(full, env=env, close_fds=True)
            except Exception as e:
                self.append_output("  Error starting terminal: %s" % e)
                self.term_active = False
                self.term_frame.place_forget()
                return
            self.term_pid = self.term_proc.pid
            self._tlog("start xterm pid=%d cmd=%s" % (self.term_pid, args))
            self.root.after(400, self._focus_embedded_term)
            self.root.after(500, self.term_monitor)

    def _pick_font(self, *names):
            try:
                from tkinter import font as tkfont
                fams = set(tkfont.families(self.root))
            except Exception:
                fams = set()
            for n in names:
                if n in fams:
                    return n
            return "TkDefaultFont"

    def _tlog(self, msg):
            try:
                logpath = os.path.join(
                    os.environ.get("TMPDIR") or
                    getattr(__import__("tempfile"), "gettempdir")(),
                    "bmo_term.log")
                with open(logpath, "a") as f:
                    f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
            except Exception:
                pass

    def _xterm_child(self, d):
            try:
                parent = d.create_resource_object("window",
                                                  self.term_frame.winfo_id())
                best, area = None, -1
                for c in parent.query_tree().children:
                    try:
                        g = c.get_geometry()
                        if c.get_attributes().map_state == 2 \
                                and g.width * g.height > area:
                            best, area = c, g.width * g.height
                    except Exception:
                        continue
                return best
            except Exception:
                return None

    def _focus_embedded_term(self, retries=10):
            if not self.term_active:
                return
            if _HAS_XLIB:
                try:
                    d = display.Display()
                    child = self._xterm_child(d)
                    if child is not None:
                        d.set_input_focus(child, X.RevertToParent, X.CurrentTime)
                        d.sync()
                        self._resize_embedded_child(d, child)
                        self._term_has_content = True
                        self.status_label.configure(
                            text="terminal: running (pid %s)" % self.term_pid)
                        self._tlog("embedded+resized+focused xterm")
                        return
                except Exception:
                    pass
            if retries > 0:
                self.root.after(300, lambda: self._focus_embedded_term(retries - 1))

    def _resize_embedded_child(self, d, child):
            try:
                w = max(10, self.term_frame.winfo_width())
                h = max(10, self.term_frame.winfo_height())
                g = child.get_geometry()
                if g.width != w or g.height != h:
                    child.configure(width=w, height=h)
                    d.sync()
            except Exception:
                pass

    def term_resize(self):
            if not self.term_active:
                return
            if _HAS_XLIB:
                try:
                    d = display.Display()
                    child = self._xterm_child(d)
                    if child is not None:
                        self._resize_embedded_child(d, child)
                except Exception:
                    pass

    def term_monitor(self):
            if not self.term_active:
                return
            if self.term_proc is not None and self.term_proc.poll() is not None:
                self._tlog("xterm exited rc=%s" % self.term_proc.poll())
                self.term_exit()
                return
            self.root.after(500, self.term_monitor)

    def term_exit(self):
            if not self.term_active:
                return
            self.term_active = False
            self.term_pid = None
            if self.term_proc is not None:
                try:
                    if self.term_proc.poll() is None:
                        self.term_proc.terminate()
                except Exception:
                    pass
                self.term_proc = None
            self.status_label.configure(text="")
            self._tlog("exit")
            try:
                self.term_frame.place_forget()
            except Exception:
                pass
            self.append_output("  (terminal exited)")
            self.root.after_idle(self.force_focus)

    def force_idle(self):
            self.exit_saver()
            if self.term_active:
                self.term_exit()
            self.last_activity = time.time()
            self.root.after_idle(self.start_saver)

    def setup_bindings(self):
            self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
            self.root.bind("<Escape>", self.on_escape)
            self.root.bind("<Return>", self.submit)
            self.root.bind("<Button-1>", self.on_press)
            self.root.bind("<B1-Motion>", self.on_drag)
            self.root.bind("<ButtonRelease-1>", self.on_release)
            self.root.bind("<Motion>", self.on_motion)
            self.root.bind("<Configure>", self.on_resize)
            self.root.bind("<Key>", self.register_activity)
            self.input_entry.bind("<Up>", self.history_up)
            self.input_entry.bind("<Down>", self.history_down)
            self.input_entry.bind("<Tab>", self.complete)
            self.input_entry.bind("<Control-c>", self.interrupt)

            self.base_font = 12
            self.base_header = 12
            self.base_padx = 20
            self.base_pady = 20
            self.base_header_pady = 10
            self.base_in_pady = 12

    def toggle_fullscreen(self):
            if not self.is_fullscreen:
                self._saved_geometry = self.root.geometry()
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                self.root.geometry(f"{sw}x{sh}+0+0")
                self.is_fullscreen = True
            else:
                self.root.geometry(self._saved_geometry)
                self.is_fullscreen = False

    def minimize_btn_click(self):
            self.exit_saver()
            self._tlog("minimize_btn_click: hiding window")
            if os.name == "nt":
                self.root.iconify()
            else:
                self.root.withdraw()

    def restore_from_min(self):
            if not self.root.state() == "withdrawn":
                return
            self._tlog("restore_from_min")
            self.exit_saver()
            self.root.deiconify()
            try:
                self.root.attributes("-topmost", True)
                if os.name != "nt":
                    self.root.overrideredirect(True)
            except Exception:
                pass
            self.root.after_idle(self.force_focus)

    def _start_restore_listener(self):
            if not _HAS_XLIB:
                return

            def run():
                try:
                    d = display.Display()
                    try:
                        d.set_error_handler(lambda *a, **k: None)
                    except Exception:
                        pass
                    root = d.screen().root
                    keycode = d.keysym_to_keycode(XK.XK_b)
                    root.grab_key(keycode, X.Mod1Mask | X.ControlMask, 1,
                                  X.GrabModeAsync, X.GrabModeAsync)
                    self._tlog("restore hotkey active: Ctrl+Alt+B")
                    while True:
                        ev = d.next_event()
                        if ev.type == X.KeyPress:
                            try:
                                self.min_queue.put("restore")
                            except Exception:
                                pass
                except Exception:
                    pass

            threading.Thread(target=run, daemon=True).start()

    def on_escape(self, event):
            if self.is_fullscreen:
                self.toggle_fullscreen()
            else:
                self.quit_app()

    def close_btn_click(self):
            if self.term_active:
                self.term_exit()
            else:
                self.quit_app()

    def quit_app(self):
            if self.term_active and self.term_proc:
                try:
                    if self.term_proc.poll() is None:
                        self.term_proc.terminate()
                except Exception:
                    pass
            self._stop_recording()
            self.root.destroy()

    def get_edge(self, x, y):
            wx = self.root.winfo_x()
            wy = self.root.winfo_y()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            threshold = 6
            lx = x - wx
            ly = y - wy
            edges = []
            if lx <= threshold:
                edges.append("left")
            elif lx >= w - threshold:
                edges.append("right")
            if ly <= threshold:
                edges.append("top")
            elif ly >= h - threshold:
                edges.append("bottom")
            return edges

    def on_press(self, event):
            was_saver = self.saver_active
            self.register_activity()
            if was_saver:
                return
            widget = self.root.winfo_containing(event.x_root, event.y_root)
            if isinstance(widget, (tk.Button, tk.Entry, tk.Text, tk.Canvas)):
                return
            edges = self.get_edge(event.x_root, event.y_root)
            if edges:
                self.resize_data = {"edges": edges, "x": event.x_root, "y": event.y_root,
                                    "w": self.root.winfo_width(), "h": self.root.winfo_height(),
                                    "x": self.root.winfo_x(), "y": self.root.winfo_y()}
                self.drag_data = {"x": 0, "y": 0}
            else:
                self.drag_data = {"x": event.x, "y": event.y}
                self.resize_data = None

    def on_drag(self, event):
            if self.resize_data:
                rd = self.resize_data
                dx = event.x_root - rd["x"]
                dy = event.y_root - rd["y"]
                new_w = rd["w"]
                new_h = rd["h"]
                new_x = rd["x"]
                new_y = rd["y"]
                if "left" in rd["edges"]:
                    new_w = max(300, rd["w"] - dx)
                    new_x = rd["x"] + rd["w"] - new_w
                if "right" in rd["edges"]:
                    new_w = max(300, rd["w"] + dx)
                if "top" in rd["edges"]:
                    new_h = max(200, rd["h"] - dy)
                    new_y = rd["y"] + rd["h"] - new_h
                if "bottom" in rd["edges"]:
                    new_h = max(200, rd["h"] + dy)
                self.root.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
            elif self.drag_data["x"] != 0 or self.drag_data["y"] != 0:
                x = self.root.winfo_x() + event.x - self.drag_data["x"]
                y = self.root.winfo_y() + event.y - self.drag_data["y"]
                self.root.geometry(f"+{x}+{y}")

    def on_release(self, event):
            self.drag_data = {"x": 0, "y": 0}
            self.resize_data = None

    def on_motion(self, event):
            self.register_activity()
            edges = self.get_edge(event.x_root, event.y_root)
            if not edges:
                self.root.configure(cursor="")
            elif len(edges) == 1:
                if edges[0] in ("left", "right"):
                    self.root.configure(cursor="sb_h_double_arrow")
                else:
                    self.root.configure(cursor="sb_v_double_arrow")
            else:
                self.root.configure(cursor="fleur")

    def on_resize(self, event):
            if self._resize_id:
                self.root.after_cancel(self._resize_id)
            self._resize_id = self.root.after(30, self.apply_scale)

    def apply_scale(self):
            self._resize_id = None
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            scale = min(w / 1000, h / 700)
            scale = max(0.3, min(scale, 2.5))
            self._scale = scale

            fs = max(5, int(self.base_font * scale))
            hs = max(5, int(self.base_header * scale))

            px = max(6, int(self.base_padx * scale))
            py = max(6, int(self.base_pady * scale))
            hp = max(2, int(self.base_header_pady * scale))
            ip = max(2, int(self.base_in_pady * scale))

            self.body.pack_configure(padx=px, pady=py)
            self.header.pack_configure(pady=(0, hp))
            self.in_wrap.pack_configure(pady=(0, ip))

            self.output.configure(font=("Courier New", fs, "bold"))
            self.input_entry.configure(font=("Courier New", fs, "bold"))
            self.prompt_label.configure(font=("Courier New", fs, "bold"))
            self.header_label.configure(font=(self._pick_font("Blue Water",
                                                              "DejaVu Sans",
                                                              "Segoe UI"),
                                              max(10, int(hs * 1.6))))
            self.draw_round_btn(self.close_btn)
            self.draw_round_btn(self.fullscreen_btn)

            self.output.configure(padx=max(4, int(10 * scale)), pady=max(2, int(8 * scale)))

            if self.saver_active:
                self.show_saver_image()
            if self.term_active:
                self.term_resize()

            self.root.after_idle(self.output.see, "end")

    def submit(self, event=None):
            if self.saver_active:
                self.exit_saver()
                return
            text = self.input_var.get().strip()
            self.input_var.set("")
            if text:
                self.history.append(text)
                self.history_idx = len(self.history)
                self.register_activity()
            if text.startswith("/"):
                self.append_output(f"> {text}")
                self.process_command(text[1:].strip())
            elif text.startswith("!"):
                self.append_output(f"> {text}")
                self.process_command(text[1:].strip())
            elif text:
                self.append_output(f"> {text}")
                self.handle_chat(text)
            if not self.term_active:
                self.input_entry.focus_set()

    def append_output(self, text, speak=True):
            self.output.configure(state="normal")
            self.output.insert("end", text + "\n")
            self.output.see("end")
            self.output.configure(state="disabled")
            if speak and text.startswith("  BMO: "):
                self._speak(text)

    _THINKING_FRAMES = [
            "  \u0e1f(=\u03c9=)\u0e1f thinking.",
            "  \u0e1f(=\u03c9=)\u0e1f thinking..",
            "  \u0e1f(=\u03c9=)\u0e1f thinking...",
            "  \u0e1f(=\uff61=)\u0e1f thinking..",
            "  \u0e1f(=^-^=)\u0e1f thinking.",
        ]

    def _start_thinking(self):
            self._stop_thinking()
            self._thinking = True
            self._thinking_frame = 0
            self._tick_thinking()

    def _thinking_line(self):
            try:
                idx = self.output.search("\u0e1f(", "1.0", stopindex="end")
                if idx:
                    return "%s.0" % idx.split(".")[0]
            except Exception:
                pass
            return None

    def _tick_thinking(self):
            if not self._thinking:
                return
            frame = self._THINKING_FRAMES[self._thinking_frame % len(self._THINKING_FRAMES)]
            self._thinking_frame += 1
            try:
                self.output.configure(state="normal")
                li = self._thinking_line()
                if li is None:
                    self.output.insert("end", frame + "\n")
                else:
                    self.output.delete(li, li + " lineend +1c")
                    self.output.insert(li, frame + "\n")
                self.output.see("end")
                self.output.configure(state="disabled")
            except Exception:
                pass
            self._thinking_job = self.root.after(280, self._tick_thinking)

    def _stop_thinking(self):
            self._thinking = False
            if self._thinking_job is not None:
                try:
                    self.root.after_cancel(self._thinking_job)
                except Exception:
                    pass
                self._thinking_job = None
            li = self._thinking_line()
            if li is not None:
                try:
                    self.output.configure(state="normal")
                    self.output.delete(li, li + " lineend +1c")
                    self.output.configure(state="disabled")
                except Exception:
                    pass

    def _end_index(self):
            try:
                return self.output.index("end-1c")
            except Exception:
                return "end"

    def _set_status(self, text):
            try:
                self.status_label.configure(text=text)
            except Exception:
                pass

    def _stream_output(self, text):
            if self._stream_mark is None:
                self.append_output("  BMO: " + text)
                return
            try:
                self.output.configure(state="normal")
                self.output.delete(self._stream_mark, "end-1c")
                self.output.insert(self._stream_mark, "  BMO: " + text)
                self.output.see("end")
                self.output.configure(state="disabled")
            except Exception:
                self.append_output("  BMO: " + text)


    _BRAIN_CAT = [
            ["  \u2588\u2588   \u2588\u2588",
             " \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             " \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             " \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
             " \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             " \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             " \u2588 \u2588\u2588\u2588\u2588\u2588 \u2588"],
            ["   \u2588\u2588   \u2588\u2588",
             "  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             "  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             "  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
             "  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             "  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588",
             "  \u2588\u2588 \u2588\u2588 \u2588\u2588"],
        ]

    _BRAIN_MSG = "  please wait, loading BMO's brain"

    def _brain_block(self):
            frame = "\n".join(self._BRAIN_CAT[self._brain_frame % len(self._BRAIN_CAT)])
            return frame + "\n" + self._brain_msg + "." * (self._brain_frame % 3 + 1) + "\n"

    def _brain_nlines(self):
            return len(self._BRAIN_CAT[0]) + 1

    def _brain_region(self):
            try:
                idx = self.output.search("\u2588", "1.0", stopindex="end")
                if idx:
                    line = int(idx.split(".")[0])
                    return "%d.0" % line, "%d.0" % (line + self._brain_nlines())
            except Exception:
                pass
            return None, None

    def _start_brain_download(self, msg=None):
            self._brain_msg = msg if msg is not None else self._BRAIN_MSG
            self._stop_thinking()
            self._stop_brain_download()
            self._brain = True
            self._brain_frame = 0
            self._brain_job = None
            self._tick_brain()

    def _tick_brain(self):
            if not self._brain:
                return
            self._brain_frame += 1
            try:
                self.output.configure(state="normal")
                start, end = self._brain_region()
                if start:
                    self.output.delete(start, end)
                self.output.insert("end", self._brain_block())
                self.output.see("end")
                self.output.configure(state="disabled")
            except Exception:
                pass
            self._brain_job = self.root.after(250, self._tick_brain)

    def _stop_brain_download(self):
            self._brain = False
            if self._brain_job is not None:
                try:
                    self.root.after_cancel(self._brain_job)
                except Exception:
                    pass
                self._brain_job = None
            try:
                self.output.configure(state="normal")
                start, end = self._brain_region()
                if start:
                    self.output.delete(start, end)
                self.output.configure(state="disabled")
            except Exception:
                pass

    def process_command(self, cmd):
            cmd = cmd.strip()
            if cmd.startswith("!"):
                cmd = cmd[1:].strip()
            cmd_lower = cmd.lower()
            if cmd_lower in ("clear", "cls"):
                self.clear_output()
            elif cmd_lower in ("help", "?"):
                self.show_help()
            elif cmd_lower in ("fs", "fullscreen"):
                self.toggle_fullscreen()
            elif cmd_lower in ("exit", "quit"):
                self.quit_app()
            elif cmd_lower == "bmo":
                self.force_idle()
            elif cmd_lower.startswith("name"):
                self.cmd_name(cmd)
            elif cmd_lower == "voice":
                self.cmd_voice()
            elif cmd_lower.startswith("voice "):
                self.cmd_voice(cmd[6:].strip())
            elif cmd_lower == "memory":
                self.cmd_memory()
            elif cmd_lower == "forget":
                self.cmd_forget()
            elif cmd_lower == "model":
                self.cmd_model()
            elif cmd_lower.startswith("model "):
                self.cmd_model(cmd[6:].strip())
            elif cmd_lower == "talk":
                self.cmd_talk()
            elif cmd_lower.startswith("talk "):
                self.cmd_talk(cmd[5:].strip())
            elif cmd_lower == "update":
                self.cmd_update()
            elif cmd_lower.startswith("update "):
                self.cmd_update(cmd[7:].strip())
            elif cmd_lower in self.SHORTCUTS:
                self.start_term(self.SHORTCUTS[cmd_lower])
            elif cmd_lower.startswith("cd"):
                self.change_dir(cmd)
            elif cmd_lower == "":
                pass
            elif self._is_interactive(cmd):
                self.start_term(cmd)
            else:
                self.run_shell(cmd)

    def cmd_name(self, cmd):
            arg = cmd[4:].strip()
            if not arg:
                self.append_output("  BMO: Tell me your name with /name <name>!")
                return
            if self._reserved_name(arg):
                self.append_output("  BMO: That's my name! (I'm BMO \u2665) Try /name <your-name>!")
                return
            self.memory["name"] = arg[:40]
            self.pending_name = False
            self.pending_confirm = None
            self._save_memory()
            self.append_output(f"  BMO: Nice to meet you, {arg}! I'll remember you. \u2665")

    def cmd_memory(self):
            m = self.memory
            name = m.get("name")
            msgs = m.get("messages", [])
            self.append_output("  BMO MEMORY")
            self.append_output(f"    name: {name if name else '(not set)'}")
            self.append_output(f"    conversations saved: {len(msgs)} messages")
            self.append_output("  Use /forget to erase, /name <n> to change your name.")

    def cmd_forget(self):
            self.memory = {"name": self.memory.get("name", ""), "messages": []}
            self.memory.pop("oc_session", None)
            self._save_memory()
            self.append_output("  BMO: Ok, I'll forget our chats... but I still remember you! \u2665")

    def cmd_model(self, arg=None):
            if arg:
                self.memory["oc_model"] = arg
                self._save_memory()
                self.append_output(f"  BMO: my brain is now {arg}. \u2665")
                return
            self.append_output(f"  BMO: my brain is online via opencode -> {self.oc_model()}")
            self.append_output("       (switch it: /model <provider/model>)")

    def _load_memory(self):
            try:
                with open(self.mem_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"name": "", "messages": []}

    def _save_memory(self):
            try:
                os.makedirs(self.data_dir, exist_ok=True)
                with open(self.mem_file, "w", encoding="utf-8") as f:
                    json.dump(self.memory, f, ensure_ascii=False)
            except Exception as e:
                self._tlog("memory save failed: %s" % e)

    def _is_interactive(self, cmd):
            if cmd == "term" or cmd.startswith("term "):
                return True
            try:
                words = shlex.split(cmd)
            except Exception:
                words = cmd.split()
            return any(os.path.basename(w) in self.INTERACTIVE for w in words)

    def clear_output(self):
            self._stream_mark = None
            self._stop_thinking()
            self._stop_brain_download()
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.configure(state="disabled")

    def show_help(self):
            self.append_output("  BMO - your GameBoy friend \u2665")
            self.append_output("  Chat with me by typing! My brain is online via opencode,")
            self.append_output("  so I can answer anything (and even use my tools).")
            self.append_output("")
            self.append_output("  Commands start with '/' :")
            self.append_output("    /help            - this screen")
            self.append_output("    /name <name>     - tell me your name")
            self.append_output("    /memory          - what I remember")
            self.append_output("    /forget          - clear chat memory")
            self.append_output("    /model [name]    - show/change brain model")
            self.append_output("    /voice on|off    - BMO talks out loud (hold MIC to talk to him)")
            self.append_output("    /voice test      - hear my voice (pitch/speed/variant to tune it)")
            self.append_output("    /talk on|off     - BMO chats on his own")
            self.append_output("    /update now      - check for updates")
            self.append_output("    /mo              - open opencode")
            self.append_output("    /gmo             - open w3m browser")
            self.append_output("    /term <cmd>      - run a command in the embedded terminal")
            self.append_output("    /ls, /pwd, ...   - any shell command (prefix with /)")
            self.append_output("    /fs              - fullscreen")
            self.append_output("    /clear           - clear screen")
            self.append_output("    /quit            - close BMO")
            self.append_output("  Up/Down history - Tab complete - Ctrl+C interrupt")

    def update_prompt(self):
            name = os.path.basename(self.cwd) or self.cwd
            self.prompt_label.configure(text=f"{name} > ")

    def _drain_queue(self):
            try:
                while True:
                    item = self.min_queue.get_nowait()
                    if item == "restore":
                        self.restore_from_min()
            except queue.Empty:
                pass
            try:
                while True:
                    item = self.output_queue.get_nowait()
                    if item == "__proactive_next__":
                        self._schedule_proactive()
                        continue
                    if isinstance(item, tuple) and item[0] == "__ai_stream_init__":
                        self._stop_thinking()
                        self._stream_mark = self._end_index()
                        self._set_status("  BMO is answering \u2665")
                        continue
                    if isinstance(item, tuple) and item[0] == "__ai_stream__":
                        self._stream_output(item[1])
                        continue
                    if isinstance(item, tuple) and item[0] == "__ai_done__":
                        self._stream_mark = None
                        self._stop_thinking()
                        self.register_activity()
                        continue
                    if isinstance(item, tuple) and item[0] == "__brain_start__":
                        self._start_brain_download()
                        continue
                    if isinstance(item, tuple) and item[0] == "__brain_stop__":
                        self._stop_brain_download()
                        continue
                    if isinstance(item, tuple) and item[0] == "__brain_done__":
                        self.clear_output()
                        self.append_output("  BMO: Hey, everything's done! I'm all set and ready to chat \u2665")
                        continue
                    if isinstance(item, tuple) and item[0] == "__ears_start__":
                        self._start_brain_download("  please wait, downloading my ears...")
                        continue
                    if isinstance(item, tuple) and item[0] == "__ears_stop__":
                        self._stop_brain_download()
                        continue
                    if item == "__voice_start__":
                        self._start_brain_download("  please wait, downloading my human voice...")
                        continue
                    if item == "__voice_stop__":
                        self._stop_brain_download()
                        continue
                    if isinstance(item, tuple) and item[0] == "__transcribed__":
                        t = item[1]
                        if t:
                            self.input_var.set(t)
                            self.submit()
                        else:
                            self.append_output("  BMO: Hmm, I didn't catch that. Can you say it again?")
                        continue
                    if item == "__mic_stop__":
                        self._set_mic_state(False)
                        continue
                    if item == "__update_applied__":
                        self._relaunch()
                        continue
                    if isinstance(item, tuple) and item[0] == "__update_failed__":
                        self.append_output("  BMO: update failed (%s) - staying on v%s. \u2665" % (item[1], self.APP_VERSION))
                        continue
                    if isinstance(item, tuple) and item[0] == "__update_offer__":
                        self._offer_update(item[1])
                        continue
                    if isinstance(item, tuple) and item[0] == "__silent__":
                        self.append_output(item[1], speak=False)
                        continue
                    try:
                        self.append_output(item)
                    except Exception:
                        pass
            except queue.Empty:
                pass
            self.root.after(50, self._drain_queue)

    def welcome(self):
            self.append_output("  /\\_/\\")
            self.append_output("  ( o.o )")
            self.append_output("   > ^ <")
            self.append_output(f"  BMO v{self.APP_VERSION} - your GameBoy friend")
            self.append_output("  ═══════════════════════")
            self.append_output("")
            name = self.memory.get("name")
            if self.pending_name or not name:
                self.append_output("  BMO: Hi! I'm BMO, your GameBoy friend! ♥")
                self.append_output("       What's your name? (just type it)")
                if not self._ai_available():
                    self.append_output("       (I chat via opencode: curl -fsSL https://opencode.ai/install | bash)")
            else:
                self.append_output(f"  BMO: Hey {name}! Good to see you! ♥")
            self.append_output("")
            self.append_output("  Chat with me by typing, or use '/' commands: /help, /ls, /mo...")
            self.append_output("")


if __name__ == "__main__":
    app = GameBoyTerminal()
