#!/usr/bin/env python3
"""Offline Graph v2 A/B/C/D ablation on cached predictions.

Does NOT modify production predictions, flags, or pipeline wiring.

Run from backend/:
  python scripts/evaluate_graph_v2.py

Outputs under training/eval_cache_backups/graph_v2_phase5/
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.engineering.graph_v2_scorer import (  # noqa: E402
    apply_safety_gates,
    build_graph_context,
    family_of,
    index_graph,
    is_explicit_complete_section,
    is_incomplete_angle,
    proxy_gold_section,
    score_candidates,
)
from services.token_extractor import (  # noqa: E402
    core_section_token,
    normalize_engineering_token,
)

CACHE_ROOT = BACKEND_DIR / "training" / "eval_cache_backups"
ARTIFACTS_ROOT = BACKEND_DIR / "training" / "engineering_artifacts"
OUT_DIR = CACHE_ROOT / "graph_v2_phase5"

TEXT_W = 1.0
GEO_W = 0.25
GRAPH_V2_W = 0.35


def _load_predictions(doc_id: str) -> List[Dict[str, Any]]:
    path = CACHE_ROOT / doc_id / "predictions_view.json"
    if not path.exists():
        art = ARTIFACTS_ROOT / doc_id / "multimodal" / "predictions_view.json"
        path = art if art.exists() else path
    data = json.loads(path.read_text())
    return list(data.get("predictions") or [])


def _load_graph(doc_id: str) -> Optional[Dict[str, Any]]:
    path = ARTIFACTS_ROOT / doc_id / "multimodal" / "graph.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _candidate_pool(pred: Dict[str, Any]) -> List[Tuple[str, float]]:
    """Return (shape, text_score) pairs. Does not invent new shapes."""

    pool: Dict[str, float] = {}
    section = normalize_engineering_token(
        str(pred.get("section") or pred.get("section_prediction") or "")
    )
    if section:
        # Live section is treated as the text baseline top pick.
        pool[section] = max(pool.get(section, 0.0), 1.0)

    for alt in pred.get("alternatives") or []:
        shape = normalize_engineering_token(str(alt.get("shape") or ""))
        if not shape:
            continue
        score = float(alt.get("confidence") or alt.get("score") or 0.0)
        pool[shape] = max(pool.get(shape, 0.0), score)

    for item in pred.get("candidate_sections") or []:
        if isinstance(item, dict):
            shape = normalize_engineering_token(str(item.get("shape") or ""))
            score = float(item.get("confidence") or item.get("score") or 0.0)
        else:
            shape = normalize_engineering_token(str(item))
            score = 0.5
        if shape:
            pool[shape] = max(pool.get(shape, 0.0), score)

    # Sort by text score desc for stable baseline order.
    return sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))


def _geometry_score(pred: Dict[str, Any]) -> float:
    expl = pred.get("explanation") or {}
    geo_ev = expl.get("geometry_evidence") or {}
    if isinstance(geo_ev, dict) and geo_ev.get("available"):
        details = geo_ev.get("details") or {}
        sim = details.get("similarity")
        if sim is not None:
            return float(sim)
        return float(geo_ev.get("score") or 0.0)
    contrib = expl.get("contributions") or {}
    return float(contrib.get("geometry") or 0.0)


def _rank(
    pool: Sequence[Tuple[str, float]],
    *,
    geometry_score: float = 0.0,
    graph_scores: Optional[Dict[str, Dict[str, Any]]] = None,
    use_geometry: bool = False,
    use_graph_v2: bool = False,
) -> List[str]:
    scored: List[Tuple[float, str]] = []
    for shape, text_score in pool:
        total = TEXT_W * float(text_score)
        if use_geometry:
            total += GEO_W * float(geometry_score)
        if use_graph_v2 and graph_scores:
            g = graph_scores.get(shape) or {}
            total += GRAPH_V2_W * float(g.get("total_score") or 0.0)
        scored.append((total, shape))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [shape for _, shape in scored]


def _size_leg_fields(section: str) -> Optional[Tuple[str, ...]]:
    fam = family_of(section)
    if not fam:
        return None
    rest = normalize_engineering_token(section)[len(fam) :]
    parts = tuple(p for p in rest.split("X") if p)
    return parts or None


def _classify_error(gold: Optional[str], pred: str, raw: str) -> str:
    if is_incomplete_angle(raw):
        if pred:
            return "incomplete_L_completion"
        return "incomplete_abstain"
    if not gold:
        return "no_gold"
    if not pred:
        return "abstain_with_gold"
    if pred == gold:
        return "correct"
    g_fam, p_fam = family_of(gold), family_of(pred)
    if g_fam == "L" and p_fam == "2L":
        return "L_to_2L"
    if g_fam == "HSS" and p_fam == "W":
        return "HSS_to_W"
    if g_fam == "W" and p_fam == "HSS":
        return "W_to_HSS"
    g_fields, p_fields = _size_leg_fields(gold), _size_leg_fields(pred)
    if g_fam == p_fam and g_fields and p_fields:
        if g_fam in {"L", "2L"} and len(g_fields) >= 3 and len(p_fields) >= 3:
            if g_fields[:2] == p_fields[:2] and g_fields[2] != p_fields[2]:
                return "thickness_error"
            if g_fields[:2] != p_fields[:2]:
                return "size_leg_error"
        if g_fam == "W" and len(g_fields) >= 2 and len(p_fields) >= 2:
            if g_fields[0] != p_fields[0] or g_fields[1] != p_fields[1]:
                return "size_leg_error"
    return "wrong_other"


def _change_class(baseline: str, variant: str, gold: Optional[str], raw: str) -> str:
    if variant == baseline:
        return "unchanged"
    if is_incomplete_angle(raw) and variant and not is_incomplete_angle(variant):
        # completed incomplete
        return "unsafe_mutation"
    if is_explicit_complete_section(raw):
        core = proxy_gold_section(raw)
        if core and baseline == core and variant != core:
            return "explicit_label_conflict"
    b_ok = bool(gold) and baseline == gold
    v_ok = bool(gold) and variant == gold
    if (not b_ok) and v_ok:
        return "wrong_to_correct"
    if b_ok and (not v_ok):
        return "correct_to_wrong"
    if (not b_ok) and (not v_ok):
        # unsafe family promotions
        if _classify_error(gold, variant, raw) in {
            "L_to_2L",
            "HSS_to_W",
            "incomplete_L_completion",
            "thickness_error",
            "size_leg_error",
        }:
            return "unsafe_mutation"
        return "wrong_to_wrong"
    return "correct_same_equivalent"


def _pick_gated(
    raw: str,
    ranked: Sequence[str],
    graph_scores: Optional[Dict[str, Dict[str, Any]]],
    *,
    apply_graph_gates: bool,
) -> Tuple[str, str]:
    if not apply_graph_gates:
        return (ranked[0] if ranked else ""), "ungated"
    gated = apply_safety_gates(
        raw_text=raw,
        ranked_candidates=ranked,
        graph_scores=graph_scores,
    )
    return str(gated.get("selected") or ""), str(gated.get("reason") or "")


def evaluate_doc(
    doc_id: str,
    graph: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []
    preds = _load_predictions(doc_id)
    graph_index = index_graph(graph)

    for pred in preds:
        raw = str(
            pred.get("raw_text")
            or pred.get("original_token")
            or pred.get("normalized_text")
            or ""
        )
        pool = _candidate_pool(pred)
        if not pool:
            continue

        # Eligible for ranking eval: has a candidate pool. Gold may be None.
        gold = proxy_gold_section(raw)
        incomplete = is_incomplete_angle(raw)
        explicit = is_explicit_complete_section(raw)

        # Skip pure non-section noise without gold and without incomplete L
        # unless live section looks structural — keep rows with structural
        # candidates only when gold or incomplete or live family known.
        live = normalize_engineering_token(
            str(pred.get("section") or pred.get("section_prediction") or "")
        )
        if not gold and not incomplete and not family_of(live) and not family_of(
            core_section_token(raw)
        ):
            # Keep only when raw itself looks like a family start.
            if not re.match(r"^(?:2L|HSS|W|WT|L|C|MC|PIPE)", core_section_token(raw)):
                continue

        geo_score = _geometry_score(pred)
        token_id = str(pred.get("object_id") or "")
        context = build_graph_context(
            prediction=pred,
            graph_index=graph_index,
            token_id=token_id,
        )
        shapes = [s for s, _ in pool]
        graph_scores = score_candidates(pred, shapes, context)

        ranked_a = _rank(pool)
        ranked_b = _rank(pool, geometry_score=geo_score, use_geometry=True)
        ranked_c = _rank(pool, graph_scores=graph_scores, use_graph_v2=True)
        ranked_d = _rank(
            pool,
            geometry_score=geo_score,
            graph_scores=graph_scores,
            use_geometry=True,
            use_graph_v2=True,
        )

        pick_a = ranked_a[0] if ranked_a else ""
        pick_b = ranked_b[0] if ranked_b else ""
        # Graph variants: gated picks for safety-aware accuracy; ungated for
        # mutation analysis. Baselines A/B stay ungated so we do not inflate
        # them by forcing printed gold.
        pick_c, reason_c = _pick_gated(
            raw, ranked_c, graph_scores, apply_graph_gates=True
        )
        pick_d, reason_d = _pick_gated(
            raw, ranked_d, graph_scores, apply_graph_gates=True
        )

        ungated_c = ranked_c[0] if ranked_c else ""
        ungated_d = ranked_d[0] if ranked_d else ""

        top_graph = graph_scores.get(ungated_c) or {}
        score_by_cand = {
            shape: float((graph_scores.get(shape) or {}).get("total_score") or 0.0)
            for shape in shapes
        }
        score_vals = list(score_by_cand.values())
        score_spread = (
            round(max(score_vals) - min(score_vals), 6) if score_vals else 0.0
        )
        graph_argmax = (
            max(score_by_cand.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if score_by_cand
            else ""
        )
        families = {family_of(s) for s in shapes}
        families.discard("")
        families.discard(None)  # type: ignore[arg-type]

        row = {
            "document_id": doc_id,
            "object_id": token_id,
            "raw_text": raw,
            "gold": gold or "",
            "incomplete": incomplete,
            "explicit": explicit,
            "live_section": live,
            "A": pick_a,
            "B": pick_b,
            "C": pick_c,
            "D": pick_d,
            "C_ungated": ungated_c,
            "D_ungated": ungated_d,
            "A_error": _classify_error(gold, pick_a, raw),
            "B_error": _classify_error(gold, pick_b, raw),
            "C_error": _classify_error(gold, pick_c, raw),
            "D_error": _classify_error(gold, pick_d, raw),
            "graph_v2_score": top_graph.get("total_score"),
            "graph_v2_confidence": top_graph.get("confidence"),
            "feature_contributions": top_graph.get("feature_contributions") or {},
            "evidence_used": top_graph.get("evidence_used") or [],
            "evidence_missing": top_graph.get("evidence_missing") or [],
            "gate_reason_C": reason_c,
            "gate_reason_D": reason_d,
            "candidates": shapes[:12],
            "graph_scores_by_candidate": score_by_cand,
            "graph_score_spread": score_spread,
            "graph_argmax": graph_argmax,
            "n_candidate_families": len(families),
            "geometry_score": geo_score,
            "takeoff_eligible": pred.get("takeoff_eligible"),
        }
        rows.append(row)

        for variant_name, variant_pick, ungated in (
            ("C", pick_c, ungated_c),
            ("D", pick_d, ungated_d),
            ("C_ungated", ungated_c, ungated_c),
            ("D_ungated", ungated_d, ungated_d),
        ):
            if variant_pick == pick_a and ungated == pick_a:
                continue
            change = _change_class(pick_a, ungated if "ungated" in variant_name else variant_pick, gold, raw)
            if change == "unchanged" and variant_pick == pick_a:
                continue
            changes.append(
                {
                    "document_id": doc_id,
                    "object_id": token_id,
                    "raw_text": raw,
                    "baseline_A": pick_a,
                    "variant": variant_name,
                    "variant_prediction": ungated
                    if "ungated" in variant_name
                    else variant_pick,
                    "gold": gold or "",
                    "candidates": "|".join(shapes[:12]),
                    "graph_score": top_graph.get("total_score"),
                    "feature_contributions": json.dumps(
                        top_graph.get("feature_contributions") or {}
                    ),
                    "evidence_used": "|".join(top_graph.get("evidence_used") or []),
                    "change_class": change,
                    "error_type": _classify_error(
                        gold,
                        ungated if "ungated" in variant_name else variant_pick,
                        raw,
                    ),
                    "gate_reason": reason_c if variant_name.startswith("C") else reason_d,
                }
            )
    return rows, changes


def _accuracy(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    eligible = [r for r in rows if r.get("gold")]
    correct = sum(1 for r in eligible if r.get(key) == r.get("gold"))
    return {
        "n_with_gold": len(eligible),
        "correct": correct,
        "accuracy": round(correct / len(eligible), 6) if eligible else None,
    }


def _count_error(rows: List[Dict[str, Any]], key: str, error: str) -> int:
    return sum(1 for r in rows if r.get(key) == error)


def _l_bucket(raw: str, gold: Optional[str], pred: str) -> Optional[str]:
    if is_incomplete_angle(raw):
        return "incomplete_L"
    if not gold or family_of(gold) not in {"L", "2L"}:
        if family_of(core_section_token(raw)) == "L":
            # L-like but incomplete already handled
            pass
        return None
    err = _classify_error(gold, pred, raw)
    if err == "correct":
        return "L_correct_explicit"
    if err == "L_to_2L":
        return "L_to_2L"
    if err in {"thickness_error", "size_leg_error"}:
        return "L_wrong_thickness_or_size"
    if family_of(gold) == "L":
        return "L_wrong_other"
    return None


def summarize(
    rows: List[Dict[str, Any]], changes: List[Dict[str, Any]]
) -> Dict[str, Any]:
    variants = ["A", "B", "C", "D"]
    overall = {v: _accuracy(rows, v) for v in variants}

    l_rows = [
        r
        for r in rows
        if is_incomplete_angle(r["raw_text"])
        or (r.get("gold") and family_of(r["gold"]) in {"L", "2L"})
        or family_of(core_section_token(r["raw_text"])) in {"L", "2L"}
    ]
    l_stats = {}
    for v in variants:
        l_stats[v] = {
            "accuracy": _accuracy(l_rows, v),
            "L_to_2L": _count_error(l_rows, f"{v}_error", "L_to_2L"),
            "thickness_error": _count_error(l_rows, f"{v}_error", "thickness_error"),
            "size_leg_error": _count_error(l_rows, f"{v}_error", "size_leg_error"),
            "incomplete_L_completion": _count_error(
                l_rows, f"{v}_error", "incomplete_L_completion"
            ),
        }

    # L bucket matrix
    buckets = [
        "L_correct_explicit",
        "L_wrong_thickness_or_size",
        "L_to_2L",
        "incomplete_L",
        "L_wrong_other",
    ]
    l_bucket_table: Dict[str, Dict[str, int]] = {
        b: {v: 0 for v in variants} for b in buckets
    }
    for r in l_rows:
        for v in variants:
            b = _l_bucket(r["raw_text"], r.get("gold") or None, r[v])
            if b:
                l_bucket_table[b][v] += 1

    hss_rows = [
        r for r in rows if r.get("gold") and family_of(r["gold"]) == "HSS"
    ]
    hss_to_w = {
        v: _count_error(hss_rows, f"{v}_error", "HSS_to_W") for v in variants
    }
    hss_to_w["C_ungated"] = sum(
        1
        for r in hss_rows
        if _classify_error(r.get("gold"), r.get("C_ungated") or "", r["raw_text"])
        == "HSS_to_W"
    )
    hss_to_w["D_ungated"] = sum(
        1
        for r in hss_rows
        if _classify_error(r.get("gold"), r.get("D_ungated") or "", r["raw_text"])
        == "HSS_to_W"
    )

    # Change analysis vs A (gated C/D and ungated)
    change_counts: Dict[str, Counter] = defaultdict(Counter)
    for ch in changes:
        change_counts[ch["variant"]][ch["change_class"]] += 1

    # Feature averages where graph changed ungated C from A
    feat_sums: Dict[str, float] = Counter()
    feat_n = 0
    feat_all_sums: Dict[str, float] = Counter()
    feat_all_n = 0
    score_spreads: List[float] = []
    for r in rows:
        feats = r.get("feature_contributions") or {}
        if feats:
            feat_all_n += 1
            for k, val in feats.items():
                feat_all_sums[k] += float(val)
        if r.get("graph_score_spread") is not None:
            score_spreads.append(float(r["graph_score_spread"]))
        if r["C_ungated"] != r["A"]:
            for k, val in feats.items():
                feat_sums[k] += float(val)
            feat_n += 1
    feat_avg = {
        k: round(v / feat_n, 6) for k, v in feat_sums.items()
    } if feat_n else {}
    feat_avg_all = {
        k: round(v / feat_all_n, 6) for k, v in feat_all_sums.items()
    } if feat_all_n else {}

    # Multi-family diagnostic: does pure graph argmax prefer gold family?
    multi = [r for r in rows if int(r.get("n_candidate_families") or 0) > 1]
    multi_with_gold = [r for r in multi if r.get("gold")]
    graph_argmax_family_correct = 0
    text_family_correct = 0
    graph_favors_w_on_hss_gold = 0
    for r in multi_with_gold:
        gold_fam = family_of(r["gold"])
        if family_of(r.get("graph_argmax") or "") == gold_fam:
            graph_argmax_family_correct += 1
        if family_of(r["A"]) == gold_fam:
            text_family_correct += 1
        if gold_fam == "HSS" and family_of(r.get("graph_argmax") or "") == "W":
            graph_favors_w_on_hss_gold += 1

    gate_reasons = Counter(str(r.get("gate_reason_C") or "") for r in rows)

    # Safety gates checks
    explicit_override_ungated = sum(
        1
        for r in rows
        if r["explicit"]
        and r["gold"]
        and r["A"] == r["gold"]
        and r["C_ungated"] != r["gold"]
    )
    explicit_override_gated = sum(
        1
        for r in rows
        if r["explicit"]
        and r["gold"]
        and r["A"] == r["gold"]
        and r["C"] != r["gold"]
    )
    # Completions newly introduced by Graph vs baseline text.
    incomplete_completed_by_graph = sum(
        1
        for r in rows
        if r["incomplete"] and r["C_ungated"] and r["C_ungated"] != r["A"]
    )
    incomplete_completed_ungated = sum(
        1
        for r in rows
        if r["incomplete"] and r["C_ungated"]
    )
    incomplete_completed_gated = sum(
        1 for r in rows if r["incomplete"] and r["C"]
    )

    takeoff_changed = sum(
        1
        for r in rows
        if r.get("takeoff_eligible") is not None
        and r["C"] != r["A"]
    )

    avg_graph_score = 0.0
    n_scores = sum(1 for r in rows if r.get("graph_v2_score") is not None)
    if n_scores:
        avg_graph_score = round(
            sum(float(r["graph_v2_score"]) for r in rows if r.get("graph_v2_score") is not None)
            / n_scores,
            6,
        )

    gates = {
        "gate1_explicit_override_gated_C": explicit_override_gated,
        "gate1_explicit_override_ungated_C": explicit_override_ungated,
        "gate2_incomplete_completed_gated_C": incomplete_completed_gated,
        "gate2_incomplete_completed_ungated_C": incomplete_completed_ungated,
        "gate2_incomplete_completed_by_graph_change": incomplete_completed_by_graph,
        "gate3_candidates_only": True,  # by construction
        "gate4_no_excel": True,  # by construction
        "gate5_unsafe_size_leg_ungated_C": change_counts["C_ungated"][
            "unsafe_mutation"
        ],
        "gate6_weak_evidence_forced_change": sum(
            1
            for r in rows
            if r.get("gate_reason_C") == "gate_weak_evidence_keep_baseline_order"
            and r["C"] != r["A"]
        ),
        "gate7_HSS_to_W": hss_to_w,
        "takeoff_eligible_field_unchanged": True,
        "prediction_changes_among_rows_with_takeoff_flag": takeoff_changed,
    }

    diagnostics = {
        "same_family_pools": sum(
            1 for r in rows if int(r.get("n_candidate_families") or 0) <= 1
        ),
        "multi_family_pools": len(multi),
        "multi_family_with_gold": len(multi_with_gold),
        "graph_argmax_family_matches_gold": graph_argmax_family_correct,
        "text_family_matches_gold_on_multi": text_family_correct,
        "graph_argmax_favors_W_on_HSS_gold": graph_favors_w_on_hss_gold,
        "mean_graph_score_spread": round(
            sum(score_spreads) / len(score_spreads), 6
        )
        if score_spreads
        else 0.0,
        "rows_with_nonzero_score_spread": sum(1 for s in score_spreads if s > 1e-9),
        "avg_graph_v2_score": avg_graph_score,
        "gate_reason_C_counts": dict(gate_reasons),
        "note": (
            "Gated C/D accuracy includes explicit-section protection and "
            "incomplete abstain; those are safety gates, not Graph v2 ranking signal. "
            "Primary Graph v2 signal = ungated C vs A and multi-family argmax diagnostics."
        ),
    }

    return {
        "n_rows": len(rows),
        "n_docs": len({r["document_id"] for r in rows}),
        "overall": overall,
        "L": l_stats,
        "L_buckets": l_bucket_table,
        "HSS_to_W": hss_to_w,
        "HSS_n_with_gold": len(hss_rows),
        "changes_vs_A": {k: dict(v) for k, v in change_counts.items()},
        "feature_avg_when_C_ungated_differs": feat_avg,
        "feature_avg_all_rows": feat_avg_all,
        "n_C_ungated_differs": feat_n,
        "gates": gates,
        "diagnostics": diagnostics,
        "changed_predictions_gated": {
            "C": sum(1 for r in rows if r["C"] != r["A"]),
            "D": sum(1 for r in rows if r["D"] != r["A"]),
        },
        "changed_predictions_ungated": {
            "C": sum(1 for r in rows if r["C_ungated"] != r["A"]),
            "D": sum(1 for r in rows if r["D_ungated"] != r["A"]),
        },
    }


def decide(summary: Dict[str, Any]) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    gates = summary["gates"]
    diag = summary.get("diagnostics") or {}
    changes_u = summary["changes_vs_A"].get("C_ungated") or {}

    wrong_to_correct = int(changes_u.get("wrong_to_correct") or 0)
    correct_to_wrong = int(changes_u.get("correct_to_wrong") or 0)
    unsafe = int(changes_u.get("unsafe_mutation") or 0)
    explicit_conflict = int(changes_u.get("explicit_label_conflict") or 0)

    hss_a = summary["HSS_to_W"]["A"]
    hss_c = summary["HSS_to_W"]["C"]
    hss_c_ungated = summary["HSS_to_W"].get("C_ungated", hss_c)

    if gates["gate1_explicit_override_gated_C"] > 0:
        reasons.append("gated Graph v2 overrode explicit labels")
    if gates["gate2_incomplete_completed_gated_C"] > 0:
        reasons.append("gated Graph v2 completed incomplete L")
    if gates.get("gate2_incomplete_completed_by_graph_change", 0) > 0:
        reasons.append("Graph ranking newly completed incomplete L vs text")
    if unsafe > 0 and wrong_to_correct <= unsafe:
        reasons.append(
            f"unsafe mutations ({unsafe}) not dominated by corrections ({wrong_to_correct})"
        )
    if explicit_conflict > 0:
        reasons.append(f"ungated explicit-label conflicts: {explicit_conflict}")
    if hss_c > hss_a:
        reasons.append(f"HSS→W increased A={hss_a} gated C={hss_c}")
    if hss_c_ungated > hss_a:
        reasons.append(
            f"HSS→W increased A={hss_a} ungated C={hss_c_ungated}"
        )
    if correct_to_wrong > wrong_to_correct:
        reasons.append(
            f"correct→wrong ({correct_to_wrong}) exceeds wrong→correct ({wrong_to_correct})"
        )
    if wrong_to_correct == 0 and summary["n_C_ungated_differs"] == 0:
        reasons.append(
            "Text+Graph v2 ranking never differed from text baseline "
            f"(same-family pools={diag.get('same_family_pools', '?')})"
        )
    elif wrong_to_correct == 0:
        reasons.append("Graph v2 produced no wrong→correct gains")

    multi_n = int(diag.get("multi_family_with_gold") or 0)
    graph_fam_ok = int(diag.get("graph_argmax_family_matches_gold") or 0)
    text_fam_ok = int(diag.get("text_family_matches_gold_on_multi") or 0)
    graph_hss_w = int(diag.get("graph_argmax_favors_W_on_HSS_gold") or 0)
    if multi_n and graph_fam_ok < text_fam_ok:
        reasons.append(
            f"On multi-family pools, graph argmax family matches gold "
            f"{graph_fam_ok}/{multi_n} vs text {text_fam_ok}/{multi_n}"
        )
    if graph_hss_w > 0:
        reasons.append(
            f"Graph argmax prefers W on {graph_hss_w} HSS-gold multi-family rows "
            "(HSS→W bias risk)"
        )

    gated_explicit = int(
        (diag.get("gate_reason_C_counts") or {}).get("gate_explicit_protected") or 0
    )
    if (
        gated_explicit
        and summary["overall"]["C"]["accuracy"] > summary["overall"]["A"]["accuracy"]
    ):
        reasons.append(
            "Gated C accuracy lift is dominated by explicit-section protection, "
            "not Graph v2 candidate scoring"
        )

    hss_regressed = hss_c > hss_a or hss_c_ungated > hss_a

    if (
        gates["gate1_explicit_override_gated_C"] > 0
        or gates["gate2_incomplete_completed_gated_C"] > 0
        or gates.get("gate2_incomplete_completed_by_graph_change", 0) > 0
        or hss_regressed
        or correct_to_wrong > wrong_to_correct + 2
        or (unsafe > 0 and wrong_to_correct <= unsafe)
        or graph_hss_w > 0
        or (multi_n and graph_fam_ok < text_fam_ok)
        or summary["n_C_ungated_differs"] == 0
    ):
        return "DO NOT ENABLE", reasons or ["safety / usefulness failure"]

    if (
        wrong_to_correct > 0
        and correct_to_wrong <= max(1, wrong_to_correct // 3)
        and unsafe == 0
        and not hss_regressed
        and graph_hss_w == 0
    ):
        return "CANDIDATE-ONLY READY", [
            f"wrong→correct={wrong_to_correct}",
            f"correct→wrong={correct_to_wrong}",
            "no unsafe / HSS→W / explicit overrides under gates",
        ]

    if summary["n_C_ungated_differs"] > 0 and wrong_to_correct >= correct_to_wrong:
        return "SHADOW ONLY", reasons or [
            "weak but non-negative signal; not ready for ranking"
        ]

    return "DO NOT ENABLE", reasons or ["insufficient useful graph signal"]


def write_report(summary: Dict[str, Any], decision: str, reasons: List[str]) -> str:
    diag = summary.get("diagnostics") or {}
    lines = [
        "# Graph v2 Phase 5 Report",
        "",
        "## 1. Experiment setup",
        "",
        "Offline candidate-only Graph v2 ablation on cached `predictions_view.json`.",
        "No production flags changed. GraphSAGE / learned fusion / ranker remain OFF.",
        "Graph v2 is not hooked into the prediction pipeline.",
        "",
        "## 2. Dataset used",
        "",
        f"- Documents: **{summary['n_docs']}**",
        f"- Evaluated rows with candidate pools: **{summary['n_rows']}**",
        "- Source: `backend/training/eval_cache_backups/doc_*/predictions_view.json`",
        "- Optional join: `engineering_artifacts/*/multimodal/graph.json` when present",
        "- Gold: printed core after shop/cut strip (`proxy_gold_section`); incomplete L → no gold / abstain",
        "",
        "## 3. A/B/C/D methodology",
        "",
        "- **A**: text-only (alternative confidences + live section) — ungated",
        "- **B**: text + existing geometry similarity — ungated",
        "- **C**: text + Graph v2 — gated pick for safety metrics; ungated recorded separately",
        "- **D**: text + geometry + Graph v2 — gated pick; ungated recorded separately",
        "- Gates on C/D only: explicit protect, incomplete abstain, weak-evidence keep order",
        "- **Primary Graph signal** = ungated C vs A (gated accuracy is contaminated by explicit protection)",
        "",
        "## 4. Overall results",
        "",
        "| Variant | N with gold | Correct | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for v in ["A", "B", "C", "D"]:
        o = summary["overall"][v]
        lines.append(
            f"| {v} | {o['n_with_gold']} | {o['correct']} | {o['accuracy']} |"
        )
    lines += [
        "",
        f"Gated prediction changes vs A: C={summary['changed_predictions_gated']['C']}, "
        f"D={summary['changed_predictions_gated']['D']}",
        f"Ungated ranking changes vs A: C={summary['changed_predictions_ungated']['C']}, "
        f"D={summary['changed_predictions_ungated']['D']}",
        "",
        "### Graph diagnostics (signal, not gated accuracy)",
        "",
        f"- Same-family candidate pools: **{diag.get('same_family_pools')}**",
        f"- Multi-family candidate pools: **{diag.get('multi_family_pools')}**",
        f"- Rows with nonzero graph score spread: **{diag.get('rows_with_nonzero_score_spread')}**",
        f"- Mean graph score spread: **{diag.get('mean_graph_score_spread')}**",
        f"- Avg Graph v2 score: **{diag.get('avg_graph_v2_score')}**",
        f"- Multi-family gold rows where text family correct: "
        f"**{diag.get('text_family_matches_gold_on_multi')}/"
        f"{diag.get('multi_family_with_gold')}**",
        f"- Multi-family gold rows where graph-argmax family correct: "
        f"**{diag.get('graph_argmax_family_matches_gold')}/"
        f"{diag.get('multi_family_with_gold')}**",
        f"- Graph argmax prefers W on HSS gold (multi-family): "
        f"**{diag.get('graph_argmax_favors_W_on_HSS_gold')}**",
        f"- Gate reason C counts: `{json.dumps(diag.get('gate_reason_C_counts') or {})}`",
        "",
        f"_{diag.get('note', '')}_",
        "",
        "## 5. L results",
        "",
    ]
    for v in ["A", "B", "C", "D"]:
        ls = summary["L"][v]
        lines.append(
            f"- **{v}**: acc={ls['accuracy']['accuracy']} "
            f"(n={ls['accuracy']['n_with_gold']}), "
            f"L→2L={ls['L_to_2L']}, thickness={ls['thickness_error']}, "
            f"size/leg={ls['size_leg_error']}, "
            f"incomplete completions={ls['incomplete_L_completion']}"
        )
    lines += ["", "### L buckets (counts by variant pick class)", ""]
    lines.append("| Bucket | A | B | C | D |")
    lines.append("|---|---:|---:|---:|---:|")
    for b, counts in summary["L_buckets"].items():
        lines.append(
            f"| {b} | {counts['A']} | {counts['B']} | {counts['C']} | {counts['D']} |"
        )
    lines += [
        "",
        "Note: gated C/D L improvements largely reflect incomplete abstain + explicit protect, "
        "not Graph-driven L candidate discrimination (ungated C==A).",
        "",
        "## 6. HSS → W results",
        "",
        f"HSS gold rows: **{summary['HSS_n_with_gold']}**",
        "",
        "| Variant | HSS→W |",
        "|---|---:|",
        f"| A | {summary['HSS_to_W']['A']} |",
        f"| B | {summary['HSS_to_W']['B']} |",
        f"| C (gated) | {summary['HSS_to_W']['C']} |",
        f"| D (gated) | {summary['HSS_to_W']['D']} |",
        f"| C ungated | {summary['HSS_to_W']['C_ungated']} |",
        f"| D ungated | {summary['HSS_to_W']['D_ungated']} |",
        "",
        f"Difference gated C−A: **{summary['HSS_to_W']['C'] - summary['HSS_to_W']['A']}**",
        f"Difference ungated C−A: **{summary['HSS_to_W']['C_ungated'] - summary['HSS_to_W']['A']}**",
        f"Graph-argmax W preference on HSS gold (multi-family): "
        f"**{diag.get('graph_argmax_favors_W_on_HSS_gold')}**",
        "",
        "## 7. Wrong → correct / Correct → wrong",
        "",
        "### Ungated C vs A (true Graph ranking signal)",
        "",
        "```json",
        json.dumps(summary["changes_vs_A"].get("C_ungated") or {}, indent=2),
        "```",
        "",
        "### Gated C vs A (includes explicit protect / abstain — not pure Graph)",
        "",
        "```json",
        json.dumps(summary["changes_vs_A"].get("C") or {}, indent=2),
        "```",
        "",
        "## 8. Unsafe cases",
        "",
        f"- Ungated C unsafe_mutation: "
        f"**{(summary['changes_vs_A'].get('C_ungated') or {}).get('unsafe_mutation', 0)}**",
        f"- Ungated C explicit_label_conflict: "
        f"**{(summary['changes_vs_A'].get('C_ungated') or {}).get('explicit_label_conflict', 0)}**",
        f"- Gated incomplete completions: "
        f"**{summary['gates']['gate2_incomplete_completed_gated_C']}**",
        f"- Incomplete completions newly caused by Graph change: "
        f"**{summary['gates'].get('gate2_incomplete_completed_by_graph_change', 0)}**",
        f"- Gated explicit overrides: "
        f"**{summary['gates']['gate1_explicit_override_gated_C']}**",
        "",
        "## 9. Feature contribution analysis",
        "",
        f"Cases where ungated C differs from A: **{summary['n_C_ungated_differs']}**",
        "",
        "Average feature contributions on those cases:",
        "",
        "```json",
        json.dumps(summary["feature_avg_when_C_ungated_differs"], indent=2),
        "```",
        "",
        "Average feature contributions across all scored rows:",
        "",
        "```json",
        json.dumps(summary.get("feature_avg_all_rows") or {}, indent=2),
        "```",
        "",
        "## 10. Safety gates",
        "",
        "```json",
        json.dumps(summary["gates"], indent=2),
        "```",
        "",
        "## 11. Recommendation",
        "",
        f"**{decision}**",
        "",
    ]
    for reason in reasons:
        lines.append(f"- {reason}")
    lines += [
        "",
        "## 12. Exact next step",
        "",
    ]
    if decision == "DO NOT ENABLE":
        lines.append(
            "Do not add production flags. Graph v2 candidate scoring did not change "
            "text ranking and, on multi-family pools, can prefer W over HSS when "
            "role/orientation/neighbor evidence looks beam-like. Next research step "
            "(offline only): leader-target family features with anti-HSS→W constraints, "
            "or deprioritize Graph v2 versus incomplete-L abstain / explicit protect."
        )
    elif decision == "SHADOW ONLY":
        lines.append(
            "Keep offline; optionally log Graph v2 scores in shadow without affecting "
            "ranking. Expand leader/neighborhood features before any rerank flag."
        )
    else:
        lines.append(
            "Still do not enable automatically. A later PR could add "
            "`GRAPH_V2_CANDIDATE_RERANK` behind the same gates — do not enable now."
        )
    lines.append("")
    return "\n".join(lines)



def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc_ids = sorted(
        p.parent.name for p in CACHE_ROOT.glob("doc_*/predictions_view.json")
    )
    if not doc_ids:
        print("No cached predictions_view.json found under", CACHE_ROOT)
        return 1

    all_rows: List[Dict[str, Any]] = []
    all_changes: List[Dict[str, Any]] = []
    for doc_id in doc_ids:
        print(f"Evaluating {doc_id} ...")
        graph = _load_graph(doc_id)
        rows, changes = evaluate_doc(doc_id, graph)
        print(f"  rows={len(rows)} changes={len(changes)} graph_json={bool(graph)}")
        all_rows.extend(rows)
        all_changes.extend(changes)

    summary = summarize(all_rows, all_changes)
    decision, reasons = decide(summary)
    summary["recommendation"] = decision
    summary["recommendation_reasons"] = reasons

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    # Compact rows without huge nested objects duplicated
    slim_rows = []
    for r in all_rows:
        slim = dict(r)
        slim["feature_contributions"] = r.get("feature_contributions")
        slim_rows.append(slim)
    (OUT_DIR / "rows.jsonl").write_text(
        "\n".join(json.dumps(r) for r in slim_rows) + ("\n" if slim_rows else "")
    )

    change_path = OUT_DIR / "changed_cases.csv"
    fieldnames = [
        "document_id",
        "object_id",
        "raw_text",
        "baseline_A",
        "variant",
        "variant_prediction",
        "gold",
        "candidates",
        "graph_score",
        "feature_contributions",
        "evidence_used",
        "change_class",
        "error_type",
        "gate_reason",
    ]
    with change_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_changes:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    # L-only table
    l_path = OUT_DIR / "l_section_table.csv"
    with l_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "document_id",
                "object_id",
                "raw_text",
                "gold",
                "A",
                "B",
                "C",
                "D",
                "A_error",
                "B_error",
                "C_error",
                "D_error",
                "C_ungated",
                "graph_v2_score",
            ],
        )
        writer.writeheader()
        for r in all_rows:
            if not (
                r["incomplete"]
                or (r.get("gold") and family_of(r["gold"]) in {"L", "2L"})
                or family_of(core_section_token(r["raw_text"])) in {"L", "2L"}
            ):
                continue
            writer.writerow({k: r.get(k, "") for k in writer.fieldnames})

    report = write_report(summary, decision, reasons)
    report_path = OUT_DIR / "GRAPH_V2_PHASE5_REPORT.md"
    report_path.write_text(report)
    # Also place a copy at repo-requested path under backend/
    (BACKEND_DIR / "GRAPH_V2_PHASE5_REPORT.md").write_text(report)

    print("\n=== SUMMARY ===")
    print(json.dumps({
        "n_rows": summary["n_rows"],
        "overall": summary["overall"],
        "HSS_to_W": summary["HSS_to_W"],
        "changes_C_ungated": summary["changes_vs_A"].get("C_ungated"),
        "recommendation": decision,
        "reasons": reasons,
    }, indent=2))
    print("Wrote", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
