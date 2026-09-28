"""Compare new retrieval candidates vs production nearest_geometry edges (read-only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def index_nearest_geometry_edges(
    graph: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Map text ``source_id`` (token_id) -> nearest_geometry edge + target geo id."""
    nodes = {n["node_id"]: n for n in (graph.get("nodes") or []) if n.get("node_id")}
    # text node_id -> source_id (token_*)
    text_source: Dict[str, str] = {}
    for node in nodes.values():
        if str(node.get("kind") or node.get("base_kind") or "").lower() in {
            "text",
            "steel_section",
            "beam",
            "column",
            "brace",
            "plate",
        } or str(node.get("node_id") or "").startswith("txt_"):
            sid = node.get("source_id")
            if sid:
                text_source[node["node_id"]] = str(sid)

    geo_by_node = {
        nid: n
        for nid, n in nodes.items()
        if str(n.get("kind") or "").lower() in {"geometry", "connection", "leader", "beam", "column", "brace"}
        or str(nid).startswith("geo_")
    }

    out: Dict[str, Dict[str, Any]] = {}
    for edge in graph.get("edges") or []:
        if edge.get("relationship") != "nearest_geometry":
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        token_id = text_source.get(src)
        if not token_id:
            continue
        geo_node = geo_by_node.get(tgt) or nodes.get(tgt) or {}
        out[token_id] = {
            "edge_id": edge.get("edge_id"),
            "text_node_id": src,
            "geometry_node_id": tgt,
            "geometry_id": geo_node.get("source_id") or geo_node.get("geometry_id") or tgt,
            "distance": edge.get("distance"),
            "page_number": edge.get("page_number"),
            "meta": edge.get("meta") or {},
            "geometry_kind": geo_node.get("geometry_kind") or geo_node.get("kind"),
            "geometry_bbox": geo_node.get("bbox"),
        }
    return out


def compare_row(
    label: Dict[str, Any],
    current: Optional[Dict[str, Any]],
    candidates: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Descriptive agreement / disagreement — no 'better' score without GT."""
    token_id = label.get("token_id") or label.get("id")
    text = label.get("text") or label.get("normalized_text") or ""
    top = candidates[0] if candidates else None
    current_gid = (current or {}).get("geometry_id")
    cand_ids = [c["geometry_id"] for c in candidates if c.get("geometry_id")]

    if not current and not candidates:
        status = "unavailable"
    elif not current and candidates:
        status = "extra_candidates_only"
    elif current and not candidates:
        status = "missing_retrieval"
    elif current_gid and current_gid in cand_ids:
        status = "agreement"
    elif current_gid and top and current_gid == top.get("geometry_id"):
        status = "agreement"
    elif current_gid and cand_ids:
        status = "disagreement"
    else:
        status = "ambiguous"

    # Ambiguous if many near-ties at top
    if status in {"agreement", "disagreement", "extra_candidates_only"} and len(candidates) >= 2:
        d0 = float(candidates[0].get("bbox_distance") or 0)
        d1 = float(candidates[1].get("bbox_distance") or 0)
        if abs(d1 - d0) <= 8.0:
            status = "ambiguous" if status != "agreement" else "agreement_ambiguous_neighborhood"

    return {
        "token_id": token_id,
        "text": text,
        "page": label.get("page"),
        "label_bbox": label.get("bbox"),
        "label_region_id": label.get("region_id"),
        "status": status,
        "current_association": current,
        "new_top_candidate": top,
        "new_candidates": list(candidates),
        "candidate_ids": cand_ids,
    }


def summarize_comparisons(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    from collections import Counter

    counts = Counter(r["status"] for r in rows)
    return {
        "label_count": len(rows),
        "status_counts": dict(counts),
        "agreement": counts.get("agreement", 0) + counts.get("agreement_ambiguous_neighborhood", 0),
        "disagreement": counts.get("disagreement", 0),
        "missing_retrieval": counts.get("missing_retrieval", 0),
        "extra_candidates_only": counts.get("extra_candidates_only", 0),
        "ambiguous": counts.get("ambiguous", 0) + counts.get("agreement_ambiguous_neighborhood", 0),
        "unavailable": counts.get("unavailable", 0),
    }
