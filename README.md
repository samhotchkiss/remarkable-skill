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

See `SKILL.md` for the operating rules ("Iron rules") and script catalog.

## Setup

```bash
npm install
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt

# one-time device pairing (browser code from my.remarkable.com/device/browser/connect)
npx tsx assets/scripts/register.ts <8-char-code>
```

TypeScript scripts run with `npx tsx`, Python scripts with `.venv/bin/python`,
both from the repo root.
