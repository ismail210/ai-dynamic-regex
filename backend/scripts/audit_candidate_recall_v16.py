"""
Candidate-generation recall audit against the AISC v16 all-editions catalog
(3,842 designations, 37 families) -- BEFORE any training.

The ranker can never recover an answer candidate generation never produces,
so this measures, for `generate_candidates_v3`, per catalog label × per
single-corruption-family: does the true canonical designation appear
anywhere in the generated candidate set (limit=25)?

This is a diagnostic pass, not the training corpus (Phase 6 builds that
separately). It exists to catch a candidate-generation gap early, before
investing in hard-negative mining/training against the larger catalog.

Temporarily reloads services.database_loader to the new catalog and
refreshes every dependent module-level cache (wildcard_matcher,
label_reconstruction.candidates, services.structural_parser,
label_reconstruction.corruption's family-code set) -- then restores the
production catalog (old XLSX) before exiting, since those caches are
process-global and every other script/test assumes the production catalog.

Writes: database/reports/aisc_v16_candidate_recall_audit.md
Run: python backend/scripts/audit_candidate_recall_v16.py
"""

from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import database_loader  # noqa: E402
from services import wildcard_matcher  # noqa: E402
from services.label_reconstruction import corruption  # noqa: E402
from services.label_reconstruction.candidates import generate_candidates_v3  # noqa: E402
from services.label_reconstruction.catalog_reload import refresh_all_dependent_caches  # noqa: E402

DATABASE_DIR = BACKEND_DIR / "database"
CATALOG_PATH = DATABASE_DIR / "aisc_v16_label_catalog.csv"
REPORTS_DIR = DATABASE_DIR / "reports"
OUT_REPORT = REPORTS_DIR / "aisc_v16_candidate_recall_audit.md"

SEED = 20260813
CANDIDATE_LIMIT = 25


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    catalog = database_loader.reload_from_aisc_v16_catalog(CATALOG_PATH)
    refresh_all_dependent_caches()
    try:
        entries = catalog.entries()
        total_checks = 0
        hits = 0
        by_family = defaultdict(lambda: [0, 0])  # family -> [hits, checks]
        by_corruption = defaultdict(lambda: [0, 0])
        by_scope = defaultdict(lambda: [0, 0])
        misses_sample = []

        for entry in entries:
            label = entry.designation
            for corruption_name, fn in corruption.CORRUPTION_FAMILIES:
                result = fn(label, rng)
                if result is None or result.text == label:
                    continue
                total_checks += 1
                candidate_set = generate_candidates_v3(result.text, limit=CANDIDATE_LIMIT)
                hit = label in candidate_set.candidates
                hits += int(hit)

                fam_bucket = by_family[entry.family]
                fam_bucket[1] += 1
                fam_bucket[0] += int(hit)

                corr_bucket = by_corruption[corruption_name]
                corr_bucket[1] += 1
                corr_bucket[0] += int(hit)

                scope_bucket = by_scope[entry.catalog_scope]
                scope_bucket[1] += 1
                scope_bucket[0] += int(hit)

                if not hit and len(misses_sample) < 40:
                    misses_sample.append((entry.family, label, corruption_name, result.text))

        overall_recall = hits / total_checks if total_checks else 0.0

        lines = []
        lines.append("# AISC v16 candidate-generation recall audit\n")
        lines.append(
            f"`generate_candidates_v3` (limit={CANDIDATE_LIMIT}), catalog = "
            f"`{CATALOG_PATH.name}` ({len(entries)} entries, {len(catalog.families())} families), "
            f"one corrupted query per (label × single-corruption-family), seed={SEED}.\n"
        )
        lines.append(f"\n**Overall candidate recall: {overall_recall:.4f} ({hits}/{total_checks})**\n")

        lines.append("\n## Recall by catalog scope\n")
        lines.append("| Scope | Recall | Checks |\n|---|---|---|\n")
        for scope, (h, c) in sorted(by_scope.items()):
            lines.append(f"| {scope} | {h / c:.4f} | {c} |\n")

        lines.append("\n## Recall by corruption type\n")
        lines.append("| Corruption | Recall | Checks |\n|---|---|---|\n")
        for name, (h, c) in sorted(by_corruption.items()):
            lines.append(f"| {name} | {h / c:.4f} | {c} |\n")

        lines.append("\n## Recall by family\n")
        lines.append("| Family | Recall | Checks |\n|---|---|---|\n")
        for family, (h, c) in sorted(by_family.items(), key=lambda kv: -kv[1][1]):
            lines.append(f"| {family} | {h / c:.4f} | {c} |\n")

        if misses_sample:
            lines.append("\n## Sample misses (true label never appeared in candidates)\n")
            for family, label, corruption_name, corrupted_text in misses_sample:
                lines.append(f"- `{family}` / `{label}` --[{corruption_name}]--> `{corrupted_text}`\n")

        OUT_REPORT.write_text("".join(lines), encoding="utf-8")
        print(f"overall recall: {overall_recall:.4f} ({hits}/{total_checks})")
        print(f"report: {OUT_REPORT}")
    finally:
        database_loader.reset_to_default()
        refresh_all_dependent_caches()


if __name__ == "__main__":
    main()
