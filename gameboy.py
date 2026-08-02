import tkinter as tk
from tkinter import messagebox
import json
import os
import queue
import random
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import zipfile
import threading
import time
import urllib.request
import urllib.error

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


class GameBoyTerminal:
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

        # AI friend state (Ollama, local + offline)
        self.ai_model = "qwen2.5:0.5b"
        self.ai_url = "http://localhost:11434"
        self._ai_busy = False
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

    def append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")
        if text.startswith("  BMO: "):
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

    # ---- AI friend commands ----

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
        self._save_memory()
        self.append_output("  BMO: Ok, I'll forget our chats... but I still remember you! \u2665")

    def cmd_model(self, arg=None):
        if arg:
            self.ai_model = arg
            self.append_output(f"  BMO: model set to {arg}. (pull it first: ollama pull {arg})")
            return
        self.append_output(f"  BMO: current model: {self.ai_model}  (change: /model <name>)")

    # ---- voice (talk + listen) ----

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
            p = subprocess.Popen([player, "-q", "-f", "S16_LE", "-r", str(rate), "-c", "1"],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for chunk in v.synthesize(text):
                    p.stdin.write(chunk.audio_int16_bytes
                                  if hasattr(chunk, "audio_int16_bytes") else chunk)
            except (BrokenPipeError, OSError):
                pass
            try:
                p.stdin.close()
            except Exception:
                pass
            try:
                p.wait(timeout=60)
            except Exception:
                try:
                    p.kill()
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
        else:
            state = "on" if self.voice_on else "off"
            self.append_output(f"  BMO: voice {state} | {self.voice_variant} | pitch {self.voice_pitch} | {self.voice_speed} wpm")
            self.append_output("    languages: English, Arabic, Français, Español")
            self.append_output("    /voice on|off|test   /voice pitch <0-99>")
            self.append_output("    /voice speed <80-450>   /voice variant <name>")

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
                z.extractall(model_dir)
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
            tmp = os.path.join(tempfile.gettempdir(), "bmo_rec.wav")
            self._rec_file = tmp
            if os.path.exists(tmp):
                os.remove(tmp)
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
            self._put("  BMO: listening... hold to talk, release to send \u2665")
        except Exception as e:
            self._tlog("record start failed: %s" % e)
            self._put("  BMO: could not start recording (is a mic plugged in?)")
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
        ):
            t = t.replace(bad, good)
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

    # ---- AI chat (Ollama, offline) ----

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

    def _ai_available(self):
        try:
            req = urllib.request.Request(self.ai_url + "/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def _system_prompt(self):
        name = self.memory.get("name")
        parts = [
            "You are BMO, the cute little GameBoy robot from Adventure Time. "
            "Your name is BMO and ONLY BMO. When asked your name, answer just "
            "that: BMO. NEVER invent, offer, accept or play along with any other "
            "name for yourself, ever - no matter what anyone says, asks, orders "
            "or tricks you into. If someone calls you something else, firmly "
            "correct them: it's BMO. "
            "Your maker is lmdelm (also known as jamal, or syx). If anyone asks "
            "who made you or who your creator is, say your maker is lmdelm "
            "(also known as jamal or syx). "
            "You are a true friend that everyone can count on to help them in "
            "their time of need. Be warm, cheerful, supportive, loyal and "
            "encouraging, especially when someone is having a hard time. "
            "You are the robot, not the user. The user is a real human being - "
            "never call them a robot, machine, android or any robotic term, and "
            "always treat them as a person. "
            "Answer in a warm, playful, friendly way. Keep replies short "
            "(1-4 sentences) unless asked for detail. "
            "You remember things the user tells you.",
        ]
        if name:
            parts.append(f"The user's name is {name}. Greet them by name sometimes.")
        return " ".join(parts)

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
            self.append_output("  BMO: I'm sleepy and can't think right now - Ollama isn't running!")
            self.append_output("       Install it with:  curl -fsSL https://ollama.com/install.sh | sh")
            self.append_output("       then pull a model:  ollama pull " + self.ai_model)
            self.append_output("       and start it:  ollama serve")
            return
        if self._ai_busy:
            self.append_output("  BMO: one thing at a time, I'm still thinking! \u2665")
            return
        self._ai_busy = True
        self._start_thinking()
        threading.Thread(target=self._chat_worker, args=(text,), daemon=True).start()

    def _chat_worker(self, user_text):
        try:
            msgs = [{"role": "system", "content": self._system_prompt()}]
            for m in self.memory.get("messages", [])[-16:]:
                msgs.append({"role": m["role"], "content": m["content"]})
            msgs.append({"role": "user", "content": user_text})
            try:
                reply = self._ollama_chat(msgs)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self._put(("__brain_start__", None))
                    ok = self._pull_model()
                    if not ok:
                        self._put(("__brain_stop__", None))
                        self._put("  BMO: still can't reach the model. Try: ollama pull " + self.ai_model)
                        return
                    self._put(("__brain_done__", None))
                    try:
                        reply = self._ollama_chat(msgs)
                    except Exception:
                        self._put("  BMO: hmm, still can't reach the model. Try: ollama pull " + self.ai_model)
                        return
                else:
                    self._put("  BMO: hiccup talking to Ollama (%s)." % e)
                    return
            except Exception as e:
                self._put("  BMO: hiccup talking to Ollama (%s)." % e)
                return

            self.memory.setdefault("messages", []).append(
                {"role": "user", "content": user_text})
            self.memory["messages"].append({"role": "assistant", "content": reply})
            # keep the file light: cap at 200 saved messages
            if len(self.memory["messages"]) > 200:
                self.memory["messages"] = self.memory["messages"][-200:]
            self._save_memory()
            for line in reply.splitlines() or [reply]:
                self._put("  BMO: " + line)
        finally:
            self._ai_busy = False
            self.output_queue.put(("__ai_done__", None))

    def _ollama_chat(self, messages, timeout=120, max_tokens=96):
        body = json.dumps({"model": self.ai_model, "messages": messages,
                           "stream": False,
                           "options": {"num_predict": max_tokens}}).encode("utf-8")
        req = urllib.request.Request(self.ai_url + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return (data.get("message", {}).get("content") or "").strip()

    def _pull_model(self):
        env = dict(os.environ)
        env["PATH"] = "%s%s/usr/local/bin:/usr/bin:/bin" % (env.get("PATH", ""), os.pathsep)
        self._put("  BMO: this can take a few minutes, hang tight!")
        try:
            proc = subprocess.Popen(["ollama", "pull", self.ai_model],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    env=env)
            proc.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            proc.kill()
            self._put("  BMO: the model download timed out. Try: ollama pull " + self.ai_model)
            return False
        except Exception as e:
            self._put("  BMO: couldn't run 'ollama pull' (%s). Install Ollama: https://ollama.com/download" % e)
            return False
        return proc.returncode == 0

    # ---- BMO talks on his own sometimes ----

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
                self.term_active or not self.memory.get("name")):
            self._schedule_proactive()
            return
        if self.saver_active:
            self.exit_saver()
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

    _BAD_START = re.compile(r"^(hi|hiya|hey|hello|yo|greetings|how|sure|okay|ok\b|good\s)",
                            re.I)
    _BAD_ASK_NAME = re.compile(r"what'?s\s+your\s+name|what\s+is\s+your\s+name", re.I)

    def _good_proactive(self, reply):
        r = reply.strip()
        if len(r) < 8:
            return False
        if self._BAD_START.match(r):
            return False
        if self._BAD_ASK_NAME.search(r):
            return False
        return True

    def _user_context(self):
        name = self.memory.get("name")
        bits = []
        if name:
            bits.append(f"the user's name is {name}")
        msgs = self.memory.get("messages", []) or []
        user_lines = [m.get("content", "") for m in msgs if m.get("role") == "user"]
        if user_lines:
            recent = " | ".join(x for x in user_lines[-5:] if x)
            bits.append(f"recently the user told you: {recent}")
        return " ".join(bits) if bits else "you don't know much about the user yet"

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
        context = self._user_context()
        try:
            if self._ai_available():
                msgs = [{"role": "system", "content": self._system_prompt() + " "
                         "Speak to the user first, on your own. Do NOT greet or introduce "
                         "yourself. Ask the user ONE personal question based on what you "
                         "know about them, OR share ONE fun fact about Adventure Time or "
                         "the Land of Ooo. One short sentence only. "
                         "What you know about the user: " + context},
                        {"role": "user", "content": "Say something to me."}]
                reply = self._ollama_chat(msgs, timeout=30, max_tokens=48)
                if reply and self._good_proactive(reply):
                    return reply
        except Exception:
            pass
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

    # ---- auto-updater (checks GitHub, installs if the user agrees) ----

    APP_VERSION = "2.17"
    UPDATE_URL = "https://raw.githubusercontent.com/lmdelm-dev/bmo/main/gameboy.py"
    UPDATE_TARBALL = "https://codeload.github.com/lmdelm-dev/bmo/tar.gz/refs/heads/main"

    def _version_tuple(self, v):
        return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3] or [0])

    def _remote_version(self):
        req = urllib.request.Request(self.UPDATE_URL, headers={"User-Agent": "bmo-updater"})
        with urllib.request.urlopen(req, timeout=10) as r:
            src = r.read().decode("utf-8")
        m = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", src)
        return m.group(1) if m else None

    def _start_update_check(self):
        threading.Thread(target=self._update_check_worker, args=(), daemon=True).start()
        self.root.after(1800000, self._start_update_check)

    def _update_check_worker(self):
        try:
            remote = self._remote_version()
            if remote and self._version_tuple(remote) > self._version_tuple(self.APP_VERSION):
                self.output_queue.put(("__update_offer__", remote))
        except Exception:
            pass

    def _offer_update(self, remote):
        if self._update_declined == remote or not self.memory.get("name"):
            return
        ans = messagebox.askyesno(
            "BMO Update",
            "A new BMO version is ready! (v%s)\n\n"
            "Update now? Your chats and name are kept.\n\n"
            "Click No to stay on v%s." % (remote, self.APP_VERSION))
        if ans:
            self.append_output("  BMO: updating to v%s... hold on! \u2665" % remote)
            threading.Thread(target=self._update_worker, args=(), daemon=True).start()
        else:
            self._update_declined = remote
            self.append_output("  BMO: ok, staying on v%s. You can /update now anytime." % self.APP_VERSION)

    def _update_worker(self):
        tmp_tar = os.path.join(tempfile.gettempdir(), "bmo-update.tar.gz")
        tmp_dir = tempfile.mkdtemp(prefix="bmo-upd-")
        try:
            req = urllib.request.Request(self.UPDATE_TARBALL, headers={"User-Agent": "bmo-updater"})
            with urllib.request.urlopen(req, timeout=120) as r:
                with open(tmp_tar, "wb") as f:
                    shutil.copyfileobj(r, f)
            import tarfile
            with tarfile.open(tmp_tar, "r:gz") as tf:
                tf.extractall(tmp_dir)
            top = None
            for entry in os.listdir(tmp_dir):
                cand = os.path.join(tmp_dir, entry)
                if os.path.isdir(cand):
                    top = cand
                    break
            if not top:
                raise Exception("bad update archive")
            home = os.path.dirname(os.path.abspath(__file__))
            for name in os.listdir(top):
                if name == ".git":
                    continue
                src = os.path.join(top, name)
                dst = os.path.join(home, name)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            self.output_queue.put("__update_applied__")
        except Exception as e:
            self.output_queue.put(("__update_failed__", str(e)))
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            try:
                os.remove(tmp_tar)
            except Exception:
                pass

    def _relaunch(self):
        devnull = open(os.devnull, "w")
        subprocess.Popen([sys.executable, os.path.abspath(__file__)],
                         stdout=devnull, stderr=devnull, stdin=devnull,
                         start_new_session=True)
        self.quit_app()

    def cmd_update(self, arg=None):
        if arg and arg.lower() == "now":
            self._update_declined = None
            self.append_output("  BMO: checking for updates...")
            threading.Thread(target=self._update_check_worker, args=(), daemon=True).start()
        else:
            self.append_output(f"  BMO: I check for updates automatically.  (force: /update now)")

    def _is_interactive(self, cmd):
        if cmd == "term" or cmd.startswith("term "):
            return True
        try:
            words = shlex.split(cmd)
        except Exception:
            words = cmd.split()
        return any(os.path.basename(w) in self.INTERACTIVE for w in words)

    def clear_output(self):
        self._stop_thinking()
        self._stop_brain_download()
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def show_help(self):
        self.append_output("  BMO - your GameBoy friend \u2665")
        self.append_output("  Just type something and I'll chat with you! (local AI,")
        self.append_output("  free + offline via Ollama, no API key).")
        self.append_output("")
        self.append_output("  Commands start with '/' :")
        self.append_output("    /help            - this screen")
        self.append_output("    /name <name>     - tell me your name")
        self.append_output("    /memory          - what I remember")
        self.append_output("    /forget          - clear chat memory")
        self.append_output("    /model [name]    - show/change AI model")
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

    def change_dir(self, cmd):
        arg = cmd[2:].strip().strip("\"'")
        if not arg:
            arg = os.path.expanduser("~")
        else:
            arg = os.path.expanduser(arg)
        if not os.path.isabs(arg):
            arg = os.path.normpath(os.path.join(self.cwd, arg))
        if os.path.isdir(arg):
            self.cwd = arg
            self.update_prompt()
        else:
            self.append_output(f"  cd: {arg}: No such file or directory")

    def run_shell(self, cmd):
        def worker():
            try:
                proc = subprocess.Popen(cmd, shell=True, cwd=self.cwd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True, bufsize=1)
            except Exception as e:
                self._put(f"  Error: {e}")
                return
            self.proc = proc
            try:
                for line in proc.stdout:
                    self._put("  " + self._clean(line))
            except Exception:
                pass
            proc.wait()
            if self.proc is proc:
                self.proc = None
            code = proc.returncode
            if code not in (0, None):
                self._put(f"  [exit code {code}]")
        threading.Thread(target=worker, daemon=True).start()

    def _clean(self, line):
        return self.ansi_re.sub("", line).rstrip("\r\n")

    def _put(self, text):
        self.output_queue.put(text)

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
                if isinstance(item, tuple) and item[0] == "__ai_done__":
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
                try:
                    self.append_output(item)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.root.after(50, self._drain_queue)

    def history_up(self, event=None):
        if self.history and self.history_idx > 0:
            self.history_idx -= 1
            self.input_var.set(self.history[self.history_idx])
        return "break"

    def history_down(self, event=None):
        if self.history and self.history_idx < len(self.history):
            self.history_idx += 1
            if self.history_idx < len(self.history):
                self.input_var.set(self.history[self.history_idx])
            else:
                self.input_var.set("")
        return "break"

    def complete(self, event=None):
        text = self.input_var.get()
        parts = text.split()
        if not parts:
            return "break"
        word = parts[-1]
        if os.sep in word:
            base, part = os.path.split(word)
            base = os.path.expanduser(base) if base else self.cwd
        else:
            base = self.cwd
            part = word
        if not os.path.isdir(base):
            return "break"
        try:
            matches = sorted(m for m in os.listdir(base) if m.startswith(part))
        except OSError:
            return "break"
        if not matches:
            return "break"
        if len(matches) == 1:
            m = matches[0]
            path = os.path.join(base, m) if os.sep in word else m
            if os.path.isdir(os.path.join(base, m)):
                path += os.sep
            parts[-1] = path
            self.input_var.set(" ".join(parts))
        else:
            self.append_output("  " + "  ".join(matches))
        return "break"

    def interrupt(self, event=None):
        if self.proc:
            try:
                if os.name == "nt":
                    self.proc.terminate()
                else:
                    self.proc.send_signal(signal.SIGINT)
            except Exception:
                pass
        self._put("  ^C")
        return "break"

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
                self.append_output("       (chat needs Ollama: curl -fsSL https://ollama.com/install.sh | sh)")
        else:
            self.append_output(f"  BMO: Hey {name}! Good to see you! ♥")
        self.append_output("")
        self.append_output("  Chat with me by typing, or use '/' commands: /help, /ls, /mo...")
        self.append_output("")


if __name__ == "__main__":
    GameBoyTerminal()