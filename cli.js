#!/usr/bin/env node
/*
 * BMO npm/bun CLI.
 *   bmo             -> launch BMO (gameboy.py)
 *   bmo --install   -> download BMO source + assets into ./dist and ensure deps
 *                      (run automatically via package.json postinstall)
 *
 * The app itself is Python/tkinter; this package just fetches the Python
 * source from GitHub and runs it with the system Python 3.
 */
"use strict";

const { execFileSync, spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PKG_DIR = __dirname;
const DIST = path.join(PKG_DIR, "dist");
const APP_FILE = path.join(DIST, "gameboy.py");

const REPO = "https://github.com/lmdelm-dev/bmo";
const BRANCH = "main";

function run(cmd, args) {
  execFileSync(cmd, args, { stdio: "inherit" });
}

function pythonBin() {
  for (const c of ["python3", "python"]) {
    try {
      execFileSync(c, ["--version"], { stdio: "ignore" });
      return c;
    } catch (_) {}
  }
  throw new Error("BMO needs Python 3 (not found on PATH).");
}

function have(cmd) {
  try { execFileSync(cmd, ["--version"], { stdio: "ignore" }); return true; }
  catch (_) { return false; }
}

// Run a shell command, inheriting stdio so the user sees install progress/prompts.
function sh(cmd, args) {
  spawnSync(cmd, args, { stdio: "inherit" });
}

// Detect + install every dependency BMO needs. Non-fatal: warnings on failure.
function bootstrapDeps() {
  const isLinux = process.platform === "linux";
  const isMac = process.platform === "darwin";
  const isWin = process.platform === "win32";

  // --- Python 3 ---
  if (!have("python3") && !have("python")) {
    console.log("bmo: Python 3 not found - installing...");
    if (isLinux) {
      sh("bash", ["-c",
        "if command -v apt-get >/dev/null; then sudo apt-get update && sudo apt-get install -y python3 python3-tk python3-pip;" +
        " elif command -v zypper >/dev/null; then sudo zypper install -y python3 python3-tk python3-pip;" +
        " elif command -v dnf >/dev/null; then sudo dnf install -y python3 python3-tkinter python3-pip;" +
        " elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm python tk python-pip;" +
        " else echo '(no supported package manager - install python3+tkinter yourself)'; fi"]);
    } else if (isMac) {
      sh("bash", ["-c", "command -v brew >/dev/null && brew install python-tk || echo '(install python-tk via homebrew)'"]);
    } else if (isWin) {
      sh("powershell", ["-NoProfile", "-Command",
        "winget install --id Python.Python.3.12 --silent || echo '(install Python 3 from python.org)'"]);
    }
  }
  const py = pythonBin();

  // --- tkinter (python -c 'import tkinter') ---
  try { execFileSync(py, ["-c", "import tkinter"], { stdio: "ignore" }); }
  catch (_) {
    console.log("bmo: tkinter missing - installing...");
    if (isLinux) {
      sh("bash", ["-c",
        "if command -v apt-get >/dev/null; then sudo apt-get install -y python3-tk;" +
        " elif command -v zypper >/dev/null; then sudo zypper install -y python3-tk;" +
        " elif command -v dnf >/dev/null; then sudo dnf install -y python3-tkinter;" +
        " elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm tk; fi"]);
    } else if (isMac) {
      sh("bash", ["-c", "command -v brew >/dev/null && brew install python-tk || true"]);
    }
  }

  // --- xterm (embedded interactive terminal) - Linux only ---
  if (isLinux && !have("xterm")) {
    console.log("bmo: xterm missing (BMO's embedded terminal needs it) - installing...");
    sh("bash", ["-c",
      "if command -v apt-get >/dev/null; then sudo apt-get install -y xterm;" +
      " elif command -v zypper >/dev/null; then sudo zypper install -y xterm;" +
      " elif command -v dnf >/dev/null; then sudo dnf install -y xterm;" +
      " elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm xterm; fi"]);
  }

  // --- opencode (powers the 'mo' shortcut) ---
  if (!have("opencode")) {
    console.log("bmo: opencode missing - installing via curl -fsSL https://opencode.ai/install | bash ...");
    const ok = isWin
      ? spawnSync("powershell", ["-NoProfile", "-Command",
          "iwr -UseBasicParsing https://opencode.ai/install.ps1 | iex"], { stdio: "inherit" })
      : spawnSync("bash", ["-c", "curl -fsSL https://opencode.ai/install | bash"], { stdio: "inherit" });
    if (ok.status !== 0) console.log("bmo: (opencode install failed - 'mo' will look for opencode on PATH)");
    // ~/.opencode/bin may now exist; surface it for this process + later launches
    const oc = path.join(os.homedir(), ".opencode", "bin");
    if (fs.existsSync(oc)) process.env.PATH = oc + path.delimiter + process.env.PATH;
  }

  // --- Pillow + python-xlib (pip --user) ---
  try { execFileSync(py, ["-c", "import PIL"], { stdio: "ignore" }); }
  catch (_) {
    console.log("bmo: installing Pillow (face saver)...");
    try { sh(py, ["-m", "pip", "install", "--user", "Pillow"]); }
    catch (_) { console.log("bmo: (Pillow install failed - face saver disabled)"); }
  }
  if (isLinux) {
    try { execFileSync(py, ["-c", "import Xlib"], { stdio: "ignore" }); }
    catch (_) {
      console.log("bmo: installing python-xlib (minimize/restore hotkey)...");
      try { sh(py, ["-m", "pip", "install", "--user", "python-xlib"]); }
      catch (_) { console.log("bmo: (python-xlib install failed - restore hotkey disabled)"); }
    }
  }
  return py;
}

function install() {
  if (fs.existsSync(APP_FILE)) {
    console.log("bmo: already installed in", DIST);
    bootstrapDeps();
    installDesktopIcon();
    return;
  }
  console.log("bmo: downloading BMO from", REPO);
  fs.mkdirSync(DIST, { recursive: true });
  const tarball = path.join(os.tmpdir(), `bmo-${Date.now()}.tar.gz`);
  const url = `${REPO}/archive/refs/heads/${BRANCH}.tar.gz`;
  try {
    run("curl", ["-fsSL", url, "-o", tarball]);
  } catch (_) {
    // Windows fallback: PowerShell Invoke-WebRequest
    const script =
      `[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;` +
      `Invoke-WebRequest -Uri '${url}' -OutFile '${tarball}'`;
    run("powershell", ["-NoProfile", "-Command", script]);
  }
  // tar is present on Windows 10+ and all Unix-likes
  run("tar", ["xzf", tarball, "--strip-components=1", "-C", DIST]);
  fs.unlinkSync(tarball);

  // Blue Water font - applied instantly (fc-cache after writing it)
  copyFont();

  bootstrapDeps();
  console.log("bmo: installed. Run 'bmo' to start.");
  installDesktopIcon();
}

// Ship the Blue Water logo font into the per-user font dir and refresh the cache
// so the font is available immediately (no restart, theme applies on launch).
function copyFont() {
  if (process.platform === "win32") return; // Windows font handling is via the .pyw launcher
  const src = path.join(DIST, "assets", "Blue Water.otf");
  if (!fs.existsSync(src)) return;
  let fontDir = path.join(os.homedir(), ".local", "share", "fonts");
  if (process.platform === "darwin") fontDir = path.join(os.homedir(), "Library", "Fonts");
  try {
    fs.mkdirSync(fontDir, { recursive: true });
    fs.copyFileSync(src, path.join(fontDir, "Blue Water.otf"));
    if (have("fc-cache")) spawnSync("fc-cache", ["-f", fontDir], { stdio: "ignore" });
    console.log("bmo: Blue Water font installed (applies on next launch).");
  } catch (_) { console.log("bmo: (could not install Blue Water font - theme will use a fallback)"); }
}

function installDesktopIcon() {
  if (process.platform !== "linux" && process.platform !== "darwin") return;
  let desktop = process.env.XDG_DESKTOP_DIR || null;
  if (!desktop) {
    try {
      const out = execFileSync("xdg-user-dir", ["DESKTOP"], { encoding: "utf8" });
      desktop = out.trim();
    } catch (_) {
      desktop = path.join(os.homedir(), "Desktop");
    }
  }
  if (!desktop || !fs.existsSync(desktop)) return;

  const launcher = path.join(DIST, "bmo");
  const icon = path.join(DIST, "assets", "bmo-icon.png");
  const entryPath = path.join(desktop, "bmo.desktop");
  const content =
    `[Desktop Entry]\n` +
    `Name=BMO\n` +
    `Comment=GameBoy-style terminal\n` +
    `GenericName=Terminal\n` +
    `Exec=${launcher}\n` +
    `Icon=${icon}\n` +
    `Type=Application\n` +
    `Categories=Utility;TerminalEmulator;\n` +
    `Terminal=false\n` +
    `StartupNotify=false\n`;
  try {
    fs.writeFileSync(entryPath, content);
    fs.chmodSync(entryPath, 0o755);
  } catch (err) {
    console.log("bmo: (could not create desktop launcher)");
    return;
  }
  if (process.platform === "linux") {
    // mark as trusted so double-click works on GNOME too
    try {
      spawnSync("gio", ["set", entryPath, "metadata::trusted", "true"],
                { stdio: "ignore" });
    } catch (_) {}
  }
  console.log("bmo: desktop launcher created -> " + entryPath);
}

function launch() {
  if (!fs.existsSync(APP_FILE)) {
    console.log("bmo: not installed yet - running --install first");
    install();
  }
  const py = pythonBin();
  spawn(py, [APP_FILE, ...process.argv.slice(2)], { stdio: "inherit" })
    .on("exit", (code) => process.exit(code === null ? 1 : code));
}

if (process.argv.includes("--install")) {
  install();
} else {
  launch();
}
