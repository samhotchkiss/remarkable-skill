#!/usr/bin/env python3
"""Overlay grading marks on the filled Sudoku PDF."""

import json
import sys
from pathlib import Path

import fitz

X0, Y0, CELL = 36.0, 90.0, 44.0
GREEN = (0.1, 0.55, 0.15)
RED = (0.85, 0.1, 0.1)

def main():
    workdir = Path(sys.argv[1])
    answer = json.loads(Path(sys.argv[2]).read_text())
    reads = json.loads(Path(sys.argv[3]).read_text())  # {"r,c": read_digit}
    puzzle, solution = answer["puzzle"], answer["solution"]

    doc = fitz.open(workdir / "filled.pdf")
    page = doc[0]

    n_right = n_wrong = 0
    for key, read in reads.items():
        r, c = map(int, key.split(","))
        want = solution[r * 9 + c]
        cx, cy = X0 + c * CELL, Y0 + r * CELL
        if read == want:
            n_right += 1
            # small green check, top-left corner of cell
            sh = page.new_shape()
            sh.draw_polyline([fitz.Point(cx + 3, cy + 8), fitz.Point(cx + 6, cy + 11), fitz.Point(cx + 12, cy + 3)])
            sh.finish(color=GREEN, width=1.6)
            sh.commit()
        else:
            n_wrong += 1
            # red circle around the cell + correct answer
            sh = page.new_shape()
            sh.draw_oval(fitz.Rect(cx + 1, cy + 1, cx + CELL - 1, cy + CELL - 1))
            sh.finish(color=RED, width=2.0)
            sh.commit()
            page.insert_text((cx + CELL - 13, cy + 13), str(want), fontsize=11, fontname="hebo", color=RED)

    # summary
    wrong_cells = [f"R{int(k.split(',')[0])+1}C{int(k.split(',')[1])+1}" for k, v in reads.items() if v != solution[int(k.split(',')[0]) * 9 + int(k.split(',')[1])]]
    msg = f"Checked by Claude (take 2): {n_right}/{n_right + n_wrong} correct."
    msg += f"  Only miss: {', '.join(wrong_cells)}." if n_wrong else "  Perfect!"
    page.insert_text((36, 76), msg, fontsize=11, fontname="hebo", color=RED if n_wrong else GREEN)

    out = workdir / "Sudoku Puzzle - Graded.pdf"
    doc.save(out)
    print(out)
    print(f"correct: {n_right}, wrong: {n_wrong}")

if __name__ == "__main__":
    main()
