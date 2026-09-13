"""Sections 19-29 -- Model A (change-decision), Model B (LightGBM ranker),
confidence policy, and the mandatory clean/corrupted/mixed-prevalence
evaluations.

Usage:
    python train_repair_policy.py --v1 <v1 dir> --v2 <v2 dir> --output <v2 dir> [--debug]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import precision_recall_fscore_support  # noqa: E402

from scripts.corpus import candidate_retrieval as cr  # noqa: E402
from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402
from scripts.corpus.repair_features import (  # noqa: E402
    FEATURE_ORDER_A, FEATURE_ORDER_B, FEATURE_ORDER_B_NO_CONTEXT,
    annotation_features, deterministic_keep, featurize_a, featurize_b,
    pair_features,
)

ACTIONS = ["KEEP", "REPAIR_CANDIDATE", "REVIEW"]
ACTION_TO_IDX = {a: i for i, a in enumerate(ACTIONS)}
SEED = 20260912
RETRIEVAL_K = 20
AMBIGUITY_SCORE_THRESHOLD = 88.0
AMBIGUITY_MIN_ALTERNATIVES = 2


def build_catalog(v1_dir: Path) -> dict[str, list[str]]:
    by_family: dict[str, set[str]] = {}
    for row in read_jsonl(v1_dir / "clean" / "annotations.jsonl"):
        by_family.setdefault(row["family"], set()).add(row["canonical_text"])
    return {fam: sorted(vals) for fam, vals in by_family.items()}


def load_identity(v2_dir: Path) -> list[dict]:
    return list(read_jsonl(v2_dir / "clean" / "identity_examples.jsonl"))


def load_hard_negatives(v2_dir: Path) -> list[dict]:
    return list(read_jsonl(v2_dir / "clean" / "hard_clean_negatives.jsonl"))


def load_repair_pairs(v1_dir: Path) -> list[dict]:
    rows = []
    for row in read_jsonl(v1_dir / "synthetic" / "repair_pairs.jsonl"):
        rows.append({
            "example_id": row["example_id"],
            "split": row["split"],
            "input": row["corrupted"]["text"],
            "target": row["clean"]["canonical_text"],
            "family": row["clean"]["family"],
            "category": row["category"],
            "difficulty": row["difficulty"],
            "source": row["source"],
        })
    return rows


AMBIGUITY_MARGIN_THRESHOLD = 3.0


def is_ambiguous(corrupted_text: str, target: str, family_pool: list[str]) -> bool:
    """A corruption is genuinely AMBIGUOUS (Section 17) when the CORRUPTED
    TEXT ITSELF -- not the target's general catalog neighborhood -- is
    nearly equally close to >=2 distinct catalog candidates (e.g. "W10X3"
    is a near-tie between W10X30/W10X33/W10X39). Using the target's own
    neighborhood instead (an earlier bug) flagged ~99% of all repairs as
    ambiguous, because dense families like W have many similar designations
    regardless of whether THIS corruption actually erased the
    disambiguating information."""
    from rapidfuzz import fuzz
    scored = sorted(((c, fuzz.ratio(corrupted_text, c)) for c in family_pool), key=lambda t: -t[1])
    if not scored:
        return False
    top1_score = scored[0][1]
    if top1_score < AMBIGUITY_SCORE_THRESHOLD:
        return False
    near_tied = [c for c, s in scored if (top1_score - s) <= AMBIGUITY_MARGIN_THRESHOLD]
    return len(near_tied) >= AMBIGUITY_MIN_ALTERNATIVES


def build_model_a_rows(identity, hard_neg, repair, catalog, debug=False):
    if debug:
        rng = random.Random(SEED)
        identity = rng.sample(identity, min(1500, len(identity)))
        hard_neg = rng.sample(hard_neg, min(1500, len(hard_neg)))
    rows = []
    # Identity (KEEP). Hard negatives duplicated once more for oversampling
    # per Section 10 -- but see report: nearly the whole clean set already
    # qualifies as "hard" for this catalog family mix, so oversampling has
    # limited additional effect; kept anyway per spec instruction.
    for src, weight in ((identity, 1), (hard_neg, 1)):
        for row in src:
            for _ in range(weight):
                rows.append({**row, "action": "KEEP"})
    for row in repair:
        pool = catalog.get(row["family"], [])
        ambiguous = is_ambiguous(row["input"], row["target"], pool)
        action = "REVIEW" if ambiguous else "REPAIR_CANDIDATE"
        rows.append({**row, "action": action, "ambiguous": ambiguous})
    return rows


def train_model_a(rows, catalog):
    train_rows = [r for r in rows if r["split"] == "train"]
    val_rows = [r for r in rows if r["split"] == "validation"]
    test_rows = [r for r in rows if r["split"] == "test"]

    def to_xy(subset):
        X, y = [], []
        for r in subset:
            pool = catalog.get(r["family"], [])
            feat = annotation_features(r["input"], pool)
            X.append(featurize_a(feat))
            y.append(ACTION_TO_IDX[r["action"]])
        return np.array(X, dtype=float), np.array(y, dtype=int)

    X_train, y_train = to_xy(train_rows)
    X_val, y_val = to_xy(val_rows)
    X_test, y_test = to_xy(test_rows)

    model = lgb.LGBMClassifier(
        objective="multiclass", num_class=3, n_estimators=300,
        learning_rate=0.05, max_depth=6, random_state=SEED,
        class_weight="balanced", verbosity=-1,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )

    def evaluate(X, y, rows_subset, name):
        pred = model.predict(X)
        precision, recall, f1, _ = precision_recall_fscore_support(
            y, pred, labels=[0, 1, 2], zero_division=0,
        )
        clean_mask = y == ACTION_TO_IDX["KEEP"]
        clean_change_rate = float(np.mean(pred[clean_mask] != ACTION_TO_IDX["KEEP"])) if clean_mask.any() else None
        return {
            "n": len(y),
            "class_distribution": dict(Counter(ACTIONS[i] for i in y)),
            "precision": dict(zip(ACTIONS, precision.tolist())),
            "recall": dict(zip(ACTIONS, recall.tolist())),
            "f1": dict(zip(ACTIONS, f1.tolist())),
            "clean_change_rate": clean_change_rate,
        }

    metrics = {
        "train": evaluate(X_train, y_train, train_rows, "train"),
        "validation": evaluate(X_val, y_val, val_rows, "validation"),
        "test": evaluate(X_test, y_test, test_rows, "test"),
    }
    return model, metrics


def doc_frequency_index(identity_rows) -> dict[tuple, Counter]:
    idx: dict[tuple, Counter] = defaultdict(Counter)
    for row in identity_rows:
        if row["split"] != "train":
            continue
        key = (row["source"]["document_sha256"], row["family"])
        idx[key][row["target"]] += 1
    return idx


def build_ranker_groups(repair_rows, catalog, doc_freq_idx, tfidf_fn, *, with_context: bool, limit=None):
    X, y, groups, meta = [], [], [], []
    for row in (repair_rows[:limit] if limit else repair_rows):
        pool = catalog.get(row["family"], [])
        if not pool:
            continue
        per_method = cr.union_retrieve(row["input"], pool, RETRIEVAL_K, tfidf_fn)
        union_candidates = list(dict.fromkeys(c for lst in per_method.values() for c in lst))
        if row["target"] not in union_candidates:
            union_candidates.append(row["target"])  # ensure a positive exists to learn from
        if len(union_candidates) < 2:
            continue
        key = (row["source"]["document_sha256"], row["family"])
        freq_counter = doc_freq_idx.get(key, Counter())
        group_size = 0
        for cand in union_candidates:
            feat = pair_features(row["input"], cand, doc_freq=freq_counter.get(cand, 0))
            X.append(featurize_b(feat, with_context=with_context))
            y.append(1 if cand == row["target"] else 0)
            group_size += 1
        groups.append(group_size)
        meta.append({"example_id": row["example_id"], "candidates": union_candidates, "target": row["target"]})
    return np.array(X, dtype=float), np.array(y, dtype=int), groups, meta


def train_model_b(repair_rows, catalog, doc_freq_idx, tfidf_fn, *, with_context: bool, limit=None):
    train_rows = [r for r in repair_rows if r["split"] == "train"]
    val_rows = [r for r in repair_rows if r["split"] == "validation"]
    test_rows = [r for r in repair_rows if r["split"] == "test"]

    Xtr, ytr, gtr, _ = build_ranker_groups(train_rows, catalog, doc_freq_idx, tfidf_fn, with_context=with_context, limit=limit)
    Xva, yva, gva, meta_va = build_ranker_groups(val_rows, catalog, doc_freq_idx, tfidf_fn, with_context=with_context, limit=limit)
    Xte, yte, gte, meta_te = build_ranker_groups(test_rows, catalog, doc_freq_idx, tfidf_fn, with_context=with_context, limit=limit)

    model = lgb.LGBMRanker(
        objective="lambdarank", n_estimators=200, learning_rate=0.05,
        max_depth=6, random_state=SEED, verbosity=-1,
    )
    model.fit(
        Xtr, ytr, group=gtr,
        eval_set=[(Xva, yva)], eval_group=[gva],
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )

    def topk_metrics(X, groups, meta):
        scores = model.predict(X)
        idx = 0
        top1 = top3 = 0
        rr_sum = 0.0
        n = len(groups)
        for g, m in zip(groups, meta):
            group_scores = scores[idx:idx + g]
            order = np.argsort(-group_scores)
            ranked = [m["candidates"][i] for i in order]
            rank = ranked.index(m["target"]) if m["target"] in ranked else None
            if rank is not None:
                if rank == 0:
                    top1 += 1
                if rank < 3:
                    top3 += 1
                rr_sum += 1.0 / (rank + 1)
            idx += g
        return {
            "n": n, "top1": top1 / n if n else None, "top3": top3 / n if n else None,
            "mrr": rr_sum / n if n else None,
        }

    metrics = {
        "validation": topk_metrics(Xva, gva, meta_va),
        "test": topk_metrics(Xte, gte, meta_te),
    }
    return model, metrics, (Xte, yte, gte, meta_te)


def score_candidates(model_b, query, candidates, doc_freq_idx, doc_key, tfidf_fn, with_context=True):
    freq_counter = doc_freq_idx.get(doc_key, Counter()) if with_context else Counter()
    feats = [featurize_b(pair_features(query, c, doc_freq=freq_counter.get(c, 0)), with_context=with_context) for c in candidates]
    if not feats:
        return []
    scores = model_b.predict(np.array(feats, dtype=float))
    ranked = sorted(zip(candidates, scores), key=lambda t: -t[1])
    return ranked


def full_policy(text, family, catalog, model_a, model_b, tfidf_fn, doc_freq_idx, doc_key, auto_thresh, margin_thresh):
    pool = catalog.get(family, [])
    if deterministic_keep(text):
        return {"action": "KEEP", "output": text, "reason": "deterministic_short_circuit"}

    feat = annotation_features(text, pool)
    proba = model_a.predict_proba([featurize_a(feat)])[0]
    a_action = ACTIONS[int(np.argmax(proba))]

    if not pool:
        return {"action": "ABSTAIN", "output": text, "reason": "unknown_family"}

    per_method = cr.union_retrieve(text, pool, RETRIEVAL_K, tfidf_fn)
    candidates = list(dict.fromkeys(c for lst in per_method.values() for c in lst))
    if not candidates:
        return {"action": "ABSTAIN", "output": text, "reason": "no_candidates_retrieved"}

    ranked = score_candidates(model_b, text, candidates, doc_freq_idx, doc_key, tfidf_fn)
    top1, top1_score = ranked[0]
    top2_score = ranked[1][1] if len(ranked) > 1 else -1e9
    margin = top1_score - top2_score

    if a_action == "REVIEW":
        return {"action": "NEEDS_REVIEW", "output": text, "reason": "model_a_review", "top1_candidate": top1}

    if top1_score >= auto_thresh and margin >= margin_thresh:
        return {"action": "AUTO_REPAIR", "output": top1, "reason": "high_confidence", "score": float(top1_score), "margin": float(margin)}
    if top1_score >= (auto_thresh - 2.0):
        return {"action": "NEEDS_REVIEW", "output": text, "reason": "plausible_but_below_threshold", "top1_candidate": top1, "score": float(top1_score)}
    return {"action": "ABSTAIN", "output": text, "reason": "low_confidence", "score": float(top1_score)}


def calibrate_thresholds(model_b, val_repair_rows, catalog, doc_freq_idx, tfidf_fn):
    """Sweep top1-score thresholds AND top1-top2 margin thresholds jointly on
    the VALIDATION split only; test split stays untouched until thresholds
    are frozen (Section 23's split discipline).

    Margin is on the raw LGBMRanker score scale, which is unbounded and has
    no fixed meaning across models -- an earlier version hard-coded
    margin>=3.0 and it silently zeroed out AUTO_REPAIR coverage because
    typical margins on this model are much smaller. Margin candidates are
    therefore derived from the observed margin DISTRIBUTION, not a constant.
    """
    records = []
    for row in val_repair_rows:
        pool = catalog.get(row["family"], [])
        if not pool:
            continue
        per_method = cr.union_retrieve(row["input"], pool, RETRIEVAL_K, tfidf_fn)
        candidates = list(dict.fromkeys(c for lst in per_method.values() for c in lst))
        if not candidates:
            continue
        key = (row["source"]["document_sha256"], row["family"])
        ranked = score_candidates(model_b, row["input"], candidates, doc_freq_idx, key, tfidf_fn)
        top1, top1_score = ranked[0]
        top2_score = ranked[1][1] if len(ranked) > 1 else top1_score
        records.append({
            "correct": top1 == row["target"], "score": float(top1_score),
            "margin": float(top1_score - top2_score),
        })

    if not records:
        return [], {}, 0.0

    score_candidates_list = sorted({round(r["score"], 2) for r in records}, reverse=True)
    margins = sorted({round(r["margin"], 4) for r in records})
    margin_candidates_list = [0.0] + [
        margins[i] for i in (len(margins) // 4, len(margins) // 2, (3 * len(margins)) // 4) if margins
    ] if margins else [0.0]
    margin_candidates_list = sorted(set(margin_candidates_list))

    sweep = []
    for s_t in score_candidates_list:
        for m_t in margin_candidates_list:
            accepted = [r for r in records if r["score"] >= s_t and r["margin"] >= m_t]
            if not accepted:
                continue
            precision = sum(r["correct"] for r in accepted) / len(accepted)
            coverage = len(accepted) / len(records)
            sweep.append({
                "threshold": s_t, "margin_threshold": m_t, "precision": precision,
                "coverage": coverage, "n_accepted": len(accepted),
            })

    targets = {}
    for target_precision in (0.99, 0.995, 0.998, 0.999):
        best = None
        for pt in sweep:
            if pt["precision"] >= target_precision:
                if best is None or pt["coverage"] > best["coverage"]:
                    best = pt
        targets[str(target_precision)] = best
    max_precision = max((pt["precision"] for pt in sweep), default=0.0)
    # Sort so sweep[0] is a sane single fallback pick (highest precision,
    # tie-broken by coverage) if no target precision is reachable at all.
    sweep.sort(key=lambda pt: (-pt["precision"], -pt["coverage"]))
    return sweep, targets, max_precision


def eval_clean_test(identity_test, hard_neg_test, catalog, model_a, model_b, tfidf_fn, doc_freq_idx, tfidf_fn2, auto_thresh, margin_thresh):
    results = Counter()
    wrong_changes = []
    pool_cache = catalog
    combined = identity_test + [r for r in hard_neg_test if r not in identity_test]
    seen = set()
    rows = []
    for r in combined:
        if r["example_id"] in seen:
            continue
        seen.add(r["example_id"])
        rows.append(r)
    for row in rows:
        key = (row["source"]["document_sha256"], row["family"])
        decision = full_policy(row["input"], row["family"], pool_cache, model_a, model_b, tfidf_fn, doc_freq_idx, key, auto_thresh, margin_thresh)
        results[decision["action"]] += 1
        if decision["action"] == "AUTO_REPAIR" and decision["output"] != row["target"]:
            wrong_changes.append({
                "input": row["input"], "proposed": decision["output"], "family": row["family"],
                "score": decision.get("score"), "project": row["source"]["project_id"], "page": row["source"].get("page"),
            })
    n = len(rows)
    keep_accuracy = results["KEEP"] / n if n else None
    wrong_repair_rate = len(wrong_changes) / n if n else None
    return {
        "n": n, "action_counts": dict(results), "keep_accuracy": keep_accuracy,
        "wrong_repair_rate": wrong_repair_rate, "review_rate": results["NEEDS_REVIEW"] / n if n else None,
        "abstain_rate": results["ABSTAIN"] / n if n else None,
    }, wrong_changes


def eval_corrupted_test(repair_test, catalog, model_a, model_b, tfidf_fn, doc_freq_idx, auto_thresh, margin_thresh):
    by_cat = defaultdict(list)
    by_diff = defaultdict(list)
    all_records = []
    for row in repair_test:
        key = (row["source"]["document_sha256"], row["family"])
        decision = full_policy(row["input"], row["family"], catalog, model_a, model_b, tfidf_fn, doc_freq_idx, key, auto_thresh, margin_thresh)
        correct_auto = decision["action"] == "AUTO_REPAIR" and decision["output"] == row["target"]
        wrong_auto = decision["action"] == "AUTO_REPAIR" and decision["output"] != row["target"]
        rec = {"category": row["category"], "difficulty": row["difficulty"], "action": decision["action"],
               "correct_auto": correct_auto, "wrong_auto": wrong_auto}
        all_records.append(rec)
        by_cat[row["category"]].append(rec)
        by_diff[row["difficulty"]].append(rec)

    def summarize(records):
        n = len(records)
        auto = [r for r in records if r["action"] == "AUTO_REPAIR"]
        return {
            "n": n,
            "auto_repair_coverage": len(auto) / n if n else None,
            "auto_repair_precision": (sum(r["correct_auto"] for r in auto) / len(auto)) if auto else None,
            "review_rate": sum(r["action"] == "NEEDS_REVIEW" for r in records) / n if n else None,
            "abstain_rate": sum(r["action"] == "ABSTAIN" for r in records) / n if n else None,
        }

    return {
        "overall": summarize(all_records),
        "by_category": {k: summarize(v) for k, v in by_cat.items()},
        "by_difficulty": {str(k): summarize(v) for k, v in by_diff.items()},
    }


def build_mixed_prevalence_sets(identity_test, repair_test, prevalence, rng):
    n_clean_pool = len(identity_test)
    n_corrupt = int(n_clean_pool * prevalence / (1 - prevalence)) if prevalence < 1 else len(repair_test)
    n_corrupt = min(n_corrupt, len(repair_test))
    corrupt_sample = rng.sample(repair_test, n_corrupt) if n_corrupt else []
    return identity_test, corrupt_sample


def eval_mixed_prevalence(identity_test, repair_test, catalog, model_a, model_b, tfidf_fn, doc_freq_idx, auto_thresh, margin_thresh):
    rng = random.Random(SEED)
    report = {}
    for prevalence in (0.01, 0.05, 0.10, 0.20):
        clean_rows, corrupt_rows = build_mixed_prevalence_sets(identity_test, repair_test, prevalence, rng)
        true_repairs = false_repairs = clean_wrongly_changed = review_ct = abstain_ct = 0
        for row in clean_rows:
            key = (row["source"]["document_sha256"], row["family"])
            d = full_policy(row["input"], row["family"], catalog, model_a, model_b, tfidf_fn, doc_freq_idx, key, auto_thresh, margin_thresh)
            if d["action"] == "AUTO_REPAIR":
                clean_wrongly_changed += 1
            elif d["action"] == "NEEDS_REVIEW":
                review_ct += 1
            elif d["action"] == "ABSTAIN":
                abstain_ct += 1
        for row in corrupt_rows:
            key = (row["source"]["document_sha256"], row["family"])
            d = full_policy(row["input"], row["family"], catalog, model_a, model_b, tfidf_fn, doc_freq_idx, key, auto_thresh, margin_thresh)
            if d["action"] == "AUTO_REPAIR":
                if d["output"] == row["target"]:
                    true_repairs += 1
                else:
                    false_repairs += 1
            elif d["action"] == "NEEDS_REVIEW":
                review_ct += 1
            elif d["action"] == "ABSTAIN":
                abstain_ct += 1
        report[str(prevalence)] = {
            "n_clean": len(clean_rows), "n_corrupt": len(corrupt_rows),
            "true_repairs": true_repairs, "false_repairs": false_repairs,
            "clean_labels_wrongly_changed": clean_wrongly_changed,
            "review_count": review_ct, "abstain_count": abstain_ct,
            "note": "SYNTHETIC sensitivity scenario, not a real prevalence claim",
        }
    return report


def git_commit_hash(repo_dir: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1", required=True, type=Path)
    parser.add_argument("--v2", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    from services.exact_section_predictor import predict_exact_sections

    print("Loading data...")
    catalog = build_catalog(args.v1)
    identity = load_identity(args.v2)
    hard_neg = load_hard_negatives(args.v2)
    repair = load_repair_pairs(args.v1)
    if args.debug:
        repair = random.Random(SEED).sample(repair, min(3000, len(repair)))
    print(f"catalog families={len(catalog)} identity={len(identity)} hard_neg={len(hard_neg)} repair={len(repair)}")

    print("Building Model A dataset (incl. ambiguity labeling)...")
    a_rows = build_model_a_rows(identity, hard_neg, repair, catalog, debug=args.debug)
    print(f"Model A rows: {len(a_rows)}; action dist: {Counter(r['action'] for r in a_rows)}")

    print("Training Model A...")
    model_a, metrics_a = train_model_a(a_rows, catalog)
    print(json.dumps(metrics_a, indent=2)[:2000])

    print("Building doc-frequency index...")
    doc_freq_idx = doc_frequency_index(identity)

    print("Training Model B (with context)...")
    limit = 1500 if args.debug else None
    model_b, metrics_b, test_bundle = train_model_b(repair, catalog, doc_freq_idx, predict_exact_sections, with_context=True, limit=limit)
    print(json.dumps(metrics_b, indent=2))

    print("Training Model B ablation (no context)...")
    model_b_noctx, metrics_b_noctx, _ = train_model_b(repair, catalog, doc_freq_idx, predict_exact_sections, with_context=False, limit=limit)
    print(json.dumps(metrics_b_noctx, indent=2))

    print("Calibrating thresholds on validation split...")
    val_repair = [r for r in repair if r["split"] == "validation"]
    sweep, risk_coverage_targets, max_precision = calibrate_thresholds(model_b, val_repair, catalog, doc_freq_idx, predict_exact_sections)
    print("max achievable precision on validation:", max_precision)
    print(json.dumps(risk_coverage_targets, indent=2, default=str)[:2000])

    # Pick operating point: highest coverage achieving >=99% precision if any,
    # else the single highest-precision point available (documented honestly).
    chosen = risk_coverage_targets.get("0.99") or (sweep[0] if sweep else None)
    auto_thresh = chosen["threshold"] if chosen else 100.0
    margin_thresh = chosen["margin_threshold"] if chosen else 0.0

    print(f"Operating point: score>={auto_thresh}, margin>={margin_thresh}")

    identity_test = [r for r in identity if r["split"] == "test"]
    hard_neg_test = [r for r in hard_neg if r["split"] == "test"]
    repair_test = [r for r in repair if r["split"] == "test"]

    print("Evaluating clean test set...")
    clean_results, wrong_changes = eval_clean_test(identity_test, hard_neg_test, catalog, model_a, model_b, predict_exact_sections, doc_freq_idx, predict_exact_sections, auto_thresh, margin_thresh)
    print(json.dumps(clean_results, indent=2))

    print("Evaluating corrupted test set...")
    corrupted_results = eval_corrupted_test(repair_test, catalog, model_a, model_b, predict_exact_sections, doc_freq_idx, auto_thresh, margin_thresh)
    print(json.dumps(corrupted_results, indent=2)[:3000])

    print("Evaluating mixed prevalence...")
    mixed_results = eval_mixed_prevalence(identity_test, repair_test, catalog, model_a, model_b, predict_exact_sections, doc_freq_idx, auto_thresh, margin_thresh)
    print(json.dumps(mixed_results, indent=2))

    print("Saving artifacts...")
    models_dir = Path(__file__).resolve().parent / "_models"
    models_dir.mkdir(exist_ok=True)
    import joblib
    joblib.dump(model_a, models_dir / "model_a_change_decision.joblib")
    joblib.dump(model_b, models_dir / "model_b_ranker.joblib")

    manifest_hash = hashlib.sha256((args.v2 / "manifest.json").read_bytes()).hexdigest() if (args.v2 / "manifest.json").exists() else None

    train_projects = (args.v2 / "splits" / "train_projects.txt").read_text().splitlines()
    val_projects = (args.v2 / "splits" / "validation_projects.txt").read_text().splitlines()
    test_projects = (args.v2 / "splits" / "test_projects.txt").read_text().splitlines()

    artifact_meta = {
        "model_a": {
            "type": "LGBMClassifier(multiclass)", "version": "repair_policy_v2.model_a.1",
            "git_commit": git_commit_hash(Path(__file__).resolve().parents[2]),
            "dataset_manifest_sha256": manifest_hash,
            "train_projects": train_projects, "validation_projects": val_projects, "test_projects": test_projects,
            "feature_schema": FEATURE_ORDER_A, "random_seed": SEED, "metrics": metrics_a,
        },
        "model_b": {
            "type": "LGBMRanker(lambdarank)", "version": "repair_policy_v2.model_b.1",
            "git_commit": git_commit_hash(Path(__file__).resolve().parents[2]),
            "dataset_manifest_sha256": manifest_hash,
            "train_projects": train_projects, "validation_projects": val_projects, "test_projects": test_projects,
            "feature_schema": FEATURE_ORDER_B, "feature_schema_no_context": FEATURE_ORDER_B_NO_CONTEXT,
            "random_seed": SEED, "metrics_with_context": metrics_b, "metrics_no_context": metrics_b_noctx,
        },
        "policy": {"auto_thresh": auto_thresh, "margin_thresh": margin_thresh, "max_precision_on_validation": max_precision},
    }
    write_json(models_dir / "artifact_metadata.json", artifact_meta)

    write_json(args.output / "reports" / "model_a_metrics.json", metrics_a)
    write_json(args.output / "reports" / "model_b_metrics.json", {"with_context": metrics_b, "no_context": metrics_b_noctx})
    write_json(args.output / "reports" / "risk_coverage.json", {"sweep": sweep, "targets": risk_coverage_targets, "max_precision": max_precision})
    write_json(args.output / "reports" / "clean_test_results.json", clean_results)
    write_json(args.output / "reports" / "corrupted_test_results.json", corrupted_results)
    write_json(args.output / "reports" / "mixed_prevalence_results.json", mixed_results)
    write_jsonl(args.output / "reports" / "clean_false_changes.jsonl", wrong_changes)

    print("DONE.")
    print(f"Wrong clean changes found: {len(wrong_changes)}")


if __name__ == "__main__":
    main()
