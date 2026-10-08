"""Render title-block crops of the Phase 0 pages for human reading.

The crop boxes are generous display-space fractions per layout family, used
only to make the printed title block readable; nothing here feeds the parser.
Run from backend/: python reports/sheet_index_phase1_20261006/render_title_blocks.py
"""

import sys
from pathlib import Path

import fitz

TESTING = "/Users/hibareda/Desktop/Testing Projects/"
PROJECTS = {
    "furley": ("uploads/Struct.pdf", [1, 2, 3, 19, 24], (0.86, 0.45, 1.0, 1.0)),
    "burrville": ("uploads/Burrville ES - ST.pdf", [1, 5, 12, 20, 29], (0.88, 0.60, 1.0, 1.0)),
    "brandywine": ("uploads/Structural4__3aa51f661bdf.pdf", [1, 4, 20, 35, 43], (0.88, 0.60, 1.0, 1.0)),
    "springhill": ("uploads/ST - Springhill Lake__f6ddc4a7e233.pdf", [1, 5, 14, 22, 28], (0.88, 0.60, 1.0, 1.0)),
    "osse": (TESTING + "OSSE - ST.pdf", [1, 5, 10, 15, 26], (0.84, 0.70, 1.0, 1.0)),
    "yellowspring": (TESTING + "ST1.pdf", [1, 5, 13, 25, 40], (0.86, 0.70, 1.0, 1.0)),
    "washlatin": (TESTING + "New bldg - St.pdf", [1, 5, 12, 18, 23], (0.62, 0.90, 1.0, 1.0)),
    "fortdavis": (TESTING + "Structure - Copy1 - edit.pdf", [1, 5, 10, 15, 20], (0.88, 0.60, 1.0, 1.0)),
}
OUT = Path(__file__).parent / "renders"
# Manual-validation pages, deliberately outside the Phase 0 set (holdout).
HOLDOUT = {
    "furley": [10, 20], "burrville": [3, 15], "brandywine": [10, 30], "springhill": [10, 20],
    "osse": [2, 20], "yellowspring": [8, 30], "washlatin": [8, 19], "fortdavis": [3, 12],
}


def main(only=None, holdout=False):
    OUT.mkdir(exist_ok=True)
    for key, (path, pages, frac) in PROJECTS.items():
        if only and key not in only:
            continue
        prefix = "ho" if holdout else "tb"
        with fitz.open(path) as doc:
            for number in HOLDOUT[key] if holdout else pages:
                page = doc[number - 1]
                w, h = page.rect.width, page.rect.height
                clip = fitz.Rect(frac[0] * w, frac[1] * h, frac[2] * w, frac[3] * h)
                dpi = 110
                page.get_pixmap(dpi=dpi, clip=clip).save(OUT / f"{prefix}_{key}_p{number}.png")
                if holdout:
                    page.get_pixmap(dpi=40).save(OUT / f"ho_{key}_p{number}_full.png")
                print(key, number, page.rotation)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--holdout"]
    main(set(args) or None, holdout="--holdout" in sys.argv)
