#!/usr/bin/env python3
"""Generate a Sudoku puzzle PDF for the reMarkable, plus a solution JSON."""

import json
import random
import sys
from pathlib import Path

import fitz  # PyMuPDF


def solve_count(grid, limit=2):
    """Count solutions up to limit (for uniqueness checking)."""
    for i in range(81):
        if grid[i] == 0:
            r, c = divmod(i, 9)
            count = 0
            for v in range(1, 10):
                if valid(grid, r, c, v):
                    grid[i] = v
                    count += solve_count(grid, limit - count)
                    grid[i] = 0
                    if count >= limit:
                        return count
            return count
    return 1


def valid(grid, r, c, v):
    for j in range(9):
        if grid[r * 9 + j] == v or grid[j * 9 + c] == v:
            return False
    br, bc = 3 * (r // 3), 3 * (c // 3)
    for i in range(br, br + 3):
        for j in range(bc, bc + 3):
            if grid[i * 9 + j] == v:
                return False
    return True


def fill(grid, rng):
    for i in range(81):
        if grid[i] == 0:
            r, c = divmod(i, 9)
            vals = list(range(1, 10))
            rng.shuffle(vals)
            for v in vals:
                if valid(grid, r, c, v):
                    grid[i] = v
                    if fill(grid, rng):
                        return True
                    grid[i] = 0
            return False
    return True


def make_puzzle(givens_target=40, seed=None):
    rng = random.Random(seed)
    solution = [0] * 81
    fill(solution, rng)
    puzzle = solution[:]
    cells = list(range(81))
    rng.shuffle(cells)
    for idx in cells:
        if sum(1 for x in puzzle if x) <= givens_target:
            break
        saved = puzzle[idx]
        puzzle[idx] = 0
        if solve_count(puzzle[:]) != 1:
            puzzle[idx] = saved
    return puzzle, solution


def render_pdf(puzzle, out_path):
    # Page proportioned to the reMarkable screen (1404x1872) so it fills the display
    W, H = 468, 624
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)

    page.insert_text((40, 48), "Sudoku", fontsize=28, fontname="helv")
    page.insert_text((40, 68), "Fill it in, then have Claude check it.", fontsize=10, fontname="helv", color=(0.35, 0.35, 0.35))

    grid_size = 396
    x0 = (W - grid_size) / 2
    y0 = 90
    cell = grid_size / 9

    for i in range(10):
        w = 2.4 if i % 3 == 0 else 0.7
        # horizontal
        page.draw_line(fitz.Point(x0, y0 + i * cell), fitz.Point(x0 + grid_size, y0 + i * cell), width=w)
        # vertical
        page.draw_line(fitz.Point(x0 + i * cell, y0), fitz.Point(x0 + i * cell, y0 + grid_size), width=w)

    for idx, v in enumerate(puzzle):
        if v == 0:
            continue
        r, c = divmod(idx, 9)
        # center the digit in its cell
        tx = x0 + c * cell + cell / 2 - 6
        ty = y0 + r * cell + cell / 2 + 7
        page.insert_text((tx, ty), str(v), fontsize=20, fontname="helv")

    doc.save(out_path)
    doc.close()


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else None
    puzzle, solution = make_puzzle(givens_target=40, seed=seed)
    pdf_path = out_dir / "sudoku.pdf"
    render_pdf(puzzle, pdf_path)
    meta = {
        "puzzle": puzzle,
        "solution": solution,
        "givens": sum(1 for x in puzzle if x),
    }
    (out_dir / "sudoku-answer.json").write_text(json.dumps(meta))
    print(f"PDF: {pdf_path}")
    print(f"Answer key: {out_dir / 'sudoku-answer.json'} (givens: {meta['givens']})")
