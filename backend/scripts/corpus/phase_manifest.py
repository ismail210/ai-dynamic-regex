"""Assemble the top-level manifest.json (Section 37) tying every phase's
output together, including the explicit source-of-truth commit for the
semantic_preprocessor implementation used throughout (Section 4).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import write_json  # noqa: E402


def git_commit(repo_dir: Path) -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, text=True).strip()
        return {"commit": commit, "branch": branch}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()

    out_dir: Path = args.output
    repo_info = git_commit(args.repo)

    manifest = {
        "schema_version": "0.1.0",
        "dataset_name": "estima3d_structural_corpus_v1",
        "source_of_truth": {
            "semantic_preprocessor_repo": str(args.repo),
            **repo_info,
            "note": (
                "A second copy of services/semantic_preprocessor exists in "
                "C:\\Users\\Bassam\\git\\ai-dynamic-regex. Content-diffed "
                "against this commit (CRLF-normalized): identical except "
                "structural_parser.py's catalog-import fallback order, which "
                "deliberately differs per repo's own catalog module layout. "
                "This corpus was built exclusively against THIS commit."
            ),
        },
        "input_corpus": load(out_dir / "inventory" / "summary.json"),
        "mining": load(out_dir / "inventory" / "mine_summary.json"),
        "clean_and_errors": load(out_dir / "inventory" / "clean_and_errors_summary.json"),
        "splits": load(out_dir / "splits" / "split_manifest.json"),
        "phase_e": load(out_dir / "inventory" / "phase_e_summary.json"),
        "grouping": load(out_dir / "inventory" / "grouping_summary.json"),
        "completion_audit": load(out_dir / "inventory" / "completion_audit_summary.json"),
        "not_run_this_pass": {
            "empirical_ocr_confusion_matrix": "No OCR engine installed/vetted in this environment this session; character-confusion weights are assumed, not empirical -- see reports/ocr_confusion_matrix.md.",
            "lightgbm_ranker": "Infrastructure confirmed available (lightgbm/xgboost installed); not trained this pass -- recommended as the next experiment, see reports/deep_learning_feasibility.md.",
            "corrupted_pdf_fixtures": "Deferred -- text-level corruption pipeline validated first per the project's own stated priority order; see reports/corruption_dataset_quality.md.",
            "deep_learning_model": "Not built -- see reports/deep_learning_feasibility.md for the explicit NOT YET verdict and numbers.",
        },
    }
    write_json(out_dir / "manifest.json", manifest)
    print(json.dumps({"source_of_truth": manifest["source_of_truth"]}, indent=2))


if __name__ == "__main__":
    main()
