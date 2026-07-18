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

# reMarkable color ids -> RGB
COLOR_MAP = {
    0: (0.05, 0.05, 0.07),   # black
    1: (0.45, 0.47, 0.50),   # gray
    2: (1.0, 1.0, 1.0),      # white (eraser-paint)
    3: (0.99, 0.85, 0.21),   # yellow
    4: (0.30, 0.75, 0.35),   # green
    5: (0.95, 0.45, 0.65),   # pink
    6: (0.20, 0.35, 0.85),   # blue
    7: (0.85, 0.15, 0.15),   # red
}
# highlighter tool ids (18 current firmware; 5 and 8 on older firmware)
HIGHLIGHTER_TOOLS = {5, 8, 18}
HIGHLIGHTER_OPACITY = 0.45


def _color_of(line):
    cid = getattr(line, "color", 0)
    cid = getattr(cid, "value", cid)  # rmscene may hand back an enum
    return COLOR_MAP.get(cid, COLOR_MAP[0])


def _legacy_strokes(rm_path, version):
    """Parse legacy .lines format (v3/v5): binary layers/strokes/points.
    Coordinates are left-origin 0..1404 (NOT centered like v6)."""
    import struct

    out = []
    with open(rm_path, "rb") as f:
        f.seek(43)  # fixed-width header
        (nlayers,) = struct.unpack("<i", f.read(4))
        for _ in range(nlayers):
            (nstrokes,) = struct.unpack("<i", f.read(4))
            for _ in range(nstrokes):
                if version >= 5:
                    pen, color, _u1, width, _u2, npts = struct.unpack("<iiifii", f.read(24))
                else:
                    pen, color, _u1, width, npts = struct.unpack("<iiifi", f.read(20))
                pts = []
                for _ in range(npts):
                    x, y, _speed, _direction, pw, pressure = struct.unpack("<ffffff", f.read(24))
                    pts.append((x * SCALE, y * SCALE, max(pw, width) * SCALE, min(max(pressure, 0.0), 1.0)))
                if pts:
                    out.append((pts, pen, color))
    return out


def visible_strokes_colored(rm_path):
    """Visible (non-erased) strokes with pen metadata:
    [(pts, tool_id, color_id), ...] where pts = [(x, y, width_pt, pressure01), ...]
    in page-point coordinates (origin top-left of a PAGE_W x PAGE_H page).
    Handles v6 (scene tree) and legacy v3/v5 (.lines binary) formats."""
    with open(rm_path, "rb") as f:
        header = f.read(43)
    if header.startswith(b"reMarkable .lines file, version=5"):
        return _legacy_strokes(rm_path, 5)
    if header.startswith(b"reMarkable .lines file, version=3"):
        return _legacy_strokes(rm_path, 3)

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
                    tool = getattr(child, "tool", 0)
                    tool = getattr(tool, "value", tool)
                    color = getattr(child, "color", 0)
                    color = getattr(color, "value", color)
                    out.append((pts, tool, color))

    walk(tree.root)
    return out


def visible_strokes(rm_path):
    """Back-compat: bare stroke point lists (no pen metadata)."""
    return [pts for pts, _tool, _color in visible_strokes_colored(rm_path)]


def _draw_runs(page, pts, widths, color, scale, offset, opacity, cap):
    """Draw a stroke as polyline runs grouped by quantized width — one Shape commit
    per stroke instead of one per segment (50x fewer PDF ops, visually identical)."""
    sh = page.new_shape()
    run = [pts[0]]
    run_w = widths[0]
    QUANT = 0.25

    def flush(run, w):
        if len(run) < 2:
            return
        sh.draw_polyline([fitz.Point(offset[0] + p[0] * scale, offset[1] + p[1] * scale) for p in run])
        sh.finish(color=color, width=w * scale, stroke_opacity=opacity, lineCap=cap, lineJoin=1, closePath=False)

    for p, w in zip(pts[1:], widths[1:]):
        if abs(w - run_w) > QUANT:
            run.append(p)
            flush(run, run_w)
            run = [p]
            run_w = w
        else:
            run.append(p)
    flush(run, run_w)
    sh.commit()


def draw_stroke(page, pts, color=(0, 0, 0), scale=1.0, offset=(0.0, 0.0), wscale=0.85, opacity=1.0):
    """Pressure-weighted ink rendering. Default wscale 0.85 reproduces a fineliner
    faithfully (1.5 looked like a marker)."""
    if len(pts) < 2:
        return
    widths = [max(0.3, p[2] * wscale * (0.7 + 0.6 * p[3])) for p in pts]
    _draw_runs(page, pts, widths, color, scale, offset, opacity, cap=1)


def draw_highlighter(page, pts, color, scale=1.0, offset=(0.0, 0.0), wscale=1.0):
    """Highlighter rendering: wide flat stroke, no pressure modulation, translucent,
    butt caps. Draw ALL highlighter strokes before ink so ink sits on top."""
    if len(pts) < 2:
        return
    widths = [max(2.0, p[2] * wscale) for p in pts]
    _draw_runs(page, pts, widths, color, scale, offset, HIGHLIGHTER_OPACITY, cap=0)


def draw_strokes_colored(page, colored, scale=1.0, offset=(0.0, 0.0), wscale=0.85, ink_override=None):
    """Render a visible_strokes_colored() list faithfully: highlighters first
    (translucent under-layer), then ink in its native color (or ink_override)."""
    hl = [(pts, color) for pts, tool, color in colored if tool in HIGHLIGHTER_TOOLS]
    ink = [(pts, color) for pts, tool, color in colored if tool not in HIGHLIGHTER_TOOLS]
    for pts, color in hl:
        draw_highlighter(page, pts, COLOR_MAP.get(color, COLOR_MAP[3]), scale=scale, offset=offset)
    for pts, color in ink:
        c = ink_override if ink_override is not None else COLOR_MAP.get(color, COLOR_MAP[0])
        draw_stroke(page, pts, color=c, scale=scale, offset=offset, wscale=wscale)


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


def render_document(extracted_dir, out_pdf, ink=None, max_pages=None, wscale=0.85):
    """Render an extracted document archive: original PDF pages (if any) with
    handwriting overlaid, or handwriting on blank tablet-aspect pages for notebooks.
    Strokes render in their native pen colors with highlighters as a translucent
    under-layer; pass ink=(r,g,b) to force all pen strokes to one color.
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
            draw_strokes_colored(page, visible_strokes_colored(rm), scale=s, wscale=wscale, ink_override=ink)
        src.close()
    else:
        count = 0
        for uid in order:
            if max_pages is not None and count >= max_pages:
                break
            rm = rm_by_stem.get(uid)
            if not rm:
                continue
            colored = visible_strokes_colored(rm)
            if not colored:
                continue
            # Extent-aware page: wider devices (e.g. Paper Pro, 1620px) produce
            # coordinates outside the classic 1404px frame — grow the page rather
            # than clipping strokes.
            xs = [p[0] for pts, _t, _c in colored for p in pts]
            ys = [p[1] for pts, _t, _c in colored for p in pts]
            M = 12
            x0 = min(0.0, min(xs) - M)
            y0 = min(0.0, min(ys) - M)
            x1 = max(PAGE_W, max(xs) + M)
            y1 = max(PAGE_H, max(ys) + M)
            page = out.new_page(width=x1 - x0, height=y1 - y0)
            draw_strokes_colored(page, colored, offset=(-x0, -y0), wscale=wscale, ink_override=ink)
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
