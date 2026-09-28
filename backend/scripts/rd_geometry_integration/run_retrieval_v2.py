#!/usr/bin/env python3
"""Run retrieval_v2 on the frozen Burrville human-gold set (R&D only).

Does not write gold_outcomes.jsonl. Does not import production association.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from overlays import render_v2_comparison_overlay
from retrieval import geometry_candidate_record, retrieve_candidates_for_label
from retrieval_v2 import (
    candidate_id_set,
    geometry_record_v2,
    gold_rank,
    has_local_member_candidate,
    retrieve_candidates_v2,
)

DOC_ID = "doc_0d910a43b4a021e3"
ARTIFACT = ROOT / "training" / "engineering_artifacts" / DOC_ID / "multimodal"
OUT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
GOLD_PATH = OUT / "review_kit" / "gold_outcomes.jsonl"
PAGES = (8, 18, 24)


def _load_json(name: str) -> Dict[str, Any]:
    path = ARTIFACT / name
    if not path.exists():
        raise FileNotFoundError(f"Missing artifact {path}")
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_gold() -> List[Dict[str, Any]]:
    rows = [json.loads(line) for line in GOLD_PATH.read_text().splitlines() if line.strip()]
    if len(rows) != 75:
        raise RuntimeError(f"Expected 75 gold rows, found {len(rows)}")
    return rows


def _geo_by_id(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(g.get("geometry_id")): g for g in records if g.get("geometry_id")}


def _failure_class(
    gold: Dict[str, Any],
    v2: List[Dict[str, Any]],
    *,
    gold_in_v2: bool,
    gold_rank_v2: Optional[int],
    proxy: bool,
) -> str:
    if gold.get("error_bucket") == "schedule_table_not_member":
        return "NOT_A_MEMBER"
    if gold.get("decision") == "ambiguous":
        return "AMBIGUITY"
    if gold.get("decision") == "associated":
        if not gold_in_v2:
            return "RETRIEVAL_FAILURE"
        if gold_rank_v2 is not None and gold_rank_v2 > 1:
            return "RANKING_FAILURE"
        return "RETRIEVED"
    # visible-member misses (no gold id)
    if gold.get("visible_member_on_drawing"):
        return "PROXY_RECOVERED" if proxy else "RETRIEVAL_FAILURE"
    return "OTHER"


def _recall_at(k: int, ranks: List[Optional[int]]) -> Dict[str, Any]:
    hits = sum(1 for r in ranks if r is not None and r <= k)
    n = len(ranks)
    return {"hits": hits, "n": n, "rate": (hits / n) if n else None}


def _leader_as_member_count(cands: List[Dict[str, Any]]) -> int:
    n = 0
    for c in cands:
        extracted = str(c.get("extracted_kind") or "")
        kind = str(c.get("geometry_kind") or "")
        reclass = c.get("reclassified_from")
        if (extracted == "leader" or kind == "leader") and not reclass:
            n += 1
        # A callout used as the associated member (mechanism never leader_target on itself)
        if kind == "leader" and c.get("retrieval_mechanism") != "leader_target" and not reclass:
            n += 1
    return n


def _ambiguity_flag(cands: List[Dict[str, Any]]) -> bool:
    if len(cands) < 2:
        return False
    d0 = cands[0].get("perpendicular_distance")
    d1 = cands[1].get("perpendicular_distance")
    if d0 is None or d1 is None:
        d0 = cands[0].get("bbox_distance")
        d1 = cands[1].get("bbox_distance")
    if d0 is None or d1 is None:
        return False
    return abs(float(d1) - float(d0)) <= 8.0


def _pick_render_token(rows: List[Dict[str, Any]], pred, fallback: str) -> str:
    for r in rows:
        if pred(r):
            return str(r["label_id"])
    return fallback


def main() -> int:
    gold_hash_before = _sha256(GOLD_PATH)
    document = _load_json("document.json")
    geometry = _load_json("geometry.json")
    gold_rows = _load_gold()

    raw_v2 = [geometry_record_v2(o) for o in (geometry.get("objects") or [])]
    raw_v1 = [geometry_candidate_record(o) for o in (geometry.get("objects") or [])]
    by_id_v2 = _geo_by_id(raw_v2)

    tokens_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for tok in document.get("engineering_tokens") or []:
        page = int(tok.get("page") or 0)
        if page in PAGES:
            tokens_by_page[page].append(tok)

    out_rows: List[Dict[str, Any]] = []
    for gold in gold_rows:
        token_id = gold["token_id"]
        page = int(gold["page"])
        label = None
        for tok in tokens_by_page[page]:
            if tok.get("token_id") == token_id:
                label = tok
                break
        if label is None:
            label = {
                "token_id": token_id,
                "text": gold.get("text"),
                "page": page,
                "bbox": gold.get("label_bbox"),
            }
        page_v1 = [g for g in raw_v1 if int(g["page_number"]) == page]
        page_v2 = [g for g in raw_v2 if int(g["page_number"]) == page]
        baseline = retrieve_candidates_for_label(
            label,
            page_v1,
            top_k=5,
            max_distance=150.0,
            exclude_leader_as_target=True,
            resolve_leaders=True,
        )
        v2 = retrieve_candidates_v2(label, page_v2, top_k=8, max_distance=180.0)
        baseline_ids = [c.get("geometry_id") for c in baseline if c.get("geometry_id")]
        v2_ids = candidate_id_set(v2)
        gold_gid = gold.get("selected_geometry_id")
        gold_in_baseline = bool(gold_gid) and gold_gid in (gold.get("candidate_geometry_ids") or baseline_ids)
        rank_v2 = gold_rank(v2, gold_gid)
        gold_in_v2 = rank_v2 is not None
        proxy = has_local_member_candidate(v2)
        baseline_proxy_rows = []
        for c in baseline:
            bb = c.get("geometry_bbox") or [0, 0, 0, 0]
            ext = ((bb[2] - bb[0]) ** 2 + (bb[3] - bb[1]) ** 2) ** 0.5
            baseline_proxy_rows.append(
                {
                    **c,
                    "extracted_kind": c.get("geometry_kind"),
                    "on_segment": c.get("perpendicular_distance") is not None,
                    "extent": ext,
                    "derived": False,
                    "giant": {"is_giant": ext >= 400.0},
                    "retrieval_mechanism": (
                        "leader_target"
                        if "leader_endpoint_resolved" in (c.get("candidate_generation_sources") or [])
                        else "direct_segment"
                    ),
                    "candidate_generation_sources": c.get("candidate_generation_sources") or ["direct_distance"],
                }
            )
        baseline_proxy = has_local_member_candidate(baseline_proxy_rows)
        # Baseline proxy should use bbox/perp already on the candidate if present.
        leader_ev = next((c.get("leader_evidence") for c in v2 if c.get("leader_evidence")), None)
        leader_detected = bool(leader_ev) or any(
            "leader_target" in (c.get("candidate_generation_sources") or []) for c in v2
        )
        failure = _failure_class(
            gold, v2, gold_in_v2=gold_in_v2, gold_rank_v2=rank_v2, proxy=proxy
        )
        gold_bb = None
        gold_cl = None
        if gold_gid and gold_gid in by_id_v2:
            gold_bb = by_id_v2[gold_gid].get("bbox")
            gold_cl = by_id_v2[gold_gid].get("centerline")
        leader_overlays = []
        if leader_ev:
            for lid in [leader_ev.get("leader_geometry_id"), *(leader_ev.get("leader_path_ids") or [])]:
                g = by_id_v2.get(str(lid or ""))
                if g:
                    leader_overlays.append(
                        {
                            "geometry_id": g.get("geometry_id"),
                            "geometry_bbox": g.get("bbox"),
                            "centerline": g.get("centerline"),
                            "points": g.get("points"),
                        }
                    )
        top_mechanism = (v2[0].get("retrieval_mechanism") if v2 else None)
        if gold_in_v2:
            for c in v2:
                if gold_gid in {c.get("geometry_id"), c.get("parent_geometry_id")}:
                    top_mechanism = c.get("retrieval_mechanism")
                    break
        elif proxy:
            for c in v2:
                if has_local_member_candidate([c]):
                    top_mechanism = c.get("retrieval_mechanism")
                    break
        out_rows.append(
            {
                "page": page,
                "label_id": token_id,
                "label_text": gold.get("text"),
                "label_bbox": gold.get("label_bbox"),
                "baseline_candidate_ids": baseline_ids,
                "v2_candidate_ids": [c.get("parent_geometry_id") or c.get("geometry_id") for c in v2],
                "v2_candidate_ids_raw": [c.get("geometry_id") for c in v2],
                "baseline_top1": (baseline[0].get("geometry_id") if baseline else None),
                "v2_top1": (
                    (v2[0].get("parent_geometry_id") or v2[0].get("geometry_id")) if v2 else None
                ),
                "human_gold_geometry_id": gold_gid,
                "human_decision": gold.get("decision"),
                "review_label": gold.get("review_label"),
                "gold_in_baseline_candidates": gold_in_baseline,
                "gold_in_v2_candidates": gold_in_v2,
                "gold_rank_v2": rank_v2,
                "retrieval_mechanism": top_mechanism,
                "ambiguity": _ambiguity_flag(v2) or gold.get("decision") == "ambiguous",
                "visible_member_on_drawing": bool(gold.get("visible_member_on_drawing")),
                "leader_required": bool(gold.get("leader_required")),
                "error_bucket": gold.get("error_bucket"),
                "failure_class": failure,
                "proxy_local_coverage_v2": proxy,
                "proxy_local_coverage_baseline": baseline_proxy,
                "leader_detected": leader_detected,
                "leader_as_member": _leader_as_member_count(v2),
                "leader_evidence": leader_ev,
                "baseline_candidates": baseline,
                "v2_candidates": v2,
                "human_gold_bbox": gold_bb,
                "human_gold_centerline": gold_cl,
                "leader_overlays": leader_overlays,
            }
        )

    associated = [r for r in out_rows if r["human_decision"] == "associated"]
    misses = [r for r in out_rows if r.get("visible_member_on_drawing") and r["human_decision"] == "no_valid_member"]
    schedule = [r for r in out_rows if r.get("error_bucket") == "schedule_table_not_member"]
    leader_req = [r for r in out_rows if r.get("leader_required")]

    def ranks_for(rows: List[Dict[str, Any]], which: str) -> List[Optional[int]]:
        out: List[Optional[int]] = []
        for r in rows:
            gid = r.get("human_gold_geometry_id")
            ids = r["baseline_candidate_ids"] if which == "baseline" else r["v2_candidate_ids"]
            if not gid:
                out.append(None)
                continue
            try:
                out.append(ids.index(gid) + 1)
            except ValueError:
                # v2 may store parent; gold_rank_v2 is authoritative for v2
                if which == "v2":
                    out.append(r.get("gold_rank_v2"))
                else:
                    out.append(None)
        return out

    base_ranks = ranks_for(associated, "baseline")
    v2_ranks = [r.get("gold_rank_v2") for r in associated]

    recovered = [r for r in misses if r["proxy_local_coverage_v2"]]
    still_missing = [r for r in misses if not r["proxy_local_coverage_v2"]]

    def _new_local_or_leader(row: Dict[str, Any]) -> List[str]:
        base = set(row.get("baseline_candidate_ids") or [])
        found: List[str] = []
        for c in row.get("v2_candidates") or []:
            pid = str(c.get("parent_geometry_id") or c.get("geometry_id") or "")
            if not pid or pid in base:
                continue
            lead = "leader_target" in (c.get("candidate_generation_sources") or [])
            perp = c.get("perpendicular_distance")
            giant = (c.get("giant") or {}).get("is_giant") and not c.get("derived")
            local = (
                perp is not None
                and float(perp) <= 28.0
                and c.get("on_segment")
                and float(c.get("extent") or 0.0) < 400.0
                and not giant
            )
            if lead or local:
                found.append(pid)
        return found

    new_coverage = [r for r in misses if _new_local_or_leader(r)]

    giant_baseline = 0
    giant_replaced = 0
    giant_examples = []
    for r in out_rows:
        b0 = r.get("baseline_top1")
        if not b0:
            continue
        # giant: baseline top1 extent from its candidate bbox
        b_cands = r.get("baseline_candidates") or []
        if not b_cands:
            continue
        bb = b_cands[0].get("geometry_bbox") or [0, 0, 0, 0]
        ext = ((bb[2] - bb[0]) ** 2 + (bb[3] - bb[1]) ** 2) ** 0.5
        if ext < 400:
            continue
        giant_baseline += 1
        v2_top = (r.get("v2_candidates") or [None])[0]
        replaced = bool(v2_top) and (
            (v2_top.get("giant") or {}).get("replaced_with_local_window")
            or v2_top.get("derived")
            or float(v2_top.get("extent") or 0) < 400
        )
        if replaced:
            giant_replaced += 1
        if len(giant_examples) < 8:
            giant_examples.append(
                {
                    "label_id": r["label_id"],
                    "page": r["page"],
                    "label_text": r["label_text"],
                    "human_decision": r["human_decision"],
                    "baseline_top1": b0,
                    "baseline_extent": round(ext, 1),
                    "v2_top1": r.get("v2_top1"),
                    "v2_extent": None if not v2_top else v2_top.get("extent"),
                    "v2_mechanism": r.get("retrieval_mechanism"),
                    "gold_geometry_id": r.get("human_gold_geometry_id"),
                }
            )

    def page_block(page: int) -> Dict[str, Any]:
        subset = [r for r in out_rows if r["page"] == page]
        vis = [r for r in subset if r.get("visible_member_on_drawing") and r["human_decision"] == "no_valid_member"]
        assoc = [r for r in subset if r["human_decision"] == "associated"]
        lead = [r for r in subset if r.get("leader_required")]
        return {
            "n": len(subset),
            "associated": len(assoc),
            "visible_member_misses": len(vis),
            "proxy_recovered": sum(1 for r in vis if r["proxy_local_coverage_v2"]),
            "leader_required": len(lead),
            "leader_detected": sum(1 for r in lead if r["leader_detected"]),
            "leader_target_in_candidates": sum(
                1
                for r in lead
                if any(
                    "leader_target" in (c.get("candidate_generation_sources") or [])
                    for c in (r.get("v2_candidates") or [])
                )
            ),
            "schedule_not_member": sum(1 for r in subset if r.get("error_bucket") == "schedule_table_not_member"),
            "ambiguity": sum(1 for r in subset if r.get("ambiguity")),
            "leader_as_member": sum(r.get("leader_as_member") or 0 for r in subset),
        }

    leader_target_retrieved = 0
    leader_detected_n = 0
    leader_target_missing = 0
    for r in leader_req:
        if r["leader_detected"]:
            leader_detected_n += 1
        has_target = any(
            "leader_target" in (c.get("candidate_generation_sources") or [])
            for c in (r.get("v2_candidates") or [])
        )
        if has_target:
            leader_target_retrieved += 1
        else:
            leader_target_missing += 1

    summary = {
        "document_id": DOC_ID,
        "n_labels": len(out_rows),
        "gold_sha256": gold_hash_before,
        "gold_immutable": True,
        "population_a_associated": {
            "n": len(associated),
            "baseline": {
                "recall_at_1": _recall_at(1, base_ranks),
                "recall_at_3": _recall_at(3, base_ranks),
                "recall_at_5": _recall_at(5, base_ranks),
            },
            "v2": {
                "recall_at_1": _recall_at(1, v2_ranks),
                "recall_at_3": _recall_at(3, v2_ranks),
                "recall_at_5": _recall_at(5, v2_ranks),
            },
        },
        "population_b_visible_member_misses": {
            "n": len(misses),
            "note": (
                "These 58 gold records have no selected_geometry_id. "
                "retrieval_recovered is PROXY local-coverage (non-giant local stroke "
                "or leader-target small geometry in the v2 shortlist), not invented gold IDs."
            ),
            "baseline_exact_gold_id": "0/58 by construction (no gold geometry id)",
            "baseline_proxy_local_coverage": sum(1 for r in misses if r["proxy_local_coverage_baseline"]),
            "retrieval_recovered": len(recovered),
            "retrieval_still_missing": len(still_missing),
            "retrieval_recovered_frac": f"{len(recovered)}/{len(misses)}",
            "retrieval_still_missing_frac": f"{len(still_missing)}/{len(misses)}",
            "new_local_or_leader_absent_from_baseline": len(new_coverage),
            "new_local_or_leader_frac": f"{len(new_coverage)}/{len(misses)}",
            "new_coverage_ids": [r["label_id"] for r in new_coverage],
            "recovered_ids": [r["label_id"] for r in recovered],
            "still_missing_ids": [r["label_id"] for r in still_missing],
        },
        "failure_classes": dict(Counter(r["failure_class"] for r in out_rows)),
        "leader": {
            "n_leader_required": len(leader_req),
            "leader_detected": leader_detected_n,
            "target_geometry_retrieved": leader_target_retrieved,
            "target_geometry_missing": leader_target_missing,
            "leader_as_member_total": sum(r.get("leader_as_member") or 0 for r in out_rows),
            "leader_as_member_invariant_ok": sum(r.get("leader_as_member") or 0 for r in out_rows) == 0,
        },
        "giant_polyline": {
            "baseline_top1_extent_ge_400": giant_baseline,
            "v2_replaced_or_local": giant_replaced,
            "examples": giant_examples,
        },
        "by_page": {str(p): page_block(p) for p in PAGES},
        "schedule_not_member": len(schedule),
        "mechanisms": dict(Counter(r.get("retrieval_mechanism") or "none" for r in out_rows)),
        "review_followup": [],
        "safety": {
            "production_untouched": True,
            "ghx_untouched": True,
            "semantic_review_untouched": True,
            "takeoff_untouched": True,
            "ml": False,
            "vlm": False,
            "section_completion": False,
            "leader_as_member": 0,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    rows_path = OUT / "v2_rows.jsonl"
    with rows_path.open("w") as fh:
        for row in out_rows:
            slim = {k: v for k, v in row.items() if k not in {"baseline_candidates", "v2_candidates"}}
            slim["baseline_candidates"] = [
                {
                    "geometry_id": c.get("geometry_id"),
                    "rank": c.get("rank"),
                    "geometry_kind": c.get("geometry_kind"),
                    "geometry_bbox": c.get("geometry_bbox"),
                    "centerline": c.get("centerline"),
                    "bbox_distance": c.get("bbox_distance"),
                    "perpendicular_distance": c.get("perpendicular_distance"),
                }
                for c in (row.get("baseline_candidates") or [])
            ]
            slim["v2_candidates"] = [
                {
                    "geometry_id": c.get("geometry_id"),
                    "parent_geometry_id": c.get("parent_geometry_id"),
                    "rank": c.get("rank"),
                    "geometry_kind": c.get("geometry_kind"),
                    "extracted_kind": c.get("extracted_kind"),
                    "geometry_bbox": c.get("geometry_bbox"),
                    "centerline": c.get("centerline"),
                    "bbox_distance": c.get("bbox_distance"),
                    "perpendicular_distance": c.get("perpendicular_distance"),
                    "extent": c.get("extent"),
                    "retrieval_mechanism": c.get("retrieval_mechanism"),
                    "candidate_generation_sources": c.get("candidate_generation_sources"),
                    "leader_evidence": c.get("leader_evidence"),
                    "tip_distance": c.get("tip_distance"),
                    "on_segment": c.get("on_segment"),
                    "derived": c.get("derived"),
                    "giant": c.get("giant"),
                    "reclassified_from": c.get("reclassified_from"),
                }
                for c in (row.get("v2_candidates") or [])
            ]
            fh.write(json.dumps(slim) + "\n")

    # Visual QA — representative crops (label-centered, source PDF unchanged)
    pdf_path = ROOT / "uploads" / "Burrville ES - ST.pdf"
    render_dir = OUT / "v2_renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    by_id_row = {r["label_id"]: r for r in out_rows}

    picks = {
        "giant_polyline_failure": "token_p8_348",
        "recovered_p8_member": _pick_render_token(
            recovered,
            lambda r: r["page"] == 8 and r["label_id"] == "token_p8_359",
            _pick_render_token(recovered, lambda r: r["page"] == 8, "token_p8_340"),
        ),
        "leader_p18": _pick_render_token(
            leader_req,
            lambda r: r["page"] == 18 and r["leader_detected"],
            "token_p18_1162",
        ),
        "leader_p24": _pick_render_token(
            leader_req,
            lambda r: r["page"] == 24 and r["leader_detected"],
            "token_p24_1361",
        ),
        "remaining_retrieval_failure": _pick_render_token(
            still_missing,
            lambda r: r["label_id"] == "token_p8_355",
            _pick_render_token(still_missing, lambda r: True, "token_p8_355"),
        ),
        "ambiguous": _pick_render_token(
            out_rows,
            lambda r: r["human_decision"] == "ambiguous",
            "token_p8_367",
        ),
    }
    if "token_p8_359" in by_id_row:
        picks["recovered_p8_member"] = "token_p8_359"
    if "token_p24_1361" in by_id_row:
        picks["leader_p24"] = "token_p24_1361"
    if "token_p8_355" in by_id_row:
        picks["remaining_retrieval_failure"] = "token_p8_355"

    render_rel = {}
    for name, tid in picks.items():
        row = by_id_row.get(tid)
        if not row:
            continue
        rel = f"v2_renders/{name}_{tid}.png"
        ok = render_v2_comparison_overlay(pdf_path, int(row["page"]), row, OUT / rel)
        render_rel[name] = {"token_id": tid, "path": rel if ok else None, "ok": ok}

    (render_dir / "LEGEND.txt").write_text(
        "blue = label bbox\n"
        "gray / dashed orange = baseline candidates (orange = baseline top-1)\n"
        "green = v2 candidates (darker = v2 top-1)\n"
        "magenta = human gold geometry (associated labels only)\n"
        "purple = leader evidence / target point\n"
        "Crop is label-centered; giant primitive boxes are not used to expand the clip.\n"
    )
    summary["visual_qa"] = render_rel
    (OUT / "v2_summary.json").write_text(json.dumps(summary, indent=2))

    gold_hash_after = _sha256(GOLD_PATH)
    if gold_hash_after != gold_hash_before:
        raise RuntimeError("gold_outcomes.jsonl changed during v2 run — abort")
    summary["gold_sha256_after"] = gold_hash_after
    (OUT / "v2_summary.json").write_text(json.dumps(summary, indent=2))

    print("Wrote", rows_path)
    print("Wrote", OUT / "v2_summary.json")
    print("Population A associated", json.dumps(summary["population_a_associated"], indent=2))
    print("Population B", json.dumps({k: summary["population_b_visible_member_misses"][k] for k in (
        "n", "retrieval_recovered", "retrieval_still_missing", "retrieval_recovered_frac", "baseline_proxy_local_coverage"
    )}, indent=2))
    print("Leader", json.dumps(summary["leader"], indent=2))
    print("By page", json.dumps(summary["by_page"], indent=2))
    print("gold hash unchanged", gold_hash_before)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
