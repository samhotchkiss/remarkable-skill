---
name: remarkable
version: 2.2.0
description: Manage a reMarkable tablet - send files, fetch and faithfully render handwritten notes, grade/mark up documents, organize the library. Use when the user mentions their reMarkable, sending something to their tablet, reading their handwritten notes/markup, or organizing tablet documents.
---

# reMarkable

A hardened skill for working with a reMarkable tablet via the cloud API.
Forked from caseyg/caseys-claude `remarkable` and rewritten after extensive
real-world use. **Read "Iron rules" before writing any new code.**

If a `SKILL.local.md` exists next to this file, read it too — it holds
machine- and user-specific configuration (token location, library layout,
personal conventions).

## Iron rules (violations have burned us before)

1. **Auth = local token file.** The device token lives at
   `~/.config/remarkable/device_token` (mode 600). Prefer it over any secret
   manager that needs interactive authorization — remote/headless sessions
   can't answer those prompts. `common.ts getDeviceToken()` reads the file
   first and only falls back to 1Password's `op` CLI.
2. **rmapi-js v11 API.** All getters take `(id, hash)`: `getDocument(id, hash)`,
   `getPdf(id, hash)`, etc. `package.json` pins `rmapi-js@^11`. Do not downgrade —
   v9/v10 fail against the current cloud API ("unexpected 'rm-filename' header").
3. **Hashes mutate, ids don't.** Every rename/move/upload changes document hashes.
   Re-resolve hashes via `listItems(true)` immediately before any operation; refer
   to documents by `id` in any plan or script (see `organize.ts`).
4. **Pressure-weighted rendering, always.** Render strokes with per-point
   `width/4 x thickness_scale`, modulated by pressure — via `rmlib.draw_stroke()`.
   Uniform thin polylines distort glyphs (a curly handwritten "2" reads as an "8").
5. **Visible strokes only.** Extract via `rmlib.visible_strokes()` (scene-tree walk);
   raw `read_blocks()` includes erased strokes.
   **Never interpret a parse failure as an empty document.** Pre-2022 notebooks use
   the legacy v3/v5 `.lines` binary format (rmscene v6-only) — rmlib parses those
   transparently. Swallowed parse errors once mislabeled 18 real notebooks as
   empty and staged them for deletion.
6. **v6 coordinates are center-origin in x.** `rmlib` handles the `+RM_WIDTH/2`
   shift. Display is 1404x1872 (3:4); a 468x624pt PDF page fills it exactly —
   generate documents at that size.
7. **Read ink first, compare to expectations after.** When reading handwriting,
   never resolve an ambiguous glyph toward what the answer "should" be. Render
   glyph tiles (`sudoku-poster.py tiles()` pattern), read them cold, then grade.
8. **PyMuPDF gotcha:** `Shape.finish()` defaults to `closePath=True` — a ✓ polyline
   becomes a ▲. Pass `closePath=False` for open marks.
9. **Markup conventions:** the user's ink renders blue, Claude's grading/annotation
   marks red, on paper-white. (Poster style: see `sudoku-poster.py`.)
10. **Respect pen color and tool.** Use `visible_strokes_colored()` /
   `draw_strokes_colored()` — color ids map via `COLOR_MAP` (0 black, 1 gray,
   3 yellow, 4 green, 5 pink, 6 blue, 7 red) and highlighter tools (18; 5/8 on
   older firmware) render as wide flat translucent strokes UNDER the ink layer,
   butt caps, no pressure modulation. A yellow highlight rendered as black ink
   is a rendering defect. Fineliner weight: default `wscale=0.85` (1.5 looks
   like a marker).
11. **Don't assume 1404px geometry for pages.** Paper Pro devices write wider
   coordinates; blank-notebook rendering is extent-aware (grows the page instead
   of clipping strokes).

## Setup

- `npm install` in this directory (rmapi-js v11).
- Python venv: `uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt`
  (`rmscene`, `PyMuPDF`, `svgwrite`).
