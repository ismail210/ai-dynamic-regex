"""Section 10 -- hard clean negatives.

Curates the subset of Layer-1 clean identity examples that specifically
contain characters commonly confused by OCR/typos (0/1/5/8/2/6, or round-HSS
decimal fields) in VALID positions, so Model A training can oversample them
and specifically learn "a suspicious-looking character is not proof of
corruption" (Section 10's own framing).

Usage:
    python phase_hard_negatives.py --v2 <v2 corpus dir>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import read_jsonl, write_jsonl  # noqa: E402
from services.structural_parser import parse_fields  # noqa: E402

_CONFUSABLE_DIGITS = set("015826")
_DECIMAL_RE = re.compile(r"\d+\.\d+")


def hard_case_reason(label: str) -> str | None:
    fields = parse_fields(label)
    if fields.grammar == "hss_round":
        return "round_hss_decimal"
    if _DECIMAL_RE.search(label):
        return "decimal_field"
    tail = re.sub(r"^[A-Z]+", "", label)
    if any(ch in _CONFUSABLE_DIGITS for ch in tail):
        return "confusable_digit_present"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2", required=True, type=Path)
    args = parser.parse_args()

    rows = list(read_jsonl(args.v2 / "clean" / "identity_examples.jsonl"))
    out = []
    for row in rows:
        reason = hard_case_reason(row["input"])
        if reason:
            out.append({**row, "hard_negative_reason": reason})

    write_jsonl(args.v2 / "clean" / "hard_clean_negatives.jsonl", out)
    print(f"Hard clean negatives: {len(out)} / {len(rows)} identity examples")
    from collections import Counter
    print(Counter(r["hard_negative_reason"] for r in out))
    from collections import Counter as C2
    print("by split:", C2(r["split"] for r in out))


if __name__ == "__main__":
    main()
