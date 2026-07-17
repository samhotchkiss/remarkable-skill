#!/usr/bin/env python3
"""Faithful pressure-weighted re-render of the Sudoku + a poster-grade marked-up version.

Outputs: digits-v2.png (verification tiles), poster.pdf, poster.png
"""

import json
import sys
from pathlib import Path

import fitz
from rmscene import read_tree
from rmscene.scene_items import Line, Group

RM_WIDTH = 1404
# original generated page geometry (468x624)
OX0, OY0, OCELL = 36.0, 90.0, 44.0

INK = (0.13, 0.22, 0.58)          # solver strokes: ballpoint blue
BG = (1.0, 1.0, 0.995)            # paper white
GRID_MINOR = (0.78, 0.80, 0.84)
GRID_MAJOR = (0.15, 0.17, 0.22)
GIVEN = (0.25, 0.27, 0.32)
GOOD = (0.82, 0.10, 0.10)         # Claude's markup: teacher red
BAD = (0.82, 0.10, 0.10)
ACCENT = (0.82, 0.10, 0.10)
TITLE = (0.10, 0.11, 0.14)
MUTED = (0.45, 0.47, 0.52)


def visible_strokes(rm_path):
    """[( [(x,y,width_pt,pressure)], )] in original-page coords."""
    with open(rm_path, "rb") as f:
        tree = read_tree(f)
    out = []

    def walk(group):
        for child in group.children.values():
            if isinstance(child, Group):
                walk(child)
            elif isinstance(child, Line):
                pts = []
                for p in child.points:
                    x = (p.x + RM_WIDTH / 2) / 3.0
                    y = p.y / 3.0
                    w = (p.width / 4.0) / 3.0 * child.thickness_scale
                    pts.append((x, y, w, p.pressure / 255.0))
                if pts:
                    out.append(pts)

    walk(tree.root)
    return out


def draw_stroke(page, pts, color, scale=1.0, offset=(0, 0), wscale=1.0, opacity=1.0):
    """Variable-width polyline: per-segment width from pen data."""
    for a, b in zip(pts, pts[1:]):
        w = max(0.35, (a[2] + b[2]) / 2 * wscale * (0.7 + 0.6 * (a[3] + b[3]) / 2))
        sh = page.new_shape()
        sh.draw_line(
            fitz.Point(offset[0] + a[0] * scale, offset[1] + a[1] * scale),
            fitz.Point(offset[0] + b[0] * scale, offset[1] + b[1] * scale),
        )
        sh.finish(color=color, width=w * scale, stroke_opacity=opacity, lineCap=1, lineJoin=1)
        sh.commit()


def cluster(strokes, puzzle):
    def bbox(s):
        xs = [p[0] for p in s]; ys = [p[1] for p in s]
        return min(xs), min(ys), max(xs), max(ys)

    def gap(a, b):
        dx = max(a[0] - b[2], b[0] - a[2], 0)
        dy = max(a[1] - b[3], b[1] - a[3], 0)
        return max(dx, dy)

    TH = 10 / 3.0  # page units
    cl = [[s] for s in strokes]
    merged = True
    while merged:
        merged = False
        for i in range(len(cl)):
            for j in range(i + 1, len(cl)):
                bi = bbox([p for s in cl[i] for p in s])
                bj = bbox([p for s in cl[j] for p in s])
                if gap(bi, bj) < TH:
                    cl[i] += cl[j]
                    del cl[j]
                    merged = True
                    break
            if merged:
                break

    def cent(c):
        pts = [p for s in c for p in s]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    ordered = sorted(((cent(c), c) for c in cl), key=lambda t: t[0][1])
    empties = {r: sorted(c for c in range(9) if puzzle[r * 9 + c] == 0) for r in range(9)}
    out = {}
    idx = 0
    for r in range(9):
        n = len(empties[r])
        row = sorted(ordered[idx : idx + n], key=lambda t: t[0][0])
        idx += n
        for (c_, strokes_), col in zip(row, empties[r]):
            out[(r, col)] = strokes_
    return out


