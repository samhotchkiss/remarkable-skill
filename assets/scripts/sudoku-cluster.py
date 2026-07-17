#!/usr/bin/env python3
"""Cluster Sudoku pen strokes into digits, assign to cells by ordering, emit labeled tiles."""

import json
import sys
from pathlib import Path

import fitz
from rmscene import read_blocks
from rmscene.scene_items import Line

RM_WIDTH = 1404

def strokes_from(rm_path):
    out = []
    with open(rm_path, "rb") as f:
        for block in read_blocks(f):
            line = None
            if hasattr(block, "item") and isinstance(getattr(block.item, "value", None), Line):
                line = block.item.value
            elif hasattr(block, "value") and isinstance(block.value, Line):
                line = block.value
            if line is not None and line.points:
                out.append([(p.x + RM_WIDTH / 2, p.y) for p in line.points])
    return out

def bbox(stroke):
    xs = [p[0] for p in stroke]; ys = [p[1] for p in stroke]
    return min(xs), min(ys), max(xs), max(ys)

def bbox_dist(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return max(dx, dy)

def main():
    workdir = Path(sys.argv[1])
    answer = json.loads(Path(sys.argv[2]).read_text())
    puzzle = answer["puzzle"]

    rm = next(workdir.glob("extracted/**/*.rm"))
    st = strokes_from(rm)

    # agglomerative clustering by bbox gap
    THRESH = 10  # rm units
    clusters = [[s] for s in st]
    merged = True
    while merged:
        merged = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                bi = [min(v) if k < 2 else max(v) for k, v in enumerate(zip(*[bbox(s) for s in clusters[i]]))]
                bj = [min(v) if k < 2 else max(v) for k, v in enumerate(zip(*[bbox(s) for s in clusters[j]]))]
                if bbox_dist(bi, bj) < THRESH:
                    clusters[i] += clusters[j]
                    del clusters[j]
                    merged = True
                    break
            if merged:
                break

    # centroid per cluster
    def centroid(cl):
        pts = [p for s in cl for p in s]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    cl = [(centroid(c), c) for c in clusters]
    empties_by_row = {r: sorted(c for c in range(9) if puzzle[r * 9 + c] == 0) for r in range(9)}
    total = sum(len(v) for v in empties_by_row.values())
    print(f"clusters: {len(cl)}, expected digits: {total}")
    if len(cl) != total:
        print("MISMATCH — adjust THRESH")
        # continue anyway for diagnostics

    # assign: sort by y, slice per row counts, then sort each row slice by x
    cl.sort(key=lambda t: t[0][1])
    assignments = {}
    idx = 0
    for r in range(9):
        n = len(empties_by_row[r])
        row_cl = sorted(cl[idx : idx + n], key=lambda t: t[0][0])
        idx += n
        for (cent, strokes_), col in zip(row_cl, empties_by_row[r]):
            assignments[(r, col)] = strokes_

    # render tiles
    TILE = 110
    cols = 7
    rows = (total + cols - 1) // cols
    sheet = fitz.open()
    sp = sheet.new_page(width=cols * TILE, height=rows * (TILE + 16))
    keys = sorted(assignments.keys())
    for j, key in enumerate(keys):
        strokes_ = assignments[key]
        pts = [p for s in strokes_ for p in s]
        x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
        x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)
        w, h = max(x1 - x0, 1), max(y1 - y0, 1)
        scale = min((TILE - 30) / w, (TILE - 30) / h)
        col, row = j % cols, j // cols
        ox = col * TILE + (TILE - w * scale) / 2
        oy = row * (TILE + 16) + 14 + (TILE - h * scale) / 2
        sp.insert_text((col * TILE + 4, row * (TILE + 16) + 11), f"R{key[0]+1}C{key[1]+1}", fontsize=9, color=(0.85, 0, 0))
        for s in strokes_:
            fpts = [fitz.Point(ox + (p[0] - x0) * scale, oy + (p[1] - y0) * scale) for p in s]
            if len(fpts) >= 2:
                sh = sp.new_shape()
                sh.draw_polyline(fpts)
                sh.finish(color=(0, 0, 0), width=1.5)
                sh.commit()
        sp.draw_rect(fitz.Rect(col * TILE, row * (TILE + 16), col * TILE + TILE, row * (TILE + 16) + TILE + 12), width=0.4)
    sp.get_pixmap(dpi=110).save(workdir / "digits.png")
    json.dump({f"{k[0]},{k[1]}": None for k in keys}, open(workdir / "cells-order.json", "w"))
    print(workdir / "digits.png")

if __name__ == "__main__":
    main()
