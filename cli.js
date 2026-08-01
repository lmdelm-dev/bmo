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

const { execFileSync, spawn } = require("child_process");
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

function install() {
  if (fs.existsSync(APP_FILE)) {
    console.log("bmo: already installed in", DIST);
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

  const py = pythonBin();
  try {
    console.log("bmo: ensuring Pillow (face saver) ...");
    run(py, ["-m", "pip", "install", "--user", "Pillow"]);
  } catch (_) {
    console.log("bmo: (Pillow not installed - BMO still runs, saver disabled)");
  }
  if (process.platform === "linux") {
    try {
      console.log("bmo: ensuring python-xlib (minimize restore hotkey) ...");
      run(py, ["-m", "pip", "install", "--user", "python-xlib"]);
    } catch (_) {
      console.log("bmo: (python-xlib not installed - restore hotkey disabled)");
    }
  }
  console.log("bmo: installed. Run 'bmo' to start.");
  installDesktopIcon();
}

function installDesktopIcon() {
  if (process.platform !== "linux" && process.platform !== "darwin") return;
  let desktop = null;
  try {
    const out = execFileSync("xdg-user-dir", ["DESKTOP"], { encoding: "utf8" });
    desktop = out.trim();
  } catch (_) {
    desktop = path.join(os.homedir(), "Desktop");
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
    if (process.platform === "linux") {
      // mark as trusted so double-click works on GNOME too
      spawnSync("gio", ["set", entryPath, "metadata::trusted", "true"],
                { stdio: "ignore" });
    }
    console.log("bmo: desktop launcher created -> " + entryPath);
  } catch (_) {
    console.log("bmo: (could not create desktop launcher)");
  }
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
