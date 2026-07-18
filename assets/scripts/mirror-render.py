#!/usr/bin/env python3
"""mirror-render.py <doc_dir> [page_cap] — render one mirrored document.

Produces in <doc_dir>:
  render.pdf        faithful full render (native colors, highlighter under-layer)
  pages/page-NN.png current state of each page (dpi 130)
  delta/delta-NN.png for pages whose ink changed since last sync:
                     pre-existing strokes faded gray, NEW strokes in full color
  .strokes.json     per-page stroke fingerprints (sync state, do not edit)

Prints a JSON summary line: {"pages": N, "inkPages": [...], "changedPages": [...]}
"""

import json
import sys
from pathlib import Path

import fitz
from rmlib import (
    PAGE_W, PAGE_H, COLOR_MAP, HIGHLIGHTER_TOOLS,
    visible_strokes_colored, draw_strokes_colored, draw_stroke, draw_highlighter, page_order,
)

FADED = (0.72, 0.73, 0.75)


def fingerprint(pts):
    a, b = pts[0], pts[-1]
    return f"{a[0]:.1f},{a[1]:.1f}|{b[0]:.1f},{b[1]:.1f}|{len(pts)}"


def page_bounds(colored_list):
    xs = [p[0] for colored in colored_list for pts, _t, _c in colored for p in pts]
    ys = [p[1] for colored in colored_list for pts, _t, _c in colored for p in pts]
    if not xs:
        return 0.0, 0.0, PAGE_W, PAGE_H
    M = 12
    return (min(0.0, min(xs) - M), min(0.0, min(ys) - M),
            max(PAGE_W, max(xs) + M), max(PAGE_H, max(ys) + M))


def main():
    doc_dir = Path(sys.argv[1])
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    raw = doc_dir / "raw"

    prev_fp = {}
    fp_file = doc_dir / ".strokes.json"
    if fp_file.exists():
        try:
            prev_fp = json.loads(fp_file.read_text())
        except Exception:
            prev_fp = {}

    rm_by_stem = {p.stem: p for p in raw.rglob("*.rm")}
    order = [u for u in page_order(raw)][:cap]
    pdfs = sorted(raw.glob("*.pdf"))
    base = fitz.open(pdfs[0]) if pdfs else None

    pages_dir = doc_dir / "pages"
    delta_dir = doc_dir / "delta"
    for d in (pages_dir, delta_dir):
        d.mkdir(exist_ok=True)
        for old in d.glob("*.png"):
            old.unlink()

    out_pdf = fitz.open()
    new_fp = {}
    ink_pages, changed_pages = [], []

    n_pages = len(base) if base is not None else len(order)
    for i in range(min(n_pages, cap)):
        uid = order[i] if i < len(order) else None
        rm = rm_by_stem.get(uid)
        colored = visible_strokes_colored(rm) if rm else []

        # page geometry
        if base is not None:
            src_rect = base[i].rect
            page = out_pdf.new_page(width=src_rect.width, height=src_rect.height)
            page.show_pdf_page(page.rect, base, i)
            scale = src_rect.width / PAGE_W
            offset = (0.0, 0.0)
        else:
            if not colored:
                continue
            x0, y0, x1, y1 = page_bounds([colored])
            page = out_pdf.new_page(width=x1 - x0, height=y1 - y0)
            scale = 1.0
            offset = (-x0, -y0)

        if colored:
            ink_pages.append(i)
            draw_strokes_colored(page, colored, scale=scale, offset=offset)

        fps = [fingerprint(pts) for pts, _t, _c in colored]
        new_fp[str(i)] = fps

        # delta page if ink changed
        old = set(prev_fp.get(str(i), []))
        fresh = [j for j, fp in enumerate(fps) if fp not in old]
        if prev_fp and (fresh or (old and set(fps) != old)):
            changed_pages.append(i)
            dpage_doc = fitz.open()
            if base is not None:
                dpage = dpage_doc.new_page(width=src_rect.width, height=src_rect.height)
                dpage.show_pdf_page(dpage.rect, base, i)
            else:
                x0, y0, x1, y1 = page_bounds([colored])
                dpage = dpage_doc.new_page(width=x1 - x0, height=y1 - y0)
            for j, (pts, tool, color) in enumerate(colored):
                if j in fresh:
                    continue
                if tool in HIGHLIGHTER_TOOLS:
                    draw_highlighter(dpage, pts, FADED, scale=scale, offset=offset)
                else:
                    draw_stroke(dpage, pts, color=FADED, scale=scale, offset=offset, opacity=0.55)
            fresh_colored = [colored[j] for j in fresh]
            draw_strokes_colored(dpage, fresh_colored, scale=scale, offset=offset)
            dpage.get_pixmap(dpi=130).save(delta_dir / f"delta-{i+1:02d}.png")
            dpage_doc.close()

        page.get_pixmap(dpi=130).save(pages_dir / f"page-{i+1:02d}.png")

    if base is not None:
        base.close()
    if len(out_pdf):
        out_pdf.save(doc_dir / "render.pdf")
    out_pdf.close()

    fp_file.write_text(json.dumps(new_fp))
    print(json.dumps({"pages": min(n_pages, cap), "inkPages": ink_pages, "changedPages": changed_pages}))


if __name__ == "__main__":
    main()
