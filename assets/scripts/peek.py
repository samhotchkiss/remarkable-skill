#!/usr/bin/env python3
"""Render first pages of downloaded reMarkable docs (zips) into labeled contact
sheets for quick visual triage. Pressure-weighted handwriting rendering.

Usage: peek.py <dir-of-zips> <out-dir> [pages-per-doc]
Zip filenames: <label>__<id>.zip (batch-download.ts format) or any name.
"""

import sys
import zipfile
import tempfile
from pathlib import Path

import fitz
from rmlib import render_document

TILE_W, TILE_H = 420, 560
COLS, ROWS = 3, 2


def main():
    src_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    out_dir.mkdir(parents=True, exist_ok=True)

    tiles = []
    for zp in sorted(src_dir.glob("*.zip")):
        label = zp.stem.split("__")[0].replace("_", " ")
        try:
            with tempfile.TemporaryDirectory() as td:
                zipfile.ZipFile(zp).extractall(td)
                tmp_pdf = Path(td) / "_render.pdf"
                n = render_document(td, tmp_pdf, max_pages=max_pages)
                if n == 0:
                    tiles.append((f"{label} [EMPTY]", None))
                    continue
                doc = fitz.open(tmp_pdf)
                for i in range(len(doc)):
                    tiles.append((f"{label} p{i+1}", doc[i].get_pixmap(dpi=72)))
                doc.close()
        except Exception as e:
            tiles.append((f"{label} [ERR {e}]", None))

    per_sheet = COLS * ROWS
    for s in range(0, len(tiles), per_sheet):
        sheet = fitz.open()
        page = sheet.new_page(width=COLS * TILE_W, height=ROWS * (TILE_H + 24))
        for j, (label, pix) in enumerate(tiles[s : s + per_sheet]):
            col, row = j % COLS, j // COLS
            x, y = col * TILE_W, row * (TILE_H + 24)
            page.insert_text((x + 6, y + 14), label[:60], fontsize=11, color=(0.8, 0, 0))
            if pix is not None:
                page.insert_image(fitz.Rect(x + 4, y + 20, x + TILE_W - 4, y + 20 + TILE_H - 4), pixmap=pix, keep_proportion=True)
            page.draw_rect(fitz.Rect(x, y, x + TILE_W, y + TILE_H + 20), width=0.5)
        out = out_dir / f"sheet-{s // per_sheet + 1:02d}.png"
        page.get_pixmap(dpi=110).save(out)
        sheet.close()
        print(out)


if __name__ == "__main__":
    main()
