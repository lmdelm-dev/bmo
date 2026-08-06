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
- 💬 **Talks first** sometimes, asking about things you've mentioned ("so you like
  hiking? tell me more!")
- ฅ(=`ω`=)ฅ **Cat loading animation** while it thinks
- 🗣️ **Has a human voice** - BMO *speaks* out loud with a real neural voice
  (Piper, offline; auto-downloads ~60MB once) pitched up into a **little-kid
  voice** (sox `pitch`). It also speaks **English, Arabic,
  French and Spanish**, auto-picking the language of what it's saying! You can
  talk back by **holding the pink MIC button** (vosk, offline speech-to-text) ♥
- 😴 **Falls asleep** after 2 minutes of quiet (cute sleep face!) - wake it with a
  mouse move or any key
- 🐚 **A real terminal** - run commands, `/mo` opens opencode, `/gmo` opens w3m
- 🎨 **opencode gets BMO's look** - installing BMO themes opencode (BMO colors +
  a BMO header logo), so `/mo` feels right at home
- 🔄 **Self-updates** from GitHub (silently checks, asks before updating)

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
- **Commands** start with `/`:

| command | does |
| --- | --- |
| `/help` | show all commands |
| `/name <n>` | tell BMO your name |
| `/memory` | what BMO remembers |
| `/forget` | forget everything |
| `/model [name]` | change the AI model |
| `/voice on\|off` | BMO talks out loud (test it with `/voice test`) |
| `/voice kid` | toggle BMO's little-kid voice (add `<cents>` to tune, e.g. `400`) |
| `/ls`, `/pwd`, ... | run any shell command |
| `/mo`, `/gmo` | open opencode / w3m |
| `/fs`, `/clear`, `/quit` | fullscreen / clear / quit |

- **Talk to BMO:** hold the pink **MIC** button in the top-right corner, say
  something, release it - BMO types what you said and replies (out loud!). The
  first time you do this it downloads a small offline speech model (~50MB)
- The blue **_** button minimizes (bring it back with **Ctrl+Alt+B**), the red **X** closes BMO
- Idle for **2 minutes** and BMO falls asleep - just move the mouse or press a key to wake it up

> **First chat?** Make sure `opencode` is installed and you've signed in to a
> provider (`opencode providers`). BMO connects to its opencode "brain" on
> chatter away - no local model to download. Type `/model <provider/model>`
> anytime to switch brains.

## For maintainers

- `install.sh` - the curl installer
- `package.json` + `cli.js` - the npm/bun package
- `Formula/bmo.rb` - Homebrew formula
- `scripts/release.sh` + `.circleci/config.yml` - release checksums + CI (free open-source CircleCI, replaces GitHub Actions)

## License

MIT
