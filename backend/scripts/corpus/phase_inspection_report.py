"""Human inspection report (Section 35) -- a static HTML page, not a full
app. Text-only (no page-crop rendering, given this pilot's time budget);
still shows everything the spec asks for: project, clean text, corrupted
text, canonical target, corruption type, difficulty, family, split.

Samples 100 train / 50 validation / 50 test examples by default.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import read_jsonl  # noqa: E402

ROW_TEMPLATE = """
<tr>
  <td>{split}</td><td>{project}</td><td>{family}</td>
  <td class="mono strike">{clean}</td><td class="mono">{corrupted}</td>
  <td>{category}</td><td>{difficulty}</td><td>{operation}</td>
</tr>"""

PAGE_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>Corpus Inspection Sample</title>
<style>
body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 24px; color: #1b1f1d; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
th {{ background: #f3f4f1; position: sticky; top: 0; }}
.mono {{ font-family: 'IBM Plex Mono', monospace; }}
.strike {{ color: #888; }}
h1 {{ font-size: 20px; }}
.meta {{ color: #666; font-size: 13px; margin-bottom: 16px; }}
</style></head><body>
<h1>Structural corruption corpus -- human inspection sample</h1>
<p class="meta">{count} randomly sampled examples (seed={seed}). Question to answer while reading:
"Do these examples actually look like errors our system encounters?"</p>
<table>
<thead><tr><th>Split</th><th>Project</th><th>Family</th><th>Clean</th><th>Corrupted</th>
<th>Category</th><th>Difficulty</th><th>Operation</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    out_dir: Path = args.output
    all_rows = (
        list(read_jsonl(out_dir / "synthetic" / "repair_pairs.jsonl"))
        + list(read_jsonl(out_dir / "synthetic" / "normalization_variants.jsonl"))
        + list(read_jsonl(out_dir / "synthetic" / "completion_examples.jsonl"))
    )
    by_split = {"train": [], "validation": [], "test": []}
    for r in all_rows:
        by_split.setdefault(r["split"], []).append(r)

    rng = random.Random(args.seed)
    sample = (
        rng.sample(by_split["train"], min(100, len(by_split["train"])))
        + rng.sample(by_split["validation"], min(50, len(by_split["validation"])))
        + rng.sample(by_split["test"], min(50, len(by_split["test"])))
    )
    rng.shuffle(sample)

    rows_html = "".join(
        ROW_TEMPLATE.format(
            split=r["split"], project=r["source"]["project_id"], family=r["clean"]["family"],
            clean=r["clean"]["canonical_text"], corrupted=r["corrupted"]["text"],
            category=r["category"], difficulty=r["difficulty"], operation=r["target_operation"],
        )
        for r in sample
    )
    html = PAGE_TEMPLATE.format(count=len(sample), seed=args.seed, rows=rows_html)
    report_path = out_dir / "reports" / "human_inspection_sample.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    print(f"Wrote {report_path} with {len(sample)} sampled examples "
          f"({len(by_split['train'])} train / {len(by_split['validation'])} val / {len(by_split['test'])} test pool)")


if __name__ == "__main__":
    main()
