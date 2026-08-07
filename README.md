# BMO ♥

A cute GameBoy friend that lives on your desktop.

Say hi and BMO **talks back** - it's a real AI friend that remembers you, chats
with you, runs commands, and even speaks up on its own once in a while.

```
  /\_/\
  ( o.o )
   > ^ <
```

> *"Hello! I'm BMO, your GameBoy friend!"*

## Why BMO is great

- 🧠 **A real AI friend** - BMO talks through **opencode**, so it can answer
  anything and even use tools. Free, no API keys (just sign in to a free provider
  once: `opencode providers`)
- 💭 **Remembers you** - your name and what you tell it (`~/.local/share/bmo/chat.json`)
- 💬 **Talks up spontaneously** sometimes, asking about things you've mentioned
- 🧼 **Just the essentials** - a clean GameBoy chat window + the brain, no bloat

## Install

**curl (Linux / macOS):**
```sh
curl -fsSL https://raw.githubusercontent.com/lmdelm-dev/bmo/main/install.sh | bash
```

**npm / bun:**
```sh
npm install -g @lmdelm-dev/bmo && bmo
# or
bun add -g @lmdelm-dev/bmo && bmo
```

**Homebrew:**
```sh
brew tap lmdelm-dev/tap https://github.com/lmdelm-dev/homebrew-tap
brew install bmo
```

**Windows:** install [Python](https://python.org) (with `tkinter`), then
double-click `bmo.pyw` or run `bmo.bat`.

**From source:**
```sh
git clone https://github.com/lmdelm-dev/bmo.git
cd bmo
./bmo
```

## Using BMO

- **Just type** anything and BMO chats with you ♥
- BMO remembers your name and what you tell it
- The blue **`_`** button minimizes, the red **X** closes, **F11** toggles fullscreen

> **First chat?** Make sure `opencode` is installed and you've signed in to a
> provider (`opencode providers`). BMO connects to its opencode "brain" on
> chatter away - no local model to download.

## For maintainers

- `install.sh` - the curl installer
- `package.json` + `cli.js` - the npm/bun package
- `Formula/bmo.rb` - Homebrew formula
- `scripts/release.sh` + `.circleci/config.yml` - release checksums + CI (free open-source CircleCI, replaces GitHub Actions)

## License

MIT
