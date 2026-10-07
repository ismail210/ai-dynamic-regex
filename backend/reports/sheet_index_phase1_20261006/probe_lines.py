"""Dump title-zone text lines (display space) for a page, to design the reader.

python reports/sheet_index_phase1_20261006/probe_lines.py <pdf> <page> <x_frac> <y_frac>
"""

import sys

sys.path.insert(0, ".")

from services.engineering.page_space import to_display  # noqa: E402
from services.pdf_parser import extract_document_structure  # noqa: E402

path, page, zx, zy = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
doc = extract_document_structure(path)
meta = next(p for p in doc["pages"] if p["page_number"] == page)
W, H, R = meta["width"], meta["height"], meta["rotation"]
rows = []
for line in doc["lines"]:
    if line["page_number"] != page:
        continue
    box = to_display(R, W, H, line["bbox"])
    if box[0] >= zx * W and box[1] >= zy * H:
        rows.append((box, line))
for box, line in sorted(rows, key=lambda r: (r[0][1], r[0][0])):
    print(f"{box} rot={line.get('rotation')} fs={line.get('font_size')} | {line['text']!r}")
