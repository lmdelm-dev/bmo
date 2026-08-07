"""BMO - a cute GameBoy friend whose brain is opencode.

A single tidy module: the GameBoy window design + the opencode chat brain.
No faces, no voice, no embedded terminal - just design and the brain.
"""

import tkinter as tk
import json
import os
import queue
import time

from bmo_ai import AIMixin
import bmo_config as config


class BMO(AIMixin):
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BMO")
        self.root.geometry("1000x700+150+50")
        if os.name != "nt":
            self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#63BDA4")

        self.drag_data = {"x": 0, "y": 0}
        self._scale = 1.0
        self._base_font = 12
        self._base_padx = 20
        self._base_pady = 20
        self._base_header_pady = 10
        self._base_in_pady = 12

        self.data_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "bmo")
        self.mem_file = os.path.join(self.data_dir, "chat.json")
        self.memory = self._load_memory()
        self.mem_ready = True
        self._ver = config.APP_VERSION

        self.pending_name = not self.memory.get("name")
        self.pending_confirm = None

        self.output_queue = queue.Queue()
        self.proactive_on = True

        self._ai_busy = False
        self._stream_mark = None
        self._thinking = False
        self._thinking_frame = 0
        self._thinking_job = None

        self.build_ui()
        self.setup_bindings()
        self.update_prompt()
        self.welcome()

        self.root.after(50, self._drain_queue)
        self._schedule_proactive()
        self.root.after_idle(self.force_focus)
        self.root.mainloop()

    # ---------------- window design ----------------

    def build_ui(self):
        self.body = tk.Frame(self.root, bg="#63BDA4", padx=self._base_padx,
                             pady=self._base_pady)
        self.body.pack(fill="both", expand=True)

        self.header = tk.Frame(self.body, bg="#63BDA4", cursor="fleur")
        self.header.pack(fill="x", pady=(0, self._base_header_pady))
        self.header.bind("<Button-1>", self.on_press)
        self.header.bind("<B1-Motion>", self.on_drag)
        self.header.bind("<ButtonRelease-1>", self.on_release)

        self.header_label = tk.Label(self.header, text="BMO",
                                     font=(self._pick_font("Blue Water",
                                                           "DejaVu Sans",
                                                           "Segoe UI"), 20),
                                     bg="#63BDA4", fg="#101E2B")
        self.header_label.pack(side="left")

        led = tk.Canvas(self.header, width=12, height=12, bg="#63BDA4", highlightthickness=0)
        led.pack(side="right", padx=(0, 6))
        led.create_oval(1, 1, 11, 11, fill="#F20553", outline="")

        self.close_btn = self._round_btn(self.header, "#E1333F", "#B02230", "X",
                                         "#FFFFFF", self.close_btn_click)
        self.minimize_btn = self._round_btn(self.header, "#4A90D9", "#3A74B2", "_",
                                            "#FFFFFF", self.minimize_click)
        self.close_btn.pack(side="right")
        self.minimize_btn.pack(side="right")

        self.out_wrap = tk.Frame(self.body, bg="#407C84", bd=4, highlightthickness=0)
        self.out_wrap.pack(fill="both", expand=True, pady=(0, 8))

        out_scroll = tk.Scrollbar(self.out_wrap, bg="#63BDA4", troughcolor="#D9FFEA",
                                  activebackground="#407C84", bd=0, width=12)
        out_scroll.pack(side="right", fill="y")

        self.output = tk.Text(self.out_wrap, bg="#D9FFEA", fg="#101E2B",
                              font=("Courier New", self._base_font, "bold"),
                              wrap="word", state="disabled", padx=10, pady=8,
                              yscrollcommand=out_scroll.set, highlightthickness=0,
                              bd=0, insertofftime=-1, insertwidth=0)
        self.output.pack(fill="both", expand=True)
        out_scroll.config(command=self.output.yview)

        self.in_wrap = tk.Frame(self.body, bg="#407C84", bd=4, highlightthickness=0)
        self.in_wrap.pack(fill="x", pady=(0, self._base_in_pady))

        self.in_inner = tk.Frame(self.in_wrap, bg="#D9FFEA", bd=0)
        self.in_inner.pack(fill="x", padx=4, pady=4)

        self.prompt_label = tk.Label(self.in_inner, text="> ",
                                     font=("Courier New", self._base_font, "bold"),
                                     bg="#D9FFEA", fg="#101E2B")
        self.prompt_label.pack(side="left")

        self._input_var = tk.StringVar()
        self.input_entry = tk.Entry(self.in_inner, textvariable=self._input_var,
                                    font=("Courier New", self._base_font, "bold"),
                                    bg="#D9FFEA", fg="#101E2B",
                                    insertbackground="#101E2B", bd=0,
                                    highlightthickness=0)
        self.input_entry.pack(side="left", fill="x", expand=True)
        self.input_entry.bind("<Button-1>", lambda e: self.entry_click())
        self.in_inner.bind("<Button-1>", lambda e: self.entry_click())
        self.in_wrap.bind("<Button-1>", lambda e: self.entry_click())

    def entry_click(self):
        self.root.after_idle(self.force_focus)

    def _round_btn(self, parent, color, hover, text, text_color, command):
        btn = tk.Canvas(parent, bg="#63BDA4", highlightthickness=0, cursor="hand2")
        btn.bc = color
        btn.bh = hover
        btn.bt = text
        btn.tc = text_color
        btn.cmd = command
        btn.bind("<Button-1>", lambda e: btn.cmd())
        btn.bind("<Enter>", lambda e: self._btn_hover(btn, True))
        btn.bind("<Leave>", lambda e: self._btn_hover(btn, False))
        btn.configure(width=28, height=28)
        pad = 2
        btn.create_oval(pad, pad, 28 - pad, 28 - pad, fill=color, outline="")
        btn.create_text(14, 15, text=text, font=("Courier New", 8, "bold"),
                        fill=text_color)
        return btn

    def _btn_hover(self, btn, on):
        for i in btn.find_all():
            if btn.type(i) == "oval":
                btn.itemconfig(i, fill=btn.bh if on else btn.bc)

    def _pick_font(self, *names):
        try:
            from tkinter import font as tkfont
            fams = set(tkfont.families())
        except Exception:
            fams = set()
        for n in names:
            if n in fams:
                return n
        return "TkDefaultFont"

    def setup_bindings(self):
        self.root.bind("<Return>", self.submit)
        self.root.bind("<Escape>", self.close_btn_click)
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind("<Button-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.input_entry.bind("<Return>", self.submit)
        self.input_entry.bind("<Up>", self.history_up)
        self.input_entry.bind("<Down>", self.history_down)

        self.history = []
        self.history_idx = 0

    def toggle_fullscreen(self):
        if getattr(self, "_fs", False):
            self.root.geometry(self._saved_geom)
            self._fs = False
        else:
            self._saved_geom = self.root.geometry()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
            self._fs = True

    def minimize_click(self):
        self.root.withdraw()

    def restore(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.after_idle(self.force_focus)

    def close_btn_click(self):
        self.root.destroy()

    def force_focus(self):
        self.root.focus_force()
        self.input_entry.focus_force()

    def on_press(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if isinstance(widget, (tk.Entry, tk.Text)):
            return
        self.drag_data = {"x": event.x, "y": event.y}

    def on_drag(self, event):
        if self.drag_data["x"] != 0:
            x = self.root.winfo_x() + event.x - self.drag_data["x"]
            y = self.root.winfo_y() + event.y - self.drag_data["y"]
            self.root.geometry(f"+{x}+{y}")

    def on_release(self, event):
        self.drag_data = {"x": 0, "y": 0}

    def update_prompt(self):
        try:
            self.prompt_label.configure(text="> ")
        except Exception:
            pass

    # ---------------- chat plumbing ----------------

    def append_output(self, text, speak=True):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def append(self, text):
        self.append_output(text)

    def submit(self, event=None):
        text = self._input_var.get().strip()
        self._input_var.set("")
        if text:
            self.history.append(text)
            self.history_idx = len(self.history)
            self.append("> " + text)
            self.handle_chat(text)
        self.root.after_idle(self.force_focus)

    def history_up(self, event):
        if self.history and self.history_idx > 0:
            self.history_idx -= 1
            self._input_var.set(self.history[self.history_idx])
        return "break"

    def history_down(self, event):
        if self.history_idx < len(self.history):
            self.history_idx += 1
            if self.history_idx == len(self.history):
                self._input_var.set("")
            else:
                self._input_var.set(self.history[self.history_idx])
        return "break"

    def welcome(self):
        self.append("  /\\_/\\")
        self.append("  ( o.o )")
        self.append("   > ^ <")
        self.append(f"  BMO v{self._ver} - your GameBoy friend")
        self.append("  \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550")
        self.append("")
        name = self.memory.get("name")
        if self.pending_name or not name:
            self.append("  BMO: Hi! I'm BMO, your GameBoy friend! \u2665")
            self.append("       What's your name? (just type it)")
        else:
            self.append(f"  BMO: Hey {name}! Good to see you! \u2665")
        self.append("")
        self.append("  Just type anything and I'll chat with you!")
        self.append("")

    # ---------------- memory ----------------

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
            print("memory save failed:", e)

    # ---------------- thinking animation ----------------

    _THINKING_FRAMES = [
        "  (\u03c9) thinking.",
        "  (\u03c9) thinking..",
        "  (\u03c9) thinking...",
    ]

    def _start_thinking(self):
        self._stop_thinking()
        self._thinking = True
        self._thinking_frame = 0
        self._tick_thinking()

    def _thinking_line(self):
        try:
            idx = self.output.search("(\u03c9)", "1.0", stopindex="end")
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

    def _stream_output(self, text):
        try:
            self.output.configure(state="normal")
            if self._stream_mark is None:
                self._stream_mark = self._end_index()
            self.output.delete(self._stream_mark, "end-1c")
            self.output.insert(self._stream_mark, text)
            self.output.see("end")
            self.output.configure(state="disabled")
        except Exception:
            pass

    def _drain_queue(self):
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item == "__proactive_next__":
                    self._schedule_proactive()
                    continue
                if isinstance(item, tuple) and item[0] == "__ai_stream_init__":
                    self._stop_thinking()
                    self._stream_mark = self._end_index()
                    continue
                if isinstance(item, tuple) and item[0] == "__ai_stream__":
                    self._stream_output(item[1])
                    continue
                if isinstance(item, tuple) and item[0] == "__ai_done__":
                    self._stream_mark = None
                    self._stop_thinking()
                    continue
        except Exception:
            pass
        self.root.after(50, self._drain_queue)

    def _put(self, obj):
        self.output_queue.put(obj)

    def _tlog(self, msg):
        try:
            logpath = os.path.join(os.path.expanduser("~"), ".local", "share",
                                   "bmo", "bmo.log")
            os.makedirs(os.path.dirname(logpath), exist_ok=True)
            line = msg[0] if isinstance(msg, tuple) else msg
            with open(logpath, "a") as f:
                f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), line))
        except Exception:
            pass


if __name__ == "__main__":
    BMO()