def tiles(assign, out_png):
    TILE, cols = 110, 7
    n = len(assign)
    rows = (n + cols - 1) // cols
    doc = fitz.open()
    page = doc.new_page(width=cols * TILE, height=rows * (TILE + 16))
    for j, key in enumerate(sorted(assign.keys())):
        strokes_ = assign[key]
        pts = [p for s in strokes_ for p in s]
        x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
        x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)
        w, h = max(x1 - x0, 1), max(y1 - y0, 1)
        sc = min((TILE - 30) / w, (TILE - 30) / h)
        col, row = j % cols, j // cols
        ox = col * TILE + (TILE - w * sc) / 2 - x0 * sc
        oy = row * (TILE + 16) + 14 + (TILE - h * sc) / 2 - y0 * sc
        page.insert_text((col * TILE + 4, row * (TILE + 16) + 11), f"R{key[0]+1}C{key[1]+1}", fontsize=9, color=(0.85, 0, 0))
        for s in strokes_:
            draw_stroke(page, s, (0, 0, 0), scale=sc, offset=(ox, oy), wscale=1.6)
        page.draw_rect(fitz.Rect(col * TILE, row * (TILE + 16), (col + 1) * TILE, row * (TILE + 16) + TILE + 12), width=0.4)
    page.get_pixmap(dpi=110).save(out_png)


