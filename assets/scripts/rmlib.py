#!/usr/bin/env python3
"""rmlib — canonical helpers for reading and rendering reMarkable .rm v6 pen data.

Hard-won rules encoded here (do not regress):
- Strokes live in the scene tree; walk visible Group/Line via read_tree() so
  erased strokes (tombstones) are excluded. Raw read_blocks() sees everything.
- v6 x-coordinates are centered on the middle of the 1404px display: add RM_WIDTH/2.
- ALWAYS render pressure-weighted: per-point width/4 x thickness_scale, modulated
  by pressure. Thin uniform polylines distort glyphs (a curly "2" reads as an "8").
- reMarkable display is 1404x1872 (3:4). A 468x624pt PDF page fills it exactly.
"""

from pathlib import Path

import fitz
from rmscene import read_tree
from rmscene.scene_items import Group, Line

RM_WIDTH, RM_HEIGHT = 1404, 1872
PAGE_W, PAGE_H = 468.0, 624.0  # PDF points, exact tablet aspect
SCALE = PAGE_W / RM_WIDTH      # rm units -> page points


def visible_strokes(rm_path):
    """Visible (non-erased) strokes as [[(x, y, width_pt, pressure01), ...], ...]
    in page-point coordinates (origin top-left of a PAGE_W x PAGE_H page)."""
    with open(rm_path, "rb") as f:
        tree = read_tree(f)
    out = []

    def walk(group):
        for child in group.children.values():
            if isinstance(child, Group):
                walk(child)
            elif isinstance(child, Line):
                pts = [
                    (
                        (p.x + RM_WIDTH / 2) * SCALE,
                        p.y * SCALE,
                        (p.width / 4.0) * SCALE * child.thickness_scale,
                        p.pressure / 255.0,
                    )
                    for p in child.points
                ]
                if pts:
                    out.append(pts)

    walk(tree.root)
    return out


def draw_stroke(page, pts, color=(0, 0, 0), scale=1.0, offset=(0.0, 0.0), wscale=1.5, opacity=1.0):
    """Pressure-weighted rendering: one segment per point pair, width from pen data."""
    for a, b in zip(pts, pts[1:]):
        w = max(0.35, (a[2] + b[2]) / 2 * wscale * (0.7 + 0.6 * (a[3] + b[3]) / 2))
        sh = page.new_shape()
        sh.draw_line(
            fitz.Point(offset[0] + a[0] * scale, offset[1] + a[1] * scale),
            fitz.Point(offset[0] + b[0] * scale, offset[1] + b[1] * scale),
        )
        sh.finish(color=color, width=w * scale, stroke_opacity=opacity, lineCap=1, lineJoin=1, closePath=False)
        sh.commit()


def page_order(doc_dir):
    """Ordered page uuids from the .content file; falls back to .rm stems found on disk."""
    import json

    for content_file in Path(doc_dir).glob("*.content"):
        try:
            c = json.loads(content_file.read_text())
            pages = c.get("cPages", {}).get("pages", [])
            ids = [p.get("id") for p in pages if isinstance(p, dict) and not p.get("deleted")]
            if ids:
                return ids
        except Exception:
            pass
    return [p.stem for p in Path(doc_dir).rglob("*.rm")]


def render_document(extracted_dir, out_pdf, ink=(0, 0, 0), max_pages=None, wscale=1.5):
    """Render an extracted document archive: original PDF pages (if any) with
    handwriting overlaid, or handwriting on blank tablet-aspect pages for notebooks.
    Returns the number of pages rendered."""
    d = Path(extracted_dir)
    pdfs = sorted(d.glob("*.pdf"))
    rm_by_stem = {p.stem: p for p in d.rglob("*.rm")}
    order = page_order(d)

    out = fitz.open()
    if pdfs:
        src = fitz.open(pdfs[0])
        n = len(src) if max_pages is None else min(max_pages, len(src))
        out.insert_pdf(src, from_page=0, to_page=n - 1)
        for i in range(n):
            uid = order[i] if i < len(order) else None
            rm = rm_by_stem.get(uid)
            if not rm:
                continue
            page = out[i]
            s = page.rect.width / PAGE_W
            for stroke in visible_strokes(rm):
                draw_stroke(page, stroke, color=ink, scale=s, wscale=wscale)
        src.close()
    else:
        count = 0
        for uid in order:
            if max_pages is not None and count >= max_pages:
                break
            rm = rm_by_stem.get(uid)
            if not rm:
                continue
            strokes = visible_strokes(rm)
            if not strokes:
                continue
            page = out.new_page(width=PAGE_W, height=PAGE_H)
            for stroke in strokes:
                draw_stroke(page, stroke, color=ink, wscale=wscale)
            count += 1

    n = len(out)
    if n:
        out.save(out_pdf)
    out.close()
    return n


def cluster_strokes(strokes, gap_pt=3.4):
    """Group strokes into glyph clusters by bounding-box gap (page points).
    Returns list of (centroid_xy, [strokes]). Sort/slice by known layout to assign;
    never bias glyph reads toward expected answers."""

    def bbox(pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def gap(a, b):
        dx = max(a[0] - b[2], b[0] - a[2], 0)
        dy = max(a[1] - b[3], b[1] - a[3], 0)
        return max(dx, dy)

    clusters = [[s] for s in strokes]
    merged = True
    while merged:
        merged = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                bi = bbox([p for s in clusters[i] for p in s])
                bj = bbox([p for s in clusters[j] for p in s])
                if gap(bi, bj) < gap_pt:
                    clusters[i] += clusters[j]
                    del clusters[j]
                    merged = True
                    break
            if merged:
                break

    def centroid(c):
        pts = [p for s in c for p in s]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    return [(centroid(c), c) for c in clusters]
