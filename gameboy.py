import tkinter as tk
import os
import queue
import random
import re
import shlex
import shutil
import signal
import subprocess
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
                 "left": "face_left.jpg", "right": "face_right.jpg"}
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
        self.saver_state = "normal"
        self.append_output("  BMO fell asleep... move mouse or press a key to wake up.")
        self.saver_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.saver_canvas.focus_set()
        self.root.update_idletasks()
        self.show_saver_image()
        self.schedule_blink()
        self.schedule_orientation()

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
        self._schedule_saver_job(random.randint(1000, 3000), self.do_blink)

    def do_blink(self):
        if not self.saver_active:
            return
        if self.saver_state == "normal":
            self.show_saver_image(blink=True)
            self._schedule_saver_job(180, self.end_blink)
        self.schedule_blink()

    def end_blink(self):
        if self.saver_active:
            self.show_saver_image()

    def schedule_orientation(self):
        self._schedule_saver_job(random.randint(120000, 300000), self.change_orientation)

    def change_orientation(self):
        if not self.saver_active:
            return
        self.saver_state = random.choice(["normal", "left", "right"])
        self.show_saver_image()
        self.schedule_orientation()

    def show_saver_image(self, blink=False):
        cw = self.saver_canvas.winfo_width()
        ch = self.saver_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        key = "blink" if blink else (self.saver_state or "normal")
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
        if (not self.saver_active and not self.term_active
                and (time.time() - self.last_activity) >= 60):
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
        self.append_output(f"> {text}")
        if text:
            self.history.append(text)
            self.history_idx = len(self.history)
            self.process_command(text)
        if not self.term_active:
            self.input_entry.focus_set()

    def append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

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

    def _is_interactive(self, cmd):
        if cmd == "term" or cmd.startswith("term "):
            return True
        try:
            words = shlex.split(cmd)
        except Exception:
            words = cmd.split()
        return any(os.path.basename(w) in self.INTERACTIVE for w in words)

    def clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def show_help(self):
        self.append_output("  BMO TERMINAL - real shell (Windows & Linux)")
        self.append_output("  Type any system command: ls, pwd, dir, echo, ...")
        self.append_output("  Interactive apps (opencode, vim, bash, python, ...)")
        self.append_output("  run in a real embedded terminal; 'term <cmd>' forces it")
        self.append_output("  Shortcuts: mo = opencode, bmo = force idle,")
        self.append_output("             gmo = browser (w3m)")
        self.append_output("  Up/Down       - command history")
        self.append_output("  Tab           - autocomplete")
        self.append_output("  Ctrl+C        - interrupt running command")
        self.append_output("  clear / cls   - clear screen")
        self.append_output("  fs            - fullscreen")
        self.append_output("  exit / quit   - close")

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
        self.append_output("  BMO TERMINAL v2.1")
        self.append_output("  ═══════════════")
        self.append_output("")
        self.append_output("  Real shell (Windows & Linux)")
        self.append_output("  Type any command, e.g. ls")
        self.append_output("  Interactive apps (opencode, vim, python...) run in a")
        self.append_output("  real embedded terminal (xterm) - full colors + keys")
        self.append_output("  Up/Down history - Tab complete - Ctrl+C interrupt")
        self.append_output("  Press F11 for fullscreen.")
        self.append_output("")


if __name__ == "__main__":
    GameBoyTerminal()