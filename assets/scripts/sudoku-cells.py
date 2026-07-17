#!/usr/bin/env python3
"""Render the filled Sudoku, then emit labeled crops of every originally-empty cell."""

import json
import sys
from pathlib import Path

import fitz
from rmscene import read_blocks
from rmscene.scene_items import Line

RM_WIDTH, RM_HEIGHT = 1404, 1872
X0, Y0, CELL, GRID = 36.0, 90.0, 44.0, 396.0

def strokes(rm_path):
    out = []
    with open(rm_path, "rb") as f:
        for block in read_blocks(f):
            line = None
            if hasattr(block, "item") and isinstance(getattr(block.item, "value", None), Line):
                line = block.item.value
            elif hasattr(block, "value") and isinstance(block.value, Line):
                line = block.value
            if line is not None and line.points:
                out.append([(p.x, p.y) for p in line.points])
    return out

def main():
    workdir = Path(sys.argv[1])
    answer = json.loads(Path(sys.argv[2]).read_text())
    puzzle = answer["puzzle"]

    pdf = next(workdir.glob("extracted/*.pdf"))
    rm = next(workdir.glob("extracted/**/*.rm"))

    doc = fitz.open(pdf)
    page = doc[0]
    sx, sy = page.rect.width / RM_WIDTH, page.rect.height / RM_HEIGHT
    all_strokes = strokes(rm)
    for s in all_strokes:
        pts = [fitz.Point((x + RM_WIDTH / 2) * sx, y * sy) for x, y in s]
        if len(pts) >= 2:
            sh = page.new_shape()
            sh.draw_polyline(pts)
            sh.finish(color=(0, 0, 0), width=1.1)
            sh.commit()
    overlay = workdir / "filled.pdf"
    doc.save(overlay)

    # full-page preview
    pix = page.get_pixmap(dpi=200)
    pix.save(workdir / "filled-full.png")

    # per-cell crops (dpi 300) of originally-empty cells
    DPI = 300
    zoom = DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    empties = [(i // 9, i % 9) for i in range(81) if puzzle[i] == 0]
    print(f"empty cells: {len(empties)}")

    TILE = 120  # px per crop tile in sheet
    cols = 7
    rows = (len(empties) + cols - 1) // cols
    sheet = fitz.open()
    sp = sheet.new_page(width=cols * TILE, height=rows * (TILE + 18))
    for j, (r, c) in enumerate(empties):
        x0px = (X0 + c * CELL + 3) * zoom
        y0px = (Y0 + r * CELL + 3) * zoom
        x1px = (X0 + (c + 1) * CELL - 3) * zoom
        y1px = (Y0 + (r + 1) * CELL - 3) * zoom
        clip = fitz.Rect(x0px / zoom, y0px / zoom, x1px / zoom, y1px / zoom)
        cellpix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        col, row = j % cols, j // cols
        x, y = col * TILE, row * (TILE + 18)
        sp.insert_text((x + 4, y + 12), f"R{r+1}C{c+1}", fontsize=10, color=(0.85, 0, 0))
        rect = fitz.Rect(x + 4, y + 16, x + TILE - 4, y + 16 + TILE - 4)
        sp.insert_image(rect, pixmap=cellpix, keep_proportion=True)
        sp.draw_rect(fitz.Rect(x, y, x + TILE, y + TILE + 16), width=0.4)
    sp.get_pixmap(dpi=100).save(workdir / "cells.png")
    print(workdir / "cells.png")

if __name__ == "__main__":
    main()
