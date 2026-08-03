"""BMO self-update mixin."""

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

from tkinter import messagebox

import bmo_config as config
import bmo_secure as secure

class UpdateMixin:
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
                    secure.safe_extract_members(tf, tmp_dir)
                top = None
                for entry in os.listdir(tmp_dir):
                    cand = os.path.join(tmp_dir, entry)
                    if os.path.isdir(cand):
                        top = cand
                        break
                if not top:
                    raise Exception("bad update archive")
                home = config.APP_DIR
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
            subprocess.Popen([sys.executable, os.path.join(config.APP_DIR, config.APP_ENTRY)],
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

