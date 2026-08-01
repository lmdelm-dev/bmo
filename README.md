# BMO

A GameBoy-style terminal. Cute BMO face, round buttons, Blue Water logo font,
a real shell, embedded terminals, and an idle screen-saver where BMO blinks and
looks around.

- **Linux** and **Windows**
- Double-click to launch (desktop entry on Linux, `.pyw` on Windows)
- Install via **curl | npm | bun | brew | paru**

## Requirements

- Python 3 with `tkinter`
- Pillow (optional - needed for BMO's face saver)
- `python-xlib` (Linux, optional - needed for the minimize/restore hotkey)

## Install

### curl (Linux / macOS)

```sh
curl -fsSL https://raw.githubusercontent.com/lmdelm-dev/bmo/main/install.sh | bash
```

Installs to `~/.local/share/bmo`, adds a `bmo` command, a desktop entry, and the
Blue Water logo font. Run it with `bmo` or from your app menu.

### npm

```sh
npm install -g @lmdelm-dev/bmo
bmo
```

### bun

```sh
bun add -g @lmdelm-dev/bmo
bmo
```

### brew (macOS / Linux)

```sh
brew tap lmdelm-dev/tap https://github.com/lmdelm-dev/homebrew-tap
brew install bmo
```

### paru / AUR (Arch)

```sh
paru -S bmo
```

### From source

```sh
git clone https://github.com/lmdelm-dev/bmo.git
cd bmo
./bmo
```

### Windows

Install [Python](https://python.org) (tick "Add python.exe to PATH", plus
`tkinter`), then:

- Double-click `bmo.pyw`, **or**
- Open a terminal and run `bmo.bat`, **or**
- `npm install -g @lmdelm-dev/bmo && bmo`

## Usage

- Type any command: `ls`, `pwd`, `echo hi`, ...
- `mo` runs opencode, `gmo` opens w3m
- Interactive apps (`python`, `vim`, `bash`, ...) open in an embedded terminal
- `fs` or the yellow **FS** button toggles fullscreen
- The blue **_** button minimizes; on Linux bring it back with **Ctrl+Alt+B**
- The red **X** button closes BMO
- `bmo` / `bmo --help`... type `help` inside BMO for more
- After 60s idle, BMO falls asleep (blinks; move mouse or press a key to wake)

## Packaging notes for maintainers

- `install.sh` - the curl installer
- `package.json` + `cli.js` - the npm/bun package (`@lmdelm-dev/bmo`)
- `Formula/bmo.rb` - Homebrew formula (copy into the `lmdelm-dev/homebrew-tap` repo)
- `pkg/aur/` - AUR `PKGBUILD` + `.SRCINFO` (submit to aur.archlinux.org)

Before tagging `v0.1.0`, replace the two `REPLACE_WITH_REAL_SHA256...` placeholders
(in `Formula/bmo.rb` and `pkg/aur/PKGBUILD` + `.SRCINFO`) with the real tarball
checksum:

```sh
sha256sum <(curl -fsSL https://github.com/lmdelm-dev/bmo/archive/refs/tags/v0.1.0.tar.gz)
```

## License

MIT
