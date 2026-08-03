"""Legacy entry shim (was the single-file BMO app).

Kept so older launchers (`bmo.pyw`, `bmo.bat`, installed copies) keep working
with the new multi-module layout. Routes straight to the real entry.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bmo_app import GameBoyTerminal  # noqa: E402

if __name__ == "__main__":
    app = GameBoyTerminal()
