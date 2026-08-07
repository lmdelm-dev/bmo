"""BMO central configuration.

APP_VERSION is the single source of truth. The auto-updater reads this file
(not the app entry) to compare versions, so bumping it here is enough.
"""

import os

APP_VERSION = "4.0"

# Entry point for the app (name that launchers execute).
APP_ENTRY = "bmo.py"

# Directory holding the app source files (this file lives in it).
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Auto-update feed: raw config file for version checks, tarball for installs.
UPDATE_URL = "https://raw.githubusercontent.com/lmdelm-dev/bmo/main/bmo_config.py"
UPDATE_TARBALL = "https://codeload.github.com/lmdelm-dev/bmo/tar.gz/refs/heads/main"
