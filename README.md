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

- `install.sh` - the curl installer (`BMO_REPO`/`BMO_BRANCH` env vars override the source)
- `package.json` + `cli.js` - the npm/bun package (`@lmdelm-dev/bmo`)
- `Formula/bmo.rb` - Homebrew formula (copy into the `lmdelm-dev/homebrew-tap` repo)
- `pkg/aur/` - AUR `PKGBUILD` + `.SRCINFO` (submit to aur.archlinux.org)
- `scripts/release.sh` - fills the real tarball sha256 into the Formula + AUR files
- `.github/workflows/ci.yml` - lint checks on push, checksum verification on tags

### Release checklist (publish a new version)

```sh
# 1. commit your changes, then create the tag
git add -A
git commit -m "My change"
git tag v0.1.0          # bump versions in package.json, Formula, PKGBUILD too

# 2. push the repo and the tag
git remote add origin https://github.com/lmdelm-dev/bmo.git
git push -u origin main
git push origin v0.1.0

# 3. now that the tarball exists on GitHub, get the real checksums:
./scripts/release.sh v0.1.0   # prints the sha256 and updates Formula + AUR files
```

> Note: a tag commit cannot contain its own tarball checksum (it would change the
> tarball). The computed sha256 must live in the **AUR repo** and the **Homebrew
> tap repo** (separate git repos), which `scripts/release.sh` produces for you.

After that:
- **npm / bun**: `npm publish` (must be run from a machine logged into npm; requires an npm account with `@lmdelm-dev` scope access).
- **Homebrew**: create `github.com/lmdelm-dev/homebrew-tap`, put the updated `Formula/bmo.rb` in it, push.
- **AUR / paru**: push the updated `pkg/aur/` (as `bmo/` repo) to aur.archlinux.org; `paru -S bmo` then works.

CI lints on push, and on each tag it re-packages the GitHub tarball to confirm it
builds.

## License

MIT
