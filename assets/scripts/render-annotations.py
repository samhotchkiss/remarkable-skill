#!/usr/bin/env python3
"""Render a downloaded reMarkable document (extracted archive) to PDF with
handwriting drawn pressure-weighted. Works for annotated PDFs and pure notebooks.

Usage: render-annotations.py <extracted_dir> <output.pdf> [max_pages]
"""

import sys
from rmlib import render_document

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: render-annotations.py <extracted_dir> <output.pdf> [max_pages]")
        sys.exit(1)
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else None
    n = render_document(sys.argv[1], sys.argv[2], max_pages=max_pages)
    if n == 0:
        print("No pages rendered (no PDF and no visible strokes).")
        sys.exit(2)
    print(f"Rendered {n} page(s) -> {sys.argv[2]}")
