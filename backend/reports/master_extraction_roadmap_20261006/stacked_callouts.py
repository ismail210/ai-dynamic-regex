"""Count detail bubbles printed as a number stacked over a sheet id (two words).

A stacked callout is a sheet-id word with a short label word centred directly
above it. This is a census only: it does not decide what the callout targets.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from census import PDFS  # noqa: E402

SHEET_WORD_RE = re.compile(r"^S-?\d{1,2}(?:\.\d{1,2}|\d{1,2})[A-Z]?(?:-[A-Z])?\.?$")
LABEL_WORD_RE = re.compile(r"^(?:[A-Z]?\d{1,2}|[A-Z])$")


def stacked(page: fitz.Page) -> list:
    words = page.get_text("words")
    sheets = [w for w in words if SHEET_WORD_RE.match(w[4])]
    labels = [w for w in words if LABEL_WORD_RE.match(w[4])]
    found = []
    for s in sheets:
        sx = (s[0] + s[2]) / 2
        for label in labels:
            lx = (label[0] + label[2]) / 2
            gap = s[1] - label[3]
            if abs(lx - sx) <= max(6.0, (s[2] - s[0]) * 0.6) and -1.0 <= gap <= 14.0:
                found.append((label[4], s[4].replace("-", "").rstrip("."), [round(v, 1) for v in s[:4]]))
                break
    return found


def main() -> None:
    out = {}
    for key, path in PDFS.items():
        if not path.exists():
            continue
        doc = fitz.open(str(path))
        per_page, targets, sample = {}, Counter(), []
        title_blocks = 0
        for index, page in enumerate(doc):
            hits = stacked(page)
            if hits:
                per_page[index + 1] = len(hits)
                for label, target, box in hits:
                    targets[target] += 1
                    if len(sample) < 6:
                        sample.append({"page": index + 1, "label": label, "target": target, "bbox": box})
        out[key] = {
            "stacked_callouts": sum(per_page.values()),
            "pages_with_stacked": len(per_page),
            "distinct_targets": len(targets),
            "top_targets": targets.most_common(8),
            "sample": sample,
        }
        print(key, json.dumps(out[key])[:600])
    (Path(__file__).resolve().parent / "stacked_callouts.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
