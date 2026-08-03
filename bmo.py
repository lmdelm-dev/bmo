"""BMO entry point.

Runs the full app from the multi-module layout. Launchers should call this
file (or the legacy `gameboy.py` shim, which routes here).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bmo_app import GameBoyTerminal  # noqa: E402

if __name__ == "__main__":
    app = GameBoyTerminal()
