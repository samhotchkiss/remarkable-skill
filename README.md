# remarkable — a Claude Code skill for the reMarkable tablet

A hardened [Claude Code skill](https://docs.claude.com/en/docs/claude-code) for
working with a reMarkable tablet via the cloud API: send documents, fetch and
faithfully render handwritten notes, grade/mark up documents, and organize the
library.

Forked from [caseyg/caseys-claude](https://github.com/caseyg/caseys-claude)'s
`remarkable` skill, then substantially rewritten after real-world use. Key
differences from the original:

- **rmapi-js v11** (two-argument getters; v9 no longer works against the cloud API)
- **Local token-file auth** (`~/.config/remarkable/device_token`) instead of a
  1Password round-trip — works in headless/remote sessions
- **Faithful handwriting rendering**: visible-strokes-only extraction (erased ink
  excluded) and pressure-weighted stroke drawing via `assets/scripts/rmlib.py` —
  uniform thin polylines demonstrably distort glyphs
- **Library management tooling**: full-inventory dump, batch download, contact-sheet
  previews, and a declarative organize script (folders / renames / moves by
  immutable document id)
- Example round-trip workflow: generate a Sudoku, have a human solve it on the
  tablet, read the handwritten digits back, and return a graded, marked-up PDF

## Local mirror daemon

`assets/scripts/install-mirror-daemon.sh` installs a launchd agent that keeps a
local mirror of your whole tablet library (default `~/reMarkable`, every 3 min):

- `INDEX.md` — recently-updated feed + full library tree
- `<Folder>/<Doc>/pages/page-NN.png` — rendered current state of every page
- `<Folder>/<Doc>/delta/delta-NN.png` — **what changed since the last sync**:
  new ink in full color, older ink faded gray. An agent (or you) sees fresh
  annotations at a glance without touching the API.
- `render.pdf`, `raw/` (.rm source archive), `meta.json`, `CHANGELOG.jsonl`

`assets/scripts/sync-now.sh` triggers an immediate synchronous sync — run it
after uploading a file or before reading the user's latest markup. The mirror
is read-only; pushing to the tablet stays explicit via `upload.ts`.

Handles v6 scene-tree files and legacy v3/v5 `.lines` notebooks (a parse
failure is never treated as an empty document).

See `SKILL.md` for the operating rules ("Iron rules") and script catalog.

## Install (Claude Code / Claude Cowork)

Skills live in `~/.claude/skills/` (available in every session) or a project's
`.claude/skills/` (that project only). Claude Cowork and the Claude Code desktop
app pick up the same user-level skills directory.

```bash
# 1. Clone as a user-level skill
git clone https://github.com/samhotchkiss/remarkable-skill ~/.claude/skills/remarkable
cd ~/.claude/skills/remarkable

# 2. Install dependencies (Node 18+ and uv required)
npm install
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

# 3. Pair with your reMarkable account (one time)
#    Get an 8-character browser code at my.remarkable.com/device/browser/connect
npx tsx assets/scripts/register.ts <8-char-code>

# 4. Optional but recommended: continuous local mirror (macOS launchd)
bash assets/scripts/install-mirror-daemon.sh
```

Then just talk to Claude about your tablet: "send this PDF to my reMarkable",
"what did I write in my meeting notebook?", "check my markup on the spec".
Claude Code discovers the skill automatically — no configuration beyond the above.

The device token is stored at `~/.config/remarkable/device_token` (mode 600).
TypeScript scripts run with `npx tsx`, Python scripts with `.venv/bin/python`,
both from the skill directory. The mirror daemon is macOS-only (launchd); all
other scripts also work on Linux.
