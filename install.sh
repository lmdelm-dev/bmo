#!/usr/bin/env bash
# BMO - GameBoy terminal
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/lmdelm-dev/bmo/main/install.sh | bash
set -euo pipefail

REPO="${BMO_REPO:-https://github.com/lmdelm-dev/bmo}"
BRANCH="${BMO_BRANCH:-main}"

DEST="${BMO_HOME:-$HOME/.local/share/bmo}"
BIN_DIR="${BMO_BIN:-$HOME/.local/bin}"
ICON_DIR="$HOME/.local/share/icons"
APP_DIR="$HOME/.local/share/applications"
FONT_DIR="$HOME/.local/share/fonts"

echo "==> BMO installer"
echo "    repo: $REPO"
echo "    install dir: $DEST"

need() {
    command -v "$1" >/dev/null 2>&1
}

if ! need curl && ! need wget; then
    echo "ERROR: need 'curl' or 'wget' to download BMO." >&2
    exit 1
fi
if ! need python3; then
    echo "ERROR: BMO needs Python 3. Install it, then re-run." >&2
    exit 1
fi

# 1. tkinter (usually a distro package, not pip-installable)
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "NOTE: Python tkinter is missing."
    if need apt-get; then
        echo "  run:  sudo apt-get install -y python3-tk"
    elif need zypper; then
        echo "  run:  sudo zypper install -y python3-tk"
    elif need dnf; then
        echo "  run:  sudo dnf install -y python3-tkinter"
    elif need pacman; then
        echo "  run:  sudo pacman -S --noconfirm tk"
    fi
    echo "  (after installing tkinter, re-run this installer)"
    exit 1
fi

# 2. download + extract source into DEST
mkdir -p "$DEST"
if need curl; then
    curl -fsSL "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar xz --strip-components=1 -C "$DEST"
else
    wget -qO- "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar xz --strip-components=1 -C "$DEST"
fi

# 3. optional python deps (user-level pip)
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "==> installing Pillow (for BMO's face saver)..."
    python3 -m pip install --user Pillow || \
        echo "WARN: Pillow install failed; BMO runs, but the idle face saver is disabled."
fi
case "$(uname -s)" in
    Linux*)
        if ! python3 -c "import Xlib" 2>/dev/null; then
            echo "==> installing python-xlib (for minimize restore hotkey)..."
            python3 -m pip install --user python-xlib || \
                echo "WARN: python-xlib install failed; minimize restore hotkey will be disabled."
        fi
        ;;
esac

# 4. launcher
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/bmo" <<EOF
#!/usr/bin/env bash
# BMO launcher
export BMO_HOME="$DEST"
exec python3 "$DEST/gameboy.py" "\$@"
EOF
chmod +x "$BIN_DIR/bmo"

# 5. icon + desktop entry (double-click)
mkdir -p "$ICON_DIR" "$APP_DIR"
cp -f "$DEST/assets/bmo-icon.png" "$ICON_DIR/bmo.png"
cat > "$APP_DIR/bmo.desktop" <<EOF
[Desktop Entry]
Name=BMO
Comment=GameBoy-style terminal
GenericName=Terminal
Exec=$BIN_DIR/bmo
Icon=bmo
Type=Application
Categories=Utility;TerminalEmulator;
Terminal=false
StartupNotify=false
EOF

# 6. Blue Water logo font
mkdir -p "$FONT_DIR"
cp -f "$DEST/assets/Blue Water.otf" "$FONT_DIR/Blue Water.otf"
if need fc-cache; then
    fc-cache -f >/dev/null 2>&1 || true
fi

# PATH hint
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "NOTE: add $BIN_DIR to your PATH, e.g.:  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo
echo "==> BMO installed!"
echo "    Run it now:   $BIN_DIR/bmo"
echo "    or double-click the 'BMO' entry in your app menu."