- Run TS scripts with `npx tsx`, Python with `.venv/bin/python`, from this directory.
- First-time device pairing: browser code from
  https://my.remarkable.com/device/browser/connect → `npx tsx assets/scripts/register.ts <code>`
  → stores the permanent device token.

## Scripts (assets/scripts/)

| Script | Purpose |
|---|---|
| `common.ts` | auth + shared helpers (`initApi`, `findDocuments`, `safeName`) |
| `list.ts` | list documents/folders |
| `inventory.ts` | full library dump as JSON: id, hash, name, type, parent, modified |
| `upload.ts <file>` | upload PDF/EPUB |
| `download.ts "<name>" [--original]` | download by name → zip (+ original PDF) |
| `batch-download.ts <targets.json> <dir>` | bulk download; targets = `[{id,hash,name}]` |
| `backup.ts` | full library backup with manifest |
| `organize.ts <plan.json>` | folders / renames / moves / folder-nesting / delete-empty-folders, all by id |
| `register.ts <code>` | device pairing |
| `rmlib.py` | **the** stroke library: `visible_strokes`, `draw_stroke`, `render_document`, `cluster_strokes`, `page_order` |
| `render-annotations.py <extracted> <out.pdf>` | faithful PDF render of any downloaded doc |
| `peek.py <zips-dir> <out-dir>` | labeled contact sheets for visual triage of many docs |
| `make-sudoku.py` | example: generate a puzzle PDF sized for the tablet |
| `sudoku-poster.py` | example: glyph clustering, cold reading, graded-poster markup |

## Local mirror (preferred read path for agents)

A launchd agent (`install-mirror-daemon.sh`, label `com.remarkable.mirror`) syncs
the cloud library to `$REMARKABLE_MIRROR` (default `~/reMarkable`) every 3 minutes.
**Agents should read the mirror instead of hitting the API:**

- `INDEX.md` — read this first: recently-updated list + full tree.
- `<Folder>/<Doc>/pages/page-NN.png` — current state of every page.
- `<Folder>/<Doc>/delta/delta-NN.png` — pages with ink changed since previous
  sync: old strokes faded gray, NEW strokes in full color. **This is how you see
  what the user just annotated.**
- `<Folder>/<Doc>/render.pdf`, `raw/`, `meta.json` — full render, source archive, sync info.
- `CHANGELOG.jsonl` — append-only event log (added/updated/moved/trashed).

**Trigger an immediate sync** (after uploading, or when the user says "look at my
notes"): `bash assets/scripts/sync-now.sh` — synchronous, safe to run anytime.
Push flow: `upload.ts <file>` then `sync-now.sh` to land it in the mirror.
The mirror is read-only — never write into it except via the sync scripts.

## Core workflows

**Send a file:** `npx tsx assets/scripts/upload.ts /path/doc.pdf` — appears in the
cloud library immediately, syncs to tablet on next connect.

**Fetch + read markup:** download → unzip → `render-annotations.py` → rasterize
pages (`fitz`, dpi 150-200) → view. For glyph-level reading (grading, forms), use the
cluster-tiles pattern from `sudoku-poster.py`.

**Organize the library:** `inventory.ts` → build plan JSON → `organize.ts`. Peek
inside ambiguous docs (`batch-download.ts` + `peek.py`) before renaming; never
delete outright — move candidates to a "Review for Deletion" folder and let the
user decide. `api.delete()` is soft (device trash).

**Grade / annotate round-trip:** generate 468x624pt PDF → upload → user marks it up →
download → render → read → produce marked-up version (blue ink / red marks) → upload
replacement, trash the stale copy.

## Known limitations

- Handwriting-to-text is visual (Claude reads rendered tiles); no OCR pipeline.
- Long documents: `render_document(max_pages=...)` to bound work.
- rmscene (0.8.0, latest) warns "Some data has not been read" on current-firmware
  files — upstream hasn't caught up with newer block types. Harmless; stroke
  extraction is unaffected. Re-check upstream if extraction ever misses ink.