def poster(assign, answer, reads, out_pdf, out_png):
    puzzle, solution = answer["puzzle"], answer["solution"]
    W, H = 936, 1190
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    page.draw_rect(fitz.Rect(0, 0, W, H), color=None, fill=BG)

    # header
    page.insert_text((64, 108), "SUDOKU", fontsize=64, fontname="hebo", color=TITLE)
    page.insert_text((66, 140), "solved by hand on a reMarkable  ·  graded by Claude from raw pen strokes", fontsize=15, fontname="helv", color=MUTED)

    # score badge
    bc = fitz.Point(W - 128, 108)
    for r_, op in ((52, 0.25), (48, 1.0)):
        sh = page.new_shape()
        sh.draw_circle(bc, r_)
        sh.finish(color=ACCENT, width=3 if r_ == 48 else 7, stroke_opacity=op)
        sh.commit()
    page.insert_text((bc.x - 37, bc.y + 2), "40/41", fontsize=25, fontname="hebo", color=ACCENT)
    page.insert_text((bc.x - 34, bc.y + 24), "one slip", fontsize=11, fontname="helv", color=MUTED)

    # grid geometry
    GW = 720.0
    GX, GY = (W - GW) / 2, 200.0
    CELL = GW / 9

    def cellrect(r, c):
        return fitz.Rect(GX + c * CELL, GY + r * CELL, GX + (c + 1) * CELL, GY + (r + 1) * CELL)

    # error cell soft glow (under everything else)
    for key, read in reads.items():
        r, c = map(int, key.split(","))
        if read != solution[r * 9 + c]:
            cr = cellrect(r, c)
            for pad, op in ((14, 0.06), (9, 0.10), (4, 0.16)):
                sh = page.new_shape()
                sh.draw_rect(fitz.Rect(cr.x0 - pad, cr.y0 - pad, cr.x1 + pad, cr.y1 + pad))
                sh.finish(color=None, fill=BAD, fill_opacity=op)
                sh.commit()

    # grid lines
    for i in range(10):
        major = i % 3 == 0
        w = 2.6 if major else 0.8
        colr = GRID_MAJOR if major else GRID_MINOR
        sh = page.new_shape()
        sh.draw_line(fitz.Point(GX, GY + i * CELL), fitz.Point(GX + GW, GY + i * CELL))
        sh.draw_line(fitz.Point(GX + i * CELL, GY), fitz.Point(GX + i * CELL, GY + GW))
        sh.finish(color=colr, width=w)
        sh.commit()

    # given digits
    for idx, v in enumerate(puzzle):
        if v == 0:
            continue
        r, c = divmod(idx, 9)
        page.insert_text((GX + c * CELL + CELL / 2 - 11, GY + r * CELL + CELL / 2 + 13), str(v), fontsize=34, fontname="helv", color=GIVEN)

    # handwriting: each digit cluster seated in its cell (kills accumulated drift)
    S = CELL / OCELL
    for key, strokes_ in assign.items():
        read = reads[f"{key[0]},{key[1]}"]
        ok = read == solution[key[0] * 9 + key[1]]
        pts = [p for s in strokes_ for p in s]
        bx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
        by = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2
        cr = cellrect(*key)
        off = (cr.x0 + CELL / 2 - bx * S, cr.y0 + CELL / 2 + 3 - by * S)
        for s in strokes_:
            draw_stroke(page, s, INK, scale=S, offset=off, wscale=1.5)

    # per-cell verdict marks
    err_cell = None
    for key, read in reads.items():
        r, c = map(int, key.split(","))
        cr = cellrect(r, c)
        if read == solution[r * 9 + c]:
            sh = page.new_shape()
            sh.draw_polyline([fitz.Point(cr.x0 + 5, cr.y0 + 12), fitz.Point(cr.x0 + 10, cr.y0 + 18), fitz.Point(cr.x0 + 21, cr.y0 + 5)])
            sh.finish(color=GOOD, width=2.2, lineCap=1, lineJoin=1, closePath=False)
            sh.commit()
        else:
            err_cell = (r, c, read)
            sh = page.new_shape()
            sh.draw_rect(fitz.Rect(cr.x0 + 1.5, cr.y0 + 1.5, cr.x1 - 1.5, cr.y1 - 1.5))
            sh.finish(color=BAD, width=2.4)
            sh.commit()
            # ghost of the correct digit
            page.insert_text((cr.x1 - 26, cr.y0 + 26), str(solution[r * 9 + c]), fontsize=22, fontname="hebo", color=ACCENT)

    # amber asterisks on the four exonerated 2s
    for r, c in ((0, 6), (3, 8), (6, 3), (7, 7)):
        cr = cellrect(r, c)
        page.insert_text((cr.x1 - 15, cr.y0 + 16), "*", fontsize=17, fontname="hebo", color=ACCENT)

    # callout for the error
    if err_cell:
        r, c, read = err_cell
        cr = cellrect(r, c)
        cx, cy = W - 232, GY + GW + 74
        sh = page.new_shape()
        sh.draw_line(fitz.Point(cr.x1 - CELL / 2, cr.y1 + 2), fitz.Point(cx + 6, cy - 24))
        sh.finish(color=BAD, width=1.2, stroke_opacity=0.7)
        sh.commit()
        page.insert_text((cx - 60, cy - 8), f"R{r+1}C{c+1}: a bold {read}.", fontsize=16, fontname="hebo", color=BAD)
        page.insert_text((cx - 60, cy + 12), f"That column already has one — it needed a {solution[r*9+c]}.", fontsize=12, fontname="helv", color=TITLE)

    # footer
    fy = H - 58
    page.insert_text((64, fy), "Read directly from reMarkable .rm v6 pen-stroke data · pressure-weighted rendering.", fontsize=12, fontname="helv", color=MUTED)
    page.insert_text((64, fy + 20), "* the four curly 2s, previously misread as 8s by a thin-polyline renderer — exonerated on appeal.", fontsize=12, fontname="helv", color=MUTED)

    doc.save(out_pdf)
    page.get_pixmap(dpi=220).save(out_png)


def main():
    workdir = Path(sys.argv[1])
    answer = json.loads(Path(sys.argv[2]).read_text())
    reads = json.loads(Path(sys.argv[3]).read_text())

    rm = next(workdir.glob("extracted/**/*.rm"))
    strokes = visible_strokes(rm)
    assign = cluster(strokes, answer["puzzle"])
    print(f"clusters assigned: {len(assign)}")

    tiles(assign, workdir / "digits-v2.png")
    poster(assign, answer, reads, workdir / "Sudoku - Graded by Claude.pdf", workdir / "sudoku-graded-poster.png")
    print("done")


if __name__ == "__main__":
    main()
