#!/usr/bin/env bash
# BMO - GameBoy terminal
# One-line install (bootstraps all missing dependencies for you):
#   curl -fsSL https://raw.githubusercontent.com/lmdelm-dev/bmo/main/install.sh | bash
#
# The installer checks for, and installs when missing:
#   - Python 3 + tkinter   (system package)
#   - opencode              (curl -fsSL https://opencode.ai/install | bash)
#   - the Blue Water font   (shipped, fc-cache)
# then drops a double-clickable BMO icon on your desktop.
set -uo pipefail

REPO="${BMO_REPO:-https://github.com/lmdelm-dev/bmo}"
BRANCH="${BMO_BRANCH:-main}"

DEST="${BMO_HOME:-$HOME/.local/share/bmo}"
BIN_DIR="${BMO_BIN:-$HOME/.local/bin}"
ICON_DIR="$HOME/.local/share/icons"
APP_DIR="$HOME/.local/share/applications"
FONT_DIR="$HOME/.local/share/fonts"

ASSUME_YES="${BMO_ASSUME_YES:-0}"
[ "${1:-}" = "-y" ] && ASSUME_YES=1

need()  { command -v "$1" >/dev/null 2>&1; }
have() { "$@" >/dev/null 2>&1; }

# ask "prompt" -> 0=yes, 1=no. Auto-yes if non-interactive or ASSUME_YES.
ask() {
    if [ "$ASSUME_YES" = "1" ] || ! [ -t 0 ]; then return 0; fi
    local ans
    printf "%s [Y/n] " "$1" >&2
    read -r ans </dev/tty 2>/dev/null || ans=y
    case "${ans:-y}" in [Nn]*) return 1 ;; esac
    return 0
}

echo "==> BMO installer"
echo "    repo: $REPO"
echo "    install dir: $DEST"
echo

# ----------------------------------------------------------------------------
# Dependency bootstrap
# ----------------------------------------------------------------------------
echo "==> checking dependencies..."

# --- curl/wget (needed to download anything) ---
if ! need curl && ! need wget; then
    echo "ERROR: need 'curl' or 'wget'. Install one, then re-run." >&2
    exit 1
fi

# --- Python 3 + tkinter ---
if ! need python3; then
    echo "    Python 3 is missing - installing..."
    if need apt-get; then
        sudo apt-get update && sudo apt-get install -y python3 python3-tk python3-pip
    elif need zypper; then
        sudo zypper install -y python3 python3-tk python3-pip
    elif need dnf; then
        sudo dnf install -y python3 python3-tkinter python3-pip
    elif need pacman; then
        sudo pacman -S --noconfirm python tk python-pip
    elif need brew; then
        brew install python-tk
    else
        echo "ERROR: no supported package manager found for Python 3." >&2
        echo "       Install Python 3 + tkinter manually, then re-run." >&2
        exit 1
    fi
elif ! python3 -c "import tkinter" 2>/dev/null; then
    echo "    Python tkinter is missing - installing..."
    if need apt-get; then
        sudo apt-get install -y python3-tk
    elif need zypper; then
        sudo zypper install -y python3-tk
    elif need dnf; then
        sudo dnf install -y python3-tkinter
    elif need pacman; then
        sudo pacman -S --noconfirm tk
    elif need brew; then
        brew install python-tk
    else
        echo "ERROR: could not install tkinter automatically." >&2
        echo "       Install python3-tk (or your distro's equivalent), then re-run." >&2
        exit 1
    fi
fi
! need python3 && { echo "ERROR: Python 3 still not found - cannot continue." >&2; exit 1; }
python3 -c "import tkinter" 2>/dev/null || { echo "ERROR: tkinter still not importable." >&2; exit 1; }

# --- opencode (BMO's brain - powers chat) ---
if ! need opencode; then
    echo "    opencode is missing (BMO's AI brain - it powers chat and 'mo')."
    echo "    Free to install; BMO will guide you to sign in to a provider on first chat."
    if ask "    Install opencode via curl -fsSL https://opencode.ai/install | bash?"; then
        bash -c "curl -fsSL https://opencode.ai/install | bash" || \
            echo "    (opencode install failed - install it later so BMO can think)"
        # opencode installs to ~/.opencode/bin; make sure it's reachable this session
        [ -d "$HOME/.opencode/bin" ] && case ":$PATH:" in
            *":$HOME/.opencode/bin:"*) ;;
            *) export PATH="$HOME/.opencode/bin:$PATH" ;;
        esac
    fi
    need opencode || echo "    continuing without opencode (BMO will show the install command on first chat)"
fi

# ----------------------------------------------------------------------------
# Download + install BMO itself
# ----------------------------------------------------------------------------
echo "==> installing BMO..."
mkdir -p "$DEST" "$BIN_DIR" "$ICON_DIR" "$APP_DIR" "$FONT_DIR"

if [ -d "$DEST/.git" ] || [ -f "$DEST/gameboy.py" ] || [ -f "$DEST/bmo.py" ]; then
    echo "    refreshing existing install at $DEST"
    rm -rf "${DEST:?}/"*
fi
if need curl; then
    curl -fsSL "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar xz --strip-components=1 -C "$DEST"
else
    wget -qO- "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar xz --strip-components=1 -C "$DEST"
fi

# launcher
cat > "$BIN_DIR/bmo" <<EOF
#!/usr/bin/env bash
# BMO launcher
export BMO_HOME="$DEST"
# prefer a bundled opencode, else one the user installed, else PATH
if [ -x "\$HOME/.opencode/bin/opencode" ]; then
    export PATH="\$HOME/.opencode/bin:\$PATH"
fi
exec python3 "$DEST/bmo.py" "\$@"
EOF
chmod +x "$BIN_DIR/bmo"

# icon + desktop entry (app menu)
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

# double-clickable BMO icon on the Desktop
DESKTOP_DIR="${XDG_DESKTOP_DIR:-}"
[ -z "$DESKTOP_DIR" ] && need xdg-user-dir && DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
DESKTOP_DIR="${DESKTOP_DIR:-$HOME/Desktop}"
if [ -d "$DESKTOP_DIR" ]; then
    cp -f "$APP_DIR/bmo.desktop" "$DESKTOP_DIR/bmo.desktop"
    chmod +x "$DESKTOP_DIR/bmo.desktop"
    need gio && gio set "$DESKTOP_DIR/bmo.desktop" metadata::trusted true >/dev/null 2>&1 || true
    echo "    desktop launcher: $DESKTOP_DIR/bmo.desktop"
fi

# Blue Water logo font - applied instantly (fc-cache picks it up before launch)
cp -f "$DEST/assets/Blue Water.otf" "$FONT_DIR/Blue Water.otf"
if need fc-cache; then
    fc-cache -f "$FONT_DIR" >/dev/null 2>&1 || true
fi

# BMO opencode theme + header logo (applies the next time opencode starts)
if [ -f "$DEST/opencode/install.py" ]; then
    python3 "$DEST/opencode/install.py" || echo "    (opencode theme install skipped)"
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
[ -t 0 ] || echo "    (re-open your terminal first so the new PATH/font take effect)"
