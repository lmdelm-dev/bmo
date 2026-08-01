# BMO for Windows - double-click this file (runs with pythonw, no console)
import os
import runpy

APP_DIR = os.path.dirname(os.path.abspath(__file__))
runpy.run_path(os.path.join(APP_DIR, "gameboy.py"), run_name="__main__")
