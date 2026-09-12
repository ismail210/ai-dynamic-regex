"""Repair benchmark: current pipeline, RapidFuzz edit-distance, existing
char-TF-IDF retriever -- evaluated strictly on the TEST split (Section 19-21,
23).

DO NOT use final Excel quantities as ground truth or as a feature (Section
34) -- ground truth here is the synthetic corruption's own recorded clean
label, which is the only correct notion of "ground truth" for a controlled
repair benchmark.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rapidfuzz import fuzz, process  # noqa: E402

from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402
from services.exact_section_predictor import predict_exact_sections  # noqa: E402
from services.semantic_preprocessor.normalization import canonicalize  # noqa: E402
from services.semantic_preprocessor.structural_parser import parse_structural_label  # noqa: E402


def load_test_rows(out_dir: Path) -> list[dict]:
    rows = [r for r in read_jsonl(out_dir / "synthetic" / "repair_pairs.jsonl") if r["split"] == "test"]
    return rows


def build_catalog(out_dir: Path) -> dict[str, list[str]]:
    """Family -> list of unique canonical designations seen in the CLEAN
    seed corpus (a project-agnostic, catalog-scale set -- Section 34 this is
    domain knowledge, not a project-specific leak, since designations are
    shared AISC shapes, not project-local abbreviations)."""
    by_family: dict[str, set[str]] = {}
    for row in read_jsonl(out_dir / "clean" / "annotations.jsonl"):
        by_family.setdefault(row["family"], set()).add(row["canonical_text"])
    return {fam: sorted(vals) for fam, vals in by_family.items()}


def baseline_current_pipeline(rows: list[dict]) -> list[dict]:
    results = []
    for row in rows:
        clean = row["clean"]["canonical_text"]
        corrupted = row["corrupted"]["text"]
        result = canonicalize(corrupted)
        proposed = result.correction.canonical if result.correction.operation == "repair" else None
        results.append({
            "example_id": row["example_id"], "family": row["clean"]["family"],
            "category": row["category"], "difficulty": row["difficulty"],
            "clean": clean, "corrupted": corrupted,
            "top1": proposed, "correct": proposed == clean if proposed else False,
            "abstained": proposed is None,
            "score": None,  # current pipeline's repair path is uncalibrated by design
        })
    return results


def baseline_rapidfuzz(rows: list[dict], catalog: dict[str, list[str]]) -> list[dict]:
    results = []
    for row in rows:
        clean = row["clean"]["canonical_text"]
        corrupted = row["corrupted"]["text"]
        family = row["clean"]["family"]
        pool = catalog.get(family, [])
        if not pool:
            results.append({"example_id": row["example_id"], "family": family, "category": row["category"],
                             "difficulty": row["difficulty"], "clean": clean, "corrupted": corrupted,
                             "ranked": [], "top1": None, "score": None})
            continue
        matches = process.extract(corrupted, pool, scorer=fuzz.ratio, limit=5)
        ranked = [m[0] for m in matches]
        results.append({
            "example_id": row["example_id"], "family": family, "category": row["category"],
            "difficulty": row["difficulty"], "clean": clean, "corrupted": corrupted,
            "ranked": ranked, "top1": ranked[0] if ranked else None,
            "score": matches[0][1] / 100.0 if matches else None,
        })
    return results


def baseline_tfidf(rows: list[dict]) -> list[dict]:
    results = []
    for row in rows:
        clean = row["clean"]["canonical_text"]
        corrupted = row["corrupted"]["text"]
        candidates = predict_exact_sections(corrupted, limit=5)
        ranked = [c.shape for c in candidates]
        results.append({
            "example_id": row["example_id"], "family": row["clean"]["family"], "category": row["category"],
            "difficulty": row["difficulty"], "clean": clean, "corrupted": corrupted,
            "ranked": ranked, "top1": ranked[0] if ranked else None,
            "score": candidates[0].confidence if candidates else None,
        })
    return results


def topk_and_mrr(results: list[dict], k_values=(1, 3, 5)) -> dict:
    n = len(results)
    if n == 0:
        return {}
    metrics = {f"top{k}": 0 for k in k_values}
    reciprocal_ranks = []
    for r in results:
        ranked = r.get("ranked") or ([r["top1"]] if r.get("top1") else [])
        rank = None
        for i, cand in enumerate(ranked):
            if cand == r["clean"]:
                rank = i + 1
                break
        for k in k_values:
            if rank is not None and rank <= k:
                metrics[f"top{k}"] += 1
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
    out = {f"top{k}": round(metrics[f"top{k}"] / n, 4) for k in k_values}
    out["mrr"] = round(sum(reciprocal_ranks) / n, 4)
    out["n"] = n
    return out


def risk_coverage(results: list[dict], thresholds=(0.5, 0.6, 0.7, 0.8, 0.9)) -> list[dict]:
    scored = [r for r in results if r.get("score") is not None]
    if not scored:
        return []
    curve = []
    for t in thresholds:
        accepted = [r for r in scored if r["score"] >= t]
        if not accepted:
            curve.append({"threshold": t, "coverage": 0.0, "precision": None, "n_accepted": 0})
            continue
        correct = sum(1 for r in accepted if r.get("top1") == r["clean"])
        curve.append({
            "threshold": t,
            "coverage": round(len(accepted) / len(scored), 4),
            "precision": round(correct / len(accepted), 4),
            "false_correction_rate": round(1 - correct / len(accepted), 4),
            "n_accepted": len(accepted),
        })
    return curve


def breakdown(results: list[dict], key: str) -> dict:
    groups: dict = {}
    for r in results:
        groups.setdefault(r[key], []).append(r)
    return {str(k): topk_and_mrr(v) for k, v in groups.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    out_dir: Path = args.output
    test_rows = load_test_rows(out_dir)
    catalog = build_catalog(out_dir)

    print(f"Test repair pairs: {len(test_rows)}")

    baselines = {
        "current_pipeline": baseline_current_pipeline(test_rows),
        "rapidfuzz": baseline_rapidfuzz(test_rows, catalog),
        "char_tfidf": baseline_tfidf(test_rows),
    }

    report = {}
    for name, results in baselines.items():
        write_jsonl(out_dir / "inventory" / f"repair_benchmark_{name}.jsonl", results)
        abstained = sum(1 for r in results if r.get("abstained") or r.get("top1") is None)
        proposed = [r for r in results if not (r.get("abstained") or r.get("top1") is None)]
        false_corrections = sum(1 for r in proposed if r.get("top1") != r["clean"])
        report[name] = {
            "overall": topk_and_mrr(results),
            "by_family": breakdown(results, "family"),
            "by_category": breakdown(results, "category"),
            "by_difficulty": breakdown(results, "difficulty"),
            "abstention_rate": round(abstained / len(results), 4) if results else None,
            "proposed_count": len(proposed),
            "false_correction_rate_among_proposed": round(false_corrections / len(proposed), 4) if proposed else None,
            "risk_coverage": risk_coverage(results),
        }

    write_json(out_dir / "reports" / "repair_benchmark_data.json", report)
    import json
    print(json.dumps({k: v["overall"] for k, v in report.items()}, indent=2))
    print(json.dumps({k: {"abstention_rate": v["abstention_rate"], "false_correction_rate_among_proposed": v["false_correction_rate_among_proposed"]} for k, v in report.items()}, indent=2))


if __name__ == "__main__":
    main()
