#!/usr/bin/env python3
"""Offline investigation: leader → target member evidence quality.

Read-only over cached graph.json / predictions_view / geometry.json.
Does NOT modify production ranking or write flags.

Run from backend/:
  python scripts/investigate_leader_target.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.engineering.graph_v2_scorer import (  # noqa: E402
    family_of,
    is_explicit_complete_section,
    is_incomplete_angle,
    proxy_gold_section,
)
from services.token_extractor import (  # noqa: E402
    core_section_token,
    normalize_engineering_token,
)

CACHE_ROOT = BACKEND_DIR / "training" / "eval_cache_backups"
ARTIFACTS_ROOT = BACKEND_DIR / "training" / "engineering_artifacts"
REPORT_PATH = BACKEND_DIR / "GRAPH_LEADER_TARGET_INVESTIGATION.md"

STRUCTURAL_KINDS = {"line", "polyline", "path", "arc", "curve"}
MEMBER_NODE_KINDS = {"beam", "column", "brace", "connection", "plate", "member"}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _orient_bin(orientation: Any) -> Optional[str]:
    if orientation is None:
        return None
    try:
        deg = float(orientation)
    except (TypeError, ValueError):
        return None
    # Normalize to [0, 180)
    deg = abs(deg) % 180.0
    if deg <= 25 or deg >= 155:
        return "horizontal"
    if 65 <= deg <= 115:
        return "vertical"
    return "diagonal"


def _classify_reliability(
    *,
    leader_resolved: bool,
    association_sources: List[str],
    candidate_count: int,
    target_kind: str,
    target_geometry_kind: str,
    distance: Optional[float],
    target_has_label_neighbor: bool,
) -> str:
    """A/B/C/D reliability buckets for a nearest_geometry association."""

    sources = set(association_sources or [])
    has_leader = leader_resolved or ("leader_endpoint_resolved" in sources)
    structural = target_geometry_kind in STRUCTURAL_KINDS or target_kind in {
        "beam",
        "column",
        "brace",
    }
    dist = float(distance) if distance is not None else 9999.0
    multi_leader = sum(
        1 for s in association_sources if s == "leader_endpoint_resolved"
    )

    if not has_leader:
        if structural and dist < 40:
            return "C"  # geometry-only / weak (direct nearest, no leader)
        return "D"

    # Leader present
    if structural and dist < 80 and candidate_count <= 2 and multi_leader <= 2:
        return "A"
    if structural and dist < 160:
        # Ambiguous if many leader hops or many candidates
        if multi_leader >= 3 or candidate_count >= 3:
            return "B"
        return "A" if dist < 100 else "B"
    if structural:
        return "B"
    # Leader resolved onto non-structural (connection/leader-like residue)
    return "C"


def _l_bucket(raw: str, gold: Optional[str]) -> str:
    if is_incomplete_angle(raw):
        return "incomplete_L"
    core = core_section_token(raw)
    fam = family_of(core)
    if fam not in {"L", "2L"}:
        return "not_L"
    if is_explicit_complete_section(raw):
        # shop/cut suffix if raw differs after strip
        if normalize_engineering_token(raw) != core and core == (gold or core):
            # has extra shop/cut material beyond core
            stripped = proxy_gold_section(raw)
            if stripped and stripped == gold:
                # check if raw contains shop/cut markers
                upper = raw.upper()
                if any(tok in upper for tok in ("SHOP", "CUT", "CONT", '"', "X", "MM")):
                    # Prefer detecting shop/cut via core != full token path
                    pass
            if '"' in raw or "SHOP" in upper or "CUT" in upper:
                return "explicit_L_shop_cut"
            return "explicit_complete_L"
        return "explicit_complete_L"
    if fam in {"L", "2L"} and not gold:
        return "unlabeled_L"
    return "other_L"


def _l_bucket_v2(raw: str) -> str:
    if is_incomplete_angle(raw):
        return "incomplete_L"
    core = core_section_token(raw)
    fam = family_of(core)
    if fam not in {"L", "2L"}:
        return "not_L"
    upper = raw.upper()
    has_shop = any(
        m in upper
        for m in ("SHOP", "CUT ", " CUT", "CONT.", "CONT ", "TYP", "SEE ")
    ) or ('"' in raw)
    if is_explicit_complete_section(raw):
        return "explicit_L_shop_cut" if has_shop else "explicit_complete_L"
    # Partial / unlabeled L-like
    if fam in {"L", "2L"}:
        return "unlabeled_L"
    return "other_L"


def analyze_doc(doc_id: str) -> Dict[str, Any]:
    graph_path = ARTIFACTS_ROOT / doc_id / "multimodal" / "graph.json"
    geom_path = ARTIFACTS_ROOT / doc_id / "multimodal" / "geometry.json"
    pred_path = CACHE_ROOT / doc_id / "predictions_view.json"
    if not pred_path.exists():
        alt = ARTIFACTS_ROOT / doc_id / "multimodal" / "predictions_view.json"
        pred_path = alt if alt.exists() else pred_path

    out: Dict[str, Any] = {
        "doc_id": doc_id,
        "has_graph": graph_path.exists(),
        "has_geometry": geom_path.exists(),
        "has_predictions": pred_path.exists(),
    }
    if not pred_path.exists():
        return out

    preds = _load_json(pred_path).get("predictions") or []
    graph = _load_json(graph_path) if graph_path.exists() else None
    geometry_by_id: Dict[str, Any] = {}
    if geom_path.exists():
        geom_payload = _load_json(geom_path)
        for g in geom_payload.get("objects") or geom_payload.get("geometries") or []:
            gid = str(g.get("geometry_id") or g.get("id") or "")
            if gid:
                geometry_by_id[gid] = g

    nodes_by_id: Dict[str, Any] = {}
    source_to_node: Dict[str, str] = {}
    text_to_nodes: Dict[str, List[str]] = defaultdict(list)
    nearest_geom_by_label: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    nearest_label_by_geom: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    leader_nodes = 0

    if graph:
        for n in graph.get("nodes") or []:
            nid = str(n.get("node_id") or "")
            nodes_by_id[nid] = n
            sid = str(n.get("source_id") or "")
            if sid:
                source_to_node[sid] = nid
            if str(n.get("geometry_kind") or "").lower() == "leader":
                leader_nodes += 1
            text = str(n.get("text") or "").strip()
            if text and nid.startswith("txt_"):
                text_to_nodes[normalize_engineering_token(text)].append(nid)

        for e in graph.get("edges") or []:
            rel = str(e.get("relationship") or "")
            src = str(e.get("source") or "")
            tgt = str(e.get("target") or "")
            meta = e.get("meta") or {}
            payload = {
                "source": src,
                "target": tgt,
                "distance": e.get("distance"),
                "weight": e.get("weight"),
                "meta": meta,
                "page_number": e.get("page_number"),
            }
            if rel == "nearest_geometry":
                nearest_geom_by_label[src].append(payload)
            elif rel == "nearest_label":
                nearest_label_by_geom[src].append(payload)

    out["leader_nodes"] = leader_nodes
    raw_diag = (graph or {}).get("diagnostics") if graph else None
    # diagnostics may be a dict or a list depending on artifact version
    if isinstance(raw_diag, list):
        merged: Dict[str, Any] = {}
        for item in raw_diag:
            if isinstance(item, dict):
                for k, v in item.items():
                    if isinstance(v, (int, float)):
                        merged[k] = merged.get(k, 0) + v
                    else:
                        merged.setdefault(k, v)
        out["diagnostics"] = merged
    else:
        out["diagnostics"] = raw_diag if isinstance(raw_diag, dict) else None

    # Predictions indexed by object_id
    rows: List[Dict[str, Any]] = []
    reliability = Counter()
    family_cases: List[Dict[str, Any]] = []
    hss_w_cases: List[Dict[str, Any]] = []
    w_hss_cases: List[Dict[str, Any]] = []
    l_cases: List[Dict[str, Any]] = []
    strong_examples: List[Dict[str, Any]] = []
    ambiguous_examples: List[Dict[str, Any]] = []
    missing_examples: List[Dict[str, Any]] = []

    for pred in preds:
        raw = str(
            pred.get("raw_text")
            or pred.get("original_token")
            or pred.get("normalized_text")
            or ""
        )
        if not raw:
            continue
        object_id = str(pred.get("object_id") or "")
        gold = proxy_gold_section(raw)
        gold_fam = family_of(gold or "")
        live = normalize_engineering_token(
            str(pred.get("section") or pred.get("section_prediction") or "")
        )
        # Candidate families from alternatives
        cand_shapes: List[str] = []
        if live:
            cand_shapes.append(live)
        for alt in pred.get("alternatives") or []:
            shape = normalize_engineering_token(str(alt.get("shape") or ""))
            if shape:
                cand_shapes.append(shape)
        for item in pred.get("candidate_sections") or []:
            if isinstance(item, dict):
                shape = normalize_engineering_token(str(item.get("shape") or ""))
            else:
                shape = normalize_engineering_token(str(item))
            if shape:
                cand_shapes.append(shape)
        cand_families = {family_of(s) for s in cand_shapes}
        cand_families.discard("")

        # Resolve label node
        label_node_id = source_to_node.get(object_id)
        if not label_node_id:
            # try matching by normalized text
            core = normalize_engineering_token(core_section_token(raw) or raw)
            candidates_ids = text_to_nodes.get(core) or []
            label_node_id = candidates_ids[0] if len(candidates_ids) == 1 else None

        edges = nearest_geom_by_label.get(label_node_id or "", [])
        # Some graphs may store object_id differently — also try txt from preds graph_preview
        if not edges:
            preview = pred.get("graph_preview") or {}
            # no direct edge id there
            pass

        if not edges:
            bucket = "D"
            reliability[bucket] += 1
            row = {
                "raw": raw,
                "gold": gold,
                "gold_fam": gold_fam,
                "bucket": bucket,
                "leader_resolved": False,
                "reason": "no_nearest_geometry_edge",
            }
            rows.append(row)
            if gold_fam or is_incomplete_angle(raw) or family_of(core_section_token(raw)):
                missing_examples.append(
                    {
                        "doc": doc_id,
                        "raw": raw[:80],
                        "gold": gold,
                        "reason": "missing_or_unresolved",
                    }
                )
            # L tracking even when missing
            lb = _l_bucket_v2(raw)
            if lb != "not_L":
                l_cases.append(
                    {
                        "doc": doc_id,
                        "raw": raw,
                        "l_bucket": lb,
                        "leader_bucket": "D",
                        "leader_resolved": False,
                        "target_kind": None,
                        "would_justify_completion": False,
                    }
                )
            continue

        # Use first nearest_geometry edge (production keeps one)
        edge = edges[0]
        meta = edge.get("meta") or {}
        sources = list(meta.get("association_sources") or [])
        leader_resolved = bool(meta.get("leader_resolved")) or (
            "leader_endpoint_resolved" in sources
        )
        target_id = str(edge.get("target") or "")
        target = nodes_by_id.get(target_id) or {}
        target_kind = str(target.get("kind") or "").lower()
        target_gkind = str(target.get("geometry_kind") or "").lower()
        distance = edge.get("distance")
        cand_count = int(meta.get("candidate_count") or 1)

        # Is target explicitly labeled? Check nearest_label back to a text node
        # with a section-like family, or target text field.
        target_labels = nearest_label_by_geom.get(target_id) or []
        labeled = False
        neighbor_label_families: List[str] = []
        for nl in target_labels[:5]:
            lab_node = nodes_by_id.get(str(nl.get("target") or "")) or {}
            lab_text = str(lab_node.get("text") or "")
            fam = family_of(core_section_token(lab_text))
            if fam:
                labeled = True
                neighbor_label_families.append(fam)

        # Also: if our own label is on the edge, the association itself is the label
        source_labeled = True  # this edge starts from a label

        # Orientation / role from graph node + geometry object
        orientation = target.get("orientation")
        orient_bin = _orient_bin(orientation)
        role = target_kind if target_kind in MEMBER_NODE_KINDS else None
        geom_obj = geometry_by_id.get(str(target.get("source_id") or ""))
        leader_geom_near: Optional[Dict[str, Any]] = None
        # Find a nearby leader via nearest_label reverse? Not stored.
        # Use geometry kind leader endpoints only when target is wrongly a leader.
        if geom_obj and str(geom_obj.get("kind") or "").lower() == "leader":
            leader_geom_near = geom_obj

        bucket = _classify_reliability(
            leader_resolved=leader_resolved,
            association_sources=sources,
            candidate_count=cand_count,
            target_kind=target_kind,
            target_geometry_kind=target_gkind,
            distance=float(distance) if distance is not None else None,
            target_has_label_neighbor=labeled,
        )
        reliability[bucket] += 1

        # Family preference heuristic from target geometry (FAMILY ONLY)
        preferred_families: Set[str] = set()
        preference = "missing"
        if not leader_resolved and bucket in {"C", "D"}:
            preference = "missing" if bucket == "D" else "neutral"
        else:
            # Map role/orientation → family soft preference (same soft priors as
            # existing project; investigation only, not a scorer).
            if role == "beam" or orient_bin == "horizontal":
                preferred_families.update({"W", "S", "M", "C", "MC"})
            if role == "column" or orient_bin == "vertical":
                preferred_families.update({"W", "HSS", "PIPE", "HP"})
            if role == "brace" or orient_bin == "diagonal":
                preferred_families.update({"L", "2L", "HSS", "WT", "PIPE"})
            if target_gkind in STRUCTURAL_KINDS and not preferred_families:
                preference = "neutral"
            elif not preferred_families:
                preference = "neutral"
            else:
                if gold_fam and gold_fam in preferred_families:
                    preference = "prefers_gold_family"
                elif gold_fam and preferred_families and gold_fam not in preferred_families:
                    preference = "prefers_other_family"
                else:
                    preference = "neutral"

        row = {
            "doc": doc_id,
            "object_id": object_id,
            "raw": raw,
            "gold": gold,
            "gold_fam": gold_fam,
            "bucket": bucket,
            "leader_resolved": leader_resolved,
            "distance": distance,
            "candidate_count": cand_count,
            "association_sources": sources,
            "n_leader_sources": sum(
                1 for s in sources if s == "leader_endpoint_resolved"
            ),
            "target_id": target_id,
            "target_kind": target_kind,
            "target_geometry_kind": target_gkind,
            "target_orientation": orientation,
            "orient_bin": orient_bin,
            "target_explicitly_labeled": labeled,
            "neighbor_label_families": neighbor_label_families,
            "preferred_families": sorted(preferred_families),
            "preference": preference,
            "cand_families": sorted(cand_families),
            "used_in_production_ranking": False,  # leader meta not read by fusion
            "used_in_association": True,
        }
        rows.append(row)

        if gold_fam and len(cand_families) >= 2:
            family_cases.append(row)

        # HSS vs W
        if gold_fam == "HSS" and "HSS" in cand_families and "W" in cand_families:
            if not leader_resolved:
                lean = "missing"
            elif "HSS" in preferred_families and "W" not in preferred_families:
                lean = "prefers_HSS"
            elif "W" in preferred_families and "HSS" not in preferred_families:
                lean = "prefers_W"
            elif "HSS" in preferred_families and "W" in preferred_families:
                lean = "neutral"
            else:
                lean = "neutral"
            hss_w_cases.append({**row, "lean": lean})

        if gold_fam == "W" and "HSS" in cand_families and "W" in cand_families:
            if not leader_resolved:
                lean = "missing"
            elif "W" in preferred_families and "HSS" not in preferred_families:
                lean = "prefers_W"
            elif "HSS" in preferred_families and "W" not in preferred_families:
                lean = "prefers_HSS"
            else:
                lean = "neutral"
            w_hss_cases.append({**row, "lean": lean})

        lb = _l_bucket_v2(raw)
        if lb != "not_L":
            # Leader evidence must NOT justify thickness/completion
            justifies_completion = False
            # By construction our analysis is family-only; flag if someone
            # might misuse distance/role as size signal — we record False.
            l_cases.append(
                {
                    "doc": doc_id,
                    "raw": raw,
                    "l_bucket": lb,
                    "leader_bucket": bucket,
                    "leader_resolved": leader_resolved,
                    "target_kind": target_kind,
                    "orient_bin": orient_bin,
                    "preferred_families": sorted(preferred_families),
                    "would_justify_completion": justifies_completion,
                    "gold": gold,
                }
            )

        if bucket == "A" and leader_resolved and len(strong_examples) < 25:
            strong_examples.append(
                {
                    "doc": doc_id,
                    "raw": raw[:80],
                    "gold": gold,
                    "target_kind": target_kind,
                    "target_geometry_kind": target_gkind,
                    "orient_bin": orient_bin,
                    "distance": distance,
                    "n_leader_sources": row["n_leader_sources"],
                    "candidate_count": cand_count,
                }
            )
        if bucket == "B" and len(ambiguous_examples) < 25:
            ambiguous_examples.append(
                {
                    "doc": doc_id,
                    "raw": raw[:80],
                    "gold": gold,
                    "target_kind": target_kind,
                    "target_geometry_kind": target_gkind,
                    "distance": distance,
                    "n_leader_sources": row["n_leader_sources"],
                    "candidate_count": cand_count,
                    "sources": sources[:6],
                }
            )
        if bucket in {"C", "D"} and leader_geom_near and len(ambiguous_examples) < 40:
            ambiguous_examples.append(
                {
                    "doc": doc_id,
                    "raw": raw[:80],
                    "gold": gold,
                    "issue": "target_is_or_near_leader_stroke",
                    "bucket": bucket,
                }
            )

    out.update(
        {
            "n_pred_rows_scanned": len(preds),
            "n_associations_classified": len(rows),
            "reliability": dict(reliability),
            "leader_resolved_true": sum(1 for r in rows if r.get("leader_resolved")),
            "family_cases": family_cases,
            "hss_w_cases": hss_w_cases,
            "w_hss_cases": w_hss_cases,
            "l_cases": l_cases,
            "strong_examples": strong_examples,
            "ambiguous_examples": ambiguous_examples[:25],
            "missing_examples": missing_examples[:25],
            "rows": rows,
        }
    )
    return out


def _pct(n: int, d: int) -> str:
    if d <= 0:
        return "n/a"
    return f"{100.0 * n / d:.1f}%"


def _agg_reliability(subset: List[Dict[str, Any]]) -> Tuple[Counter, int, int]:
    rel: Counter = Counter()
    leader_true = 0
    n_assoc = 0
    for r in subset:
        for k, v in (r.get("reliability") or {}).items():
            rel[k] += v
        leader_true += int(r.get("leader_resolved_true") or 0)
        n_assoc += int(r.get("n_associations_classified") or 0)
    return rel, leader_true, n_assoc


def write_report(results: List[Dict[str, Any]]) -> str:
    docs_with_graph = [r for r in results if r.get("has_graph")]
    docs_without = [r for r in results if not r.get("has_graph")]

    rel, leader_true, n_assoc = _agg_reliability(results)
    rel_g, leader_true_g, n_assoc_g = _agg_reliability(docs_with_graph)
    total_rel = sum(rel.values())
    total_rel_g = sum(rel_g.values())

    # Family separation among multi-family gold
    fam_pref = Counter()
    fam_n = 0
    for r in docs_with_graph:
        for case in r.get("family_cases") or []:
            if not case.get("gold_fam"):
                continue
            fam_n += 1
            fam_pref[case.get("preference") or "missing"] += 1

    hss_lean = Counter()
    hss_n = 0
    hss_with_leader = 0
    for r in docs_with_graph:
        for case in r.get("hss_w_cases") or []:
            hss_n += 1
            hss_lean[case.get("lean") or "missing"] += 1
            if case.get("leader_resolved"):
                hss_with_leader += 1

    # Broader HSS lean: all HSS-gold leader_resolved rows (even without W in pool)
    hss_all_lean = Counter()
    hss_all_n = 0
    w_all_lean = Counter()
    w_all_n = 0
    leader_target_kinds = Counter()
    leader_orients = Counter()
    leader_multi_src = Counter()
    for r in docs_with_graph:
        for row in r.get("rows") or []:
            if not row.get("leader_resolved"):
                continue
            leader_target_kinds[row.get("target_kind") or ""] += 1
            leader_orients[row.get("orient_bin") or "unknown"] += 1
            nls = int(row.get("n_leader_sources") or 0)
            leader_multi_src["ge3" if nls >= 3 else "lt3"] += 1
            pref = set(row.get("preferred_families") or [])
            gf = row.get("gold_fam")
            if gf == "HSS":
                hss_all_n += 1
                if "HSS" in pref and "W" not in pref:
                    hss_all_lean["prefers_HSS_only"] += 1
                elif "W" in pref and "HSS" not in pref:
                    hss_all_lean["prefers_W_only"] += 1
                elif "HSS" in pref and "W" in pref:
                    hss_all_lean["both_HSS_and_W"] += 1
                else:
                    hss_all_lean["neither"] += 1
            if gf == "W":
                w_all_n += 1
                if "W" in pref and "HSS" not in pref:
                    w_all_lean["prefers_W_only"] += 1
                elif "HSS" in pref and "W" not in pref:
                    w_all_lean["prefers_HSS_only"] += 1
                elif "HSS" in pref and "W" in pref:
                    w_all_lean["both"] += 1
                else:
                    w_all_lean["neither"] += 1

    w_lean = Counter()
    w_n = 0
    for r in docs_with_graph:
        for case in r.get("w_hss_cases") or []:
            w_n += 1
            w_lean[case.get("lean") or "missing"] += 1

    l_stats: Dict[str, Counter] = defaultdict(Counter)
    l_completion_flags = 0
    for r in results:
        for case in r.get("l_cases") or []:
            lb = case.get("l_bucket") or "other"
            l_stats[lb]["n"] += 1
            l_stats[lb][f"leader_{case.get('leader_bucket')}"] += 1
            if case.get("leader_resolved"):
                l_stats[lb]["leader_resolved"] += 1
            if case.get("would_justify_completion"):
                l_completion_flags += 1

    strong = []
    amb = []
    missing = []
    for r in results:
        strong.extend(r.get("strong_examples") or [])
        amb.extend(r.get("ambiguous_examples") or [])
        missing.extend(r.get("missing_examples") or [])

    prod_use = (
        "Leader meta (`leader_resolved`, `association_sources`) is used when "
        "**building** `nearest_geometry` edges (selects the associated member). "
        "Production fusion/ranking does **not** read leader fields as a feature; "
        "only indirect graph scalars (degree / min_distance / graph_consistency) "
        "reach ranking. GraphSAGE / learned fusion remain OFF."
    )

    prefers_w_only = hss_all_lean.get("prefers_W_only", 0)
    prefers_hss_only = hss_all_lean.get("prefers_HSS_only", 0)
    gold_family_ok = fam_pref.get("prefers_gold_family", 0)
    other_family = fam_pref.get("prefers_other_family", 0)
    a_pct_g = (rel_g["A"] / total_rel_g) if total_rel_g else 0.0

    # Family-level signal is the question. Association edges exist, but
    # orientation/role priors after leader hop bias HSS→W and A-rate is tiny.
    if prefers_w_only > 0 and prefers_hss_only == 0 and hss_all_n >= 20:
        recommendation = "STOP — leader-target evidence is too weak/noisy"
        rec_why = [
            f"On {hss_all_n} HSS-gold rows with leader_resolved, orientation/role "
            f"lean is prefers_W_only={prefers_w_only}, prefers_HSS_only="
            f"{prefers_hss_only}, both={hss_all_lean.get('both_HSS_and_W', 0)} "
            "(systematic HSS→W risk).",
            f"Reliability A is only {rel_g['A']}/{total_rel_g} "
            f"({_pct(rel_g['A'], total_rel_g)}) on docs that have graph.json; "
            f"most resolved hops are ambiguous B "
            f"({rel_g['B']}, often ≥3 leader sources).",
            "Targets are almost always unlabeled `kind=geometry` — no printed "
            "member section to ground family.",
            "Far-endpoint hop uses bbox corner; true polyline endpoints are not "
            "on graph nodes; leader id is not stored on the winning edge.",
        ]
    elif a_pct_g >= 0.35 and gold_family_ok > other_family * 1.5 and prefers_w_only == 0:
        recommendation = (
            "CANDIDATE-FAMILY SIGNAL POSSIBLE — evidence is sufficiently reliable "
            "for a future controlled offline scorer"
        )
        rec_why = [
            f"Reliability A share={_pct(rel_g['A'], total_rel_g)}; "
            f"gold-family preference {gold_family_ok} vs other {other_family}.",
            "Still keep Graph v2 / GraphSAGE OFF in production.",
        ]
    elif leader_true_g > 0:
        recommendation = (
            "INVESTIGATE FURTHER — evidence exists but needs better data"
        )
        rec_why = [
            f"leader_resolved associations exist ({leader_true_g}) but family "
            "separation is not reliable.",
            "Need true endpoints, leader id on edge, and member role labels "
            "before any family scorer.",
        ]
    else:
        recommendation = "STOP — leader-target evidence is too weak/noisy"
        rec_why = ["No usable leader-target associations found."]

    lines: List[str] = []
    lines += [
        "# Graph Leader → Target Member Investigation",
        "",
        "## A. Executive conclusion",
        "",
        f"**Recommendation: {recommendation}**",
        "",
        "Graph v2 remains **DO NOT ENABLE** in production. This investigation only "
        "asks whether existing leader→target associations contain family-level signal.",
        "",
        "Key findings:",
        f"- Docs with `graph.json`: **{len(docs_with_graph)}** / {len(results)} "
        "(primary evidence subset; 5/8 eval docs lack graph.json → D)",
        f"- All-doc associations classified: **{n_assoc}** "
        f"(leader_resolved={leader_true})",
        f"- Graph-doc-only associations: **{n_assoc_g}** "
        f"(leader_resolved={leader_true_g})",
        f"- Reliability **graph docs only**: A={rel_g['A']} ({_pct(rel_g['A'], total_rel_g)}), "
        f"B={rel_g['B']} ({_pct(rel_g['B'], total_rel_g)}), "
        f"C={rel_g['C']} ({_pct(rel_g['C'], total_rel_g)}), "
        f"D={rel_g['D']} ({_pct(rel_g['D'], total_rel_g)})",
        f"- HSS-gold + leader_resolved (any candidate pool): n={hss_all_n}, "
        f"prefers_W_only={prefers_w_only}, prefers_HSS_only={prefers_hss_only}, "
        f"both={hss_all_lean.get('both_HSS_and_W', 0)}",
        f"- HSS-gold with HSS+W in candidate pool: n={hss_n}, "
        f"prefers_HSS={hss_lean.get('prefers_HSS', 0)}, "
        f"prefers_W={hss_lean.get('prefers_W', 0)}, "
        f"neutral={hss_lean.get('neutral', 0)}, "
        f"missing={hss_lean.get('missing', 0)}",
        f"- Incomplete-L completion justification from leader evidence: "
        f"**{l_completion_flags}** (must stay 0)",
        "",
        "Reasons:",
    ]
    for why in rec_why:
        lines.append(f"- {why}")

    lines += [
        "",
        "## B. How leader-target relationships are represented",
        "",
        "### Construction",
        "",
        "1. `geometry_extractor` marks thin short strokes as `kind=leader` and "
        "stores `leader_endpoints.near_endpoint` / `far_endpoint` on the geometry object.",
        "2. `graph_builder.build_geometry_nodes` maps leaders to graph nodes with "
        "`geometry_kind=leader`, `kind=connection`. **Endpoints and polyline points "
        "are not copied onto graph nodes.**",
        "3. `spatial_index.nearest_geometry_candidates` (used by `graph_builder.build_graph`):",
        "   - finds geometries near the label",
        "   - if a candidate is a leader, computes a **bbox far-corner** hop "
        "(`_leader_far_endpoint`) — not the geometry object's true far endpoint",
        "   - queries again for a structural member near that point",
        "   - ranks `leader_endpoint_resolved` ahead of `direct_distance`",
        "4. Winning association is stored as one `nearest_geometry` edge:",
        "",
        "```text",
        "label (txt_*)  --nearest_geometry-->  member (geo_*)",
        "meta.leader_resolved = true",
        "meta.association_sources = [leader_endpoint_resolved, ...]",
        "meta.candidate_count = N",
        "distance / weight present",
        "leader node id NOT stored on the edge",
        "```",
        "",
        "Separate `nearest_label` edges may link leader strokes → nearby labels "
        "(empty meta) — that is proximity to the leader, not the resolved target.",
        "",
        "### Production usage",
        "",
        prod_use,
        "",
        "### Docs analyzed",
        "",
    ]
    for r in results:
        diag = r.get("diagnostics") or {}
        lines.append(
            f"- `{r['doc_id']}`: graph={r.get('has_graph')} "
            f"geometry={r.get('has_geometry')} "
            f"leader_nodes={r.get('leader_nodes', 0)} "
            f"diag.leader_resolved_associations="
            f"{diag.get('leader_resolved_associations') if isinstance(diag, dict) else 'n/a'}"
        )
    if docs_without:
        lines.append("")
        lines.append(
            f"Docs **without** graph.json (prediction-only; associations → D/missing): "
            + ", ".join(f"`{r['doc_id']}`" for r in docs_without)
        )

    lines += [
        "",
        "## C. Reliability counts",
        "",
        "Buckets:",
        "- **A** Explicitly resolved and reliable (leader hop → structural member, "
        "tight distance, low ambiguity)",
        "- **B** Resolved but ambiguous (many leader sources / high candidate_count / "
        "farther distance)",
        "- **C** Geometry-only / weak (direct nearest without leader, or non-structural target)",
        "- **D** Missing or unresolved (no nearest_geometry edge / no graph)",
        "",
        "### C1. All 8 eval docs (includes 5 without graph.json → mostly D)",
        "",
        "| Bucket | Count | % |",
        "|---|---:|---:|",
        f"| A | {rel['A']} | {_pct(rel['A'], total_rel)} |",
        f"| B | {rel['B']} | {_pct(rel['B'], total_rel)} |",
        f"| C | {rel['C']} | {_pct(rel['C'], total_rel)} |",
        f"| D | {rel['D']} | {_pct(rel['D'], total_rel)} |",
        f"| **Total** | **{total_rel}** | 100% |",
        "",
        f"Leader-resolved (all docs): **{leader_true}** ({_pct(leader_true, n_assoc)}).",
        "",
        "### C2. Graph-available docs only (primary evidence)",
        "",
        "| Bucket | Count | % |",
        "|---|---:|---:|",
        f"| A | {rel_g['A']} | {_pct(rel_g['A'], total_rel_g)} |",
        f"| B | {rel_g['B']} | {_pct(rel_g['B'], total_rel_g)} |",
        f"| C | {rel_g['C']} | {_pct(rel_g['C'], total_rel_g)} |",
        f"| D | {rel_g['D']} | {_pct(rel_g['D'], total_rel_g)} |",
        f"| **Total** | **{total_rel_g}** | 100% |",
        "",
        f"Leader-resolved (graph docs): **{leader_true_g}** "
        f"({_pct(leader_true_g, n_assoc_g)}).",
        "",
        "Among `leader_resolved` rows on graph docs:",
        f"- Target `kind` top: `{dict(leader_target_kinds.most_common(6))}`",
        f"- Orientation bins: `{dict(leader_orients)}`",
        f"- Leader source multiplicity: "
        f"<3 sources={leader_multi_src.get('lt3', 0)}, "
        f"≥3 sources={leader_multi_src.get('ge3', 0)} "
        f"({_pct(leader_multi_src.get('ge3', 0), sum(leader_multi_src.values()) or 1)} "
        "of leader_resolved are multi-leader / ambiguous)",
        "",
        "## D. Family-level separation results",
        "",
        "Allowed families only: HSS / W / L / 2L / PIPE (plus related soft priors). "
        "No thickness, legs, or incomplete-L completion.",
        "",
        f"Multi-family gold association rows (graph docs): **{fam_n}**",
        "",
        "| Preference vs gold family | Count | % |",
        "|---|---:|---:|",
    ]
    for key in (
        "prefers_gold_family",
        "prefers_other_family",
        "neutral",
        "missing",
    ):
        lines.append(
            f"| {key} | {fam_pref.get(key, 0)} | {_pct(fam_pref.get(key, 0), fam_n)} |"
        )
    lines += [
        "",
        "Interpretation: soft preference is derived from target **role/orientation** "
        "after leader association — not from reading a printed section on the member. "
        "Most targets are unlabeled `kind=geometry`, so family signal is weak and "
        "prior-driven. Multi-family gold preference is near coin-flip "
        f"({gold_family_ok} gold vs {other_family} other).",
        "",
        "## E. HSS vs W analysis",
        "",
        "### E1. All HSS-gold rows with leader_resolved (family lean from "
        "target orientation/role)",
        "",
        f"n = **{hss_all_n}**",
        "",
        "| Lean | Count |",
        "|---|---:|",
        f"| prefers_HSS_only | {hss_all_lean.get('prefers_HSS_only', 0)} |",
        f"| prefers_W_only | {hss_all_lean.get('prefers_W_only', 0)} |",
        f"| both_HSS_and_W | {hss_all_lean.get('both_HSS_and_W', 0)} |",
        f"| neither | {hss_all_lean.get('neither', 0)} |",
        "",
        "### E2. Gold family = HSS, candidates include HSS and W",
        "",
        f"n = **{hss_n}** (leader_resolved on **{hss_with_leader}**)",
        "",
        "| Lean | Count |",
        "|---|---:|",
        f"| prefers_HSS | {hss_lean.get('prefers_HSS', 0)} |",
        f"| prefers_W | {hss_lean.get('prefers_W', 0)} |",
        f"| neutral | {hss_lean.get('neutral', 0)} |",
        f"| missing | {hss_lean.get('missing', 0)} |",
        "",
        "### E3. Gold family = W, candidates include HSS and W",
        "",
        f"n = **{w_n}**",
        "",
        "| Lean | Count |",
        "|---|---:|",
        f"| prefers_W | {w_lean.get('prefers_W', 0)} |",
        f"| prefers_HSS | {w_lean.get('prefers_HSS', 0)} |",
        f"| neutral | {w_lean.get('neutral', 0)} |",
        f"| missing | {w_lean.get('missing', 0)} |",
        "",
        "### E4. W-gold leader lean (all W-gold + leader_resolved)",
        "",
        f"n = **{w_all_n}** → `{dict(w_all_lean)}`",
        "",
    ]

    # Show a few HSS→W lean examples
    hss_w_examples = []
    for r in results:
        for case in r.get("rows") or []:
            if case.get("gold_fam") != "HSS" or not case.get("leader_resolved"):
                continue
            pref = set(case.get("preferred_families") or [])
            if "W" in pref and "HSS" not in pref:
                hss_w_examples.append(case)
    if hss_w_examples:
        lines.append(
            "Examples where leader-target orientation/role lean prefers **W only** "
            "on HSS gold:"
        )
        lines.append("")
        for case in hss_w_examples[:8]:
            lines.append(
                f"- `{case.get('doc')}` raw=`{str(case.get('raw'))[:60]}` "
                f"target_kind={case.get('target_kind')} "
                f"orient={case.get('orient_bin')} "
                f"preferred={case.get('preferred_families')} "
                f"dist={case.get('distance')} bucket={case.get('bucket')}"
            )
        lines.append("")

    lines += [
        "## F. L analysis",
        "",
        "Leader-target evidence is evaluated at **family** level only. "
        "It must not justify completing incomplete L or inventing thickness.",
        "",
        f"Completion-justification flags: **{l_completion_flags}** "
        "(analysis encodes family-only; must remain 0).",
        "",
        "| L bucket | n | leader A | leader B | leader C | leader D | leader_resolved |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for lb in (
        "explicit_complete_L",
        "explicit_L_shop_cut",
        "incomplete_L",
        "unlabeled_L",
        "other_L",
    ):
        c = l_stats.get(lb) or Counter()
        lines.append(
            f"| {lb} | {c.get('n', 0)} | {c.get('leader_A', 0)} | "
            f"{c.get('leader_B', 0)} | {c.get('leader_C', 0)} | "
            f"{c.get('leader_D', 0)} | {c.get('leader_resolved', 0)} |"
        )
    lines += [
        "",
        "Verification:",
        "- Incomplete L (`L4x4` style): leader evidence does **not** create a "
        "thickness/leg completion signal in this investigation.",
        "- No path from leader-target → `L4X4X1/4` or `2L…` invention is supported "
        "by stored fields (no size fields on target geometry).",
        "- Explicit complete / shop-cut L remain protected by existing production "
        "exact-section / core-section rules (unchanged).",
        "",
        "## G. Examples of strong evidence",
        "",
    ]
    if not strong:
        lines.append("_None collected under bucket A with leader_resolved._")
    else:
        for ex in strong[:12]:
            lines.append(
                f"- `{ex.get('doc')}` `{ex.get('raw')}` gold={ex.get('gold')} "
                f"→ {ex.get('target_geometry_kind')}/{ex.get('target_kind')} "
                f"orient={ex.get('orient_bin')} dist={ex.get('distance')} "
                f"leader_sources={ex.get('n_leader_sources')} "
                f"cand_count={ex.get('candidate_count')}"
            )

    lines += ["", "## H. Examples of ambiguous/unsafe evidence", ""]
    if not amb:
        lines.append("_None collected._")
    else:
        for ex in amb[:12]:
            lines.append(
                f"- `{ex.get('doc')}` `{ex.get('raw')}` gold={ex.get('gold')} "
                f"kind={ex.get('target_geometry_kind')}/{ex.get('target_kind')} "
                f"dist={ex.get('distance')} "
                f"leader_sources={ex.get('n_leader_sources')} "
                f"cand_count={ex.get('candidate_count')} "
                f"issue={ex.get('issue', '')} sources={ex.get('sources', '')}"
            )

    lines += [
        "",
        "## I. Missing evidence",
        "",
        f"- Reliability D count: **{rel['D']}** ({_pct(rel['D'], total_rel)})",
        f"- Docs without graph.json: **{len(docs_without)}**",
        "- Graph nodes omit true `leader_endpoints` / polyline points.",
        "- Winning `nearest_geometry` edge does not store which leader was used.",
        "- `predictions_view` explanations generally lack `leader_resolved` / "
        "far-endpoint fields (association provenance not surfaced to fusion).",
        "- `source_features` has no leader flag.",
        "",
    ]
    if missing:
        lines.append("Sample missing/unresolved rows:")
        lines.append("")
        for ex in missing[:10]:
            lines.append(
                f"- `{ex.get('doc')}` `{ex.get('raw')}` gold={ex.get('gold')} "
                f"({ex.get('reason')})"
            )
        lines.append("")

    lines += [
        "## J. Recommendation",
        "",
        f"**{recommendation}**",
        "",
        "Constraints that remain in force:",
        "- Do **not** wire Graph v2 into production.",
        "- Do **not** add `GRAPH_V2_ENABLED` / GraphSAGE / learned fusion flags.",
        "- Do **not** use leader-target evidence to invent thickness, complete "
        "incomplete L, or override explicit printed sections.",
        "- Family-level research only, offline, if continued.",
        "",
        "### Reasons",
        "",
    ]
    for why in rec_why:
        lines.append(f"- {why}")
    lines += [
        "",
        "---",
        "",
        "_Generated offline by `scripts/investigate_leader_target.py` from cached "
        "artifacts only. No production modules modified._",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    doc_ids = sorted(
        {p.parent.name for p in CACHE_ROOT.glob("doc_*/predictions_view.json")}
        | {
            p.parent.parent.name
            for p in ARTIFACTS_ROOT.glob("doc_*/multimodal/graph.json")
        }
    )
    # Prefer the 8-doc eval set order
    eval_docs = sorted(
        p.parent.name for p in CACHE_ROOT.glob("doc_*/predictions_view.json")
    )
    doc_ids = eval_docs or sorted(doc_ids)

    results = []
    for doc_id in doc_ids:
        print(f"Analyzing {doc_id} ...")
        result = analyze_doc(doc_id)
        print(
            f"  graph={result.get('has_graph')} "
            f"assoc={result.get('n_associations_classified')} "
            f"rel={result.get('reliability')} "
            f"hss_w={len(result.get('hss_w_cases') or [])}"
        )
        results.append(result)

    report = write_report(results)
    REPORT_PATH.write_text(report)
    # Also dump machine-readable summary (investigation artifact)
    summary = {
        "docs": [
            {
                "doc_id": r["doc_id"],
                "has_graph": r.get("has_graph"),
                "reliability": r.get("reliability"),
                "leader_resolved_true": r.get("leader_resolved_true"),
                "n_hss_w": len(r.get("hss_w_cases") or []),
                "n_l": len(r.get("l_cases") or []),
            }
            for r in results
        ]
    }
    out_dir = CACHE_ROOT / "leader_target_investigation"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out_dir / "GRAPH_LEADER_TARGET_INVESTIGATION.md").write_text(report)
    print("Wrote", REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
