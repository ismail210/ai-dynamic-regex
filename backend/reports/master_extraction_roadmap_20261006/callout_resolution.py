"""Split stacked / inline detail bubbles into own-sheet view titles and cross-sheet references.

A page's own sheet id is the tallest sheet-id word on the page (the title-block
number). A target is "in PDF" when some page owns that sheet id. This is a
census: it measures whether a target sheet exists, not which detail on it.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from census import DETAIL_CALLOUT_RE, PDFS  # noqa: E402
from stacked_callouts import SHEET_WORD_RE, stacked  # noqa: E402


def own_sheet(page: fitz.Page) -> str:
    best = ("", 0.0)
    for w in page.get_text("words"):
        if SHEET_WORD_RE.match(w[4]):
            height = w[3] - w[1]
            if page.rotation:
                height = max(height, w[2] - w[0])
            if height > best[1]:
                best = (w[4].replace("-", "").rstrip("."), height)
    return best[0]


def main() -> None:
    out = {}
    for key, path in PDFS.items():
        if not path.exists():
            continue
        doc = fitz.open(str(path))
        owners = {index + 1: own_sheet(page) for index, page in enumerate(doc)}
        owned = {s for s in owners.values() if s}
        counts = Counter()
        unresolved_targets = Counter()
        page_refs = {}
        view_titles = set()
        for index, page in enumerate(doc):
            number = index + 1
            refs = [(label, target) for label, target, _ in stacked(page)]
            refs += [(label, target.replace("-", "")) for label, target in DETAIL_CALLOUT_RE.findall((page.get_text() or "").upper())]
            page_refs[number] = refs
            for label, target in refs:
                if target == owners[number]:
                    view_titles.add((label, target))
        for number, refs in page_refs.items():
            mine = owners[number]
            for label, target in refs:
                if target == mine:
                    counts["own_sheet_view_title"] += 1
                elif target in owned:
                    counts["cross_sheet_target_in_pdf"] += 1
                    if (label, target) in view_titles:
                        counts["cross_sheet_detail_number_found_on_target"] += 1
                    else:
                        counts["cross_sheet_detail_number_not_found"] += 1
                else:
                    counts["cross_sheet_target_missing"] += 1
                    unresolved_targets[target] += 1
        out[key] = {
            "pages": doc.page_count,
            "pages_with_own_sheet_id": sum(1 for s in owners.values() if s),
            "distinct_own_sheet_ids": len(owned),
            **counts,
            "missing_targets": unresolved_targets.most_common(10),
        }
        print(key, json.dumps(out[key]))
    (Path(__file__).resolve().parent / "callout_resolution.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
