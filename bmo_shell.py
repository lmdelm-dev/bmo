"""BMO shell mixin - embedded shell commands, history, completion."""

import os
import re
import signal
import subprocess
import threading

class ShellMixin:
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

