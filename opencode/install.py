#!/usr/bin/env python3
"""Install the BMO theme + header logo into opencode's config.

Writes:
  ~/.config/opencode/themes/bmo.json       (theme)
  ~/.config/opencode/tui-plugins/bmo-logo.tsx   (header logo plugin)
  ~/.config/opencode/tui.json              (sets theme: "bmo" + the logo plugin,
                                            preserving any existing fields/plugins)

Safe to run repeatedly; never destroys an existing tui.json.
Pass an alternate config dir as argv[1] (used for tests).
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
OC = os.path.join(os.path.expanduser("~"), ".config", "opencode")
if len(sys.argv) > 1:
    OC = os.path.expanduser(sys.argv[1])

THEME_DIR = os.path.join(OC, "themes")
PLUGIN_DIR = os.path.join(OC, "tui-plugins")
os.makedirs(THEME_DIR, exist_ok=True)
os.makedirs(PLUGIN_DIR, exist_ok=True)

shutil.copyfile(os.path.join(HERE, "bmo.json"), os.path.join(THEME_DIR, "bmo.json"))
shutil.copyfile(os.path.join(HERE, "bmo-logo.tsx"), os.path.join(PLUGIN_DIR, "bmo-logo.tsx"))

tui_path = os.path.join(OC, "tui.json")
data = {}
if os.path.exists(tui_path):
    try:
        with open(tui_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
data.setdefault("$schema", "https://opencode.ai/tui.json")
data["theme"] = "bmo"
plugins = data.get("plugin", [])
if not isinstance(plugins, list):
    plugins = [plugins]
logo = os.path.join(PLUGIN_DIR, "bmo-logo.tsx")
if logo not in plugins:
    plugins.append(logo)
data["plugin"] = plugins
with open(tui_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

print("BMO opencode theme + logo installed (restart opencode to apply).")
