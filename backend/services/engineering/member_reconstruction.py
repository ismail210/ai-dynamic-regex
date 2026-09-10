"""Phase C -- physical member reconstruction pipeline (SHADOW ONLY).

Chains the deterministic pieces:

    framing pages (from DrawingIntelligenceProfile)
      -> W-member candidates (framing_member_candidates)
      -> structural graph V2 with member nodes (member_graph_v2)
      -> explicit section labels attached as SEEDS
      -> repeated-bay clustering
      -> multi-seed / scoped-TYP section propagation
      -> shadow tiers  (SHADOW_AUTO / SHADOW_REVIEW / SHADOW_WEAK / SHADOW_REJECTED)
      -> shadow takeoff  (a SEPARATE histogram; never added to production counts)

Nothing here is written into ``predictions``, the review queue, exports, the
canonical takeoff, or the graph the orchestrator consumes. It is gated by
``MEMBER_RECONSTRUCTION_SHADOW_ENABLED`` (default off) and produces a report
object for evaluation and the (future) shadow UI. Section assignment only ever
uses the existing high-precision explicit-label system as trusted seeds --
never the ground-truth Excel.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from services.database_loader import catalog_form
from services.engineering import framing_member_candidates as fmc
from services.engineering import member_graph_v2 as mgv2

SHADOW_AUTO = "SHADOW_AUTO"
SHADOW_REVIEW = "SHADOW_REVIEW"
SHADOW_WEAK = "SHADOW_WEAK"
SHADOW_REJECTED = "SHADOW_REJECTED"

RECONSTRUCTION_VERSION = "member_reconstruction_v1_shadow"

# section-confidence thresholds
_SEED_STRONG = 0.8
_MULTI_SEED_MIN = 2
_EXISTENCE_WEAK_FLOOR = 0.45
_EXISTENCE_AUTO_FLOOR = 0.6


# --------------------------------------------------------------------------
# seed labels from the production predictions
# --------------------------------------------------------------------------
def _seed_label_nodes(
    predictions: List[Dict[str, Any]],
    document: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Trusted explicit W-section labels -> label nodes for the graph. Only
    real, catalog-valid, explicitly-read W designations (never a synthetic
    token, never a low-confidence fusion pick).

    The served prediction contract drops ``page`` / ``bbox``, so positional
    data is recovered by joining back to ``document["engineering_tokens"]`` on
    the token id.
    """

    token_pos: Dict[str, Dict[str, Any]] = {}
    for tok in (document or {}).get("engineering_tokens") or []:
        tid = str(tok.get("token_id") or "")
        if tid:
            token_pos[tid] = {"bbox": tok.get("bbox"), "page": tok.get("page")}

    seeds: List[Dict[str, Any]] = []
    for pred in predictions:
        object_id = str(pred.get("object_id") or pred.get("token_id") or "")
        if not object_id.startswith("token_"):
            continue
        raw = pred.get("raw_text") or pred.get("original_token") or ""
        section = catalog_form(str(raw).replace(" ", "").upper())
        if not section or not section.startswith("W"):
            continue
        comparison = pred.get("comparison") or {}
        if comparison.get("match_status") not in ("exact_match", "normalized_match", "corrected_prediction"):
            if catalog_form(str(pred.get("section") or "").replace(" ", "").upper()) != section:
                continue
        pos = token_pos.get(object_id, {})
        bbox = pred.get("bbox") or pos.get("bbox") or []
        page = int(pred.get("page") or pos.get("page") or 0)
        centre = (
            [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]
            if bbox and len(bbox) >= 4 else None
        )
        seeds.append({
            "node_id": f"seed_{object_id}",
            "source_id": object_id,
            "kind": "steel_section_label",
            "page_number": page,
            "center": centre,
            "section": section,
        })
    return seeds


# --------------------------------------------------------------------------
# repeated-bay clustering (geometry/topology only, NOT labels)
# --------------------------------------------------------------------------
def _cluster_bays(candidates: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group candidates on the same page that share orientation and a similar
    span length into repeated-framing clusters."""

    clusters: Dict[str, List[str]] = defaultdict(list)
    by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for cand in candidates:
        by_page[cand["page"]].append(cand)
    for page, items in by_page.items():
        for cand in items:
            axis = "H" if abs((cand["orientation_deg"] % 180.0) - 90.0) > 45.0 else "V"
            span_bucket = int(round(cand["length_pdf"] / 40.0))
            key = f"p{page}_{axis}_{span_bucket}"
            clusters[key].append(cand["member_candidate_id"])
            cand["repeated_cluster_id"] = key
            cand["same_bay_cluster_id"] = key
    return {k: v for k, v in clusters.items() if len(v) >= 2}


# --------------------------------------------------------------------------
# section propagation
# --------------------------------------------------------------------------
def _propagate_sections(
    candidates: List[Dict[str, Any]],
    graph: Dict[str, Any],
    clusters: Dict[str, List[str]],
    typ_rules: List[Dict[str, Any]],
) -> Dict[str, int]:
    by_id = {c["member_candidate_id"]: c for c in candidates}
    node_to_cand = {c["graph_node_id"]: c for c in candidates if c.get("graph_node_id")}

    # 1. direct label_to_member seeds
    seed_by_member: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for edge in graph.get("edges") or []:
        if edge.get("relationship") != "label_to_member":
            continue
        member_node = edge["target"]
        cand = node_to_cand.get(member_node)
        if not cand:
            continue
        seed_node = edge["source"]
        section = _section_of_seed(graph, seed_node)
        if section:
            seed_by_member[cand["member_candidate_id"]].append((section, float(edge.get("confidence") or 0.0)))

    tally = Counter()
    for mid, seeds in seed_by_member.items():
        cand = by_id[mid]
        strong = [s for s, c in seeds if c >= _SEED_STRONG]
        if strong and len(set(strong)) == 1:
            cand["section_candidate"] = strong[0]
            cand["section_confidence"] = 0.85
            cand["section_evidence"] = ["direct_label_unambiguous"]
            cand["seed_label_id"] = mid
            tally["direct_seed"] += 1
        elif seeds:
            best = max(seeds, key=lambda t: t[1])
            cand["section_candidate"] = best[0]
            cand["section_confidence"] = min(0.55, best[1])
            cand["section_evidence"] = ["nearest_label_only"]
            tally["weak_seed"] += 1

    # 2. multi-seed cluster propagation
    for key, member_ids in clusters.items():
        seeded = [
            (mid, by_id[mid]["section_candidate"])
            for mid in member_ids
            if by_id[mid].get("section_candidate")
            and by_id[mid].get("section_confidence", 0) >= _SEED_STRONG - 0.05
            and "direct_label_unambiguous" in by_id[mid].get("section_evidence", [])
        ]
        sections = {section for _mid, section in seeded}
        if len(seeded) >= _MULTI_SEED_MIN and len(sections) == 1:
            section = sections.pop()
            for mid in member_ids:
                cand = by_id[mid]
                if cand.get("section_candidate") == section:
                    continue
                if cand.get("section_candidate") and cand.get("section_confidence", 0) >= _SEED_STRONG:
                    continue  # explicit conflict -- never overwrite
                cand["section_candidate"] = section
                cand["section_confidence"] = 0.75
                cand["section_evidence"] = ["repeated_cluster_multi_seed", key]
                cand["provenance"]["propagation"] = "RB_MULTI_SEED"
                tally["cluster_propagated"] += 1
        elif len(sections) > 1:
            tally["cluster_conflict_blocked"] += 1

    # 3. scoped TYP rules (structured, from DrawingIntelligenceProfile -- never prose)
    typ_by_page: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for rule in typ_rules:
        for page in rule.get("framing_pages") or rule.get("pages") or []:
            typ_by_page[int(page)].append(rule)
    for cand in candidates:
        if cand.get("section_candidate") and cand.get("section_confidence", 0) >= 0.7:
            continue
        for rule in typ_by_page.get(cand["page"], []):
            near = rule.get("near_sections") or []
            if len(near) == 1 and near[0].startswith("W"):
                cand["section_candidate"] = near[0]
                cand["section_confidence"] = 0.6
                cand["section_evidence"] = ["scoped_typ_rule", f"page_{cand['page']}"]
                cand["typ_rule_id"] = f"typ_p{cand['page']}"
                cand["provenance"]["propagation"] = "SCOPED_TYP"
                tally["typ_propagated"] += 1
                break

    return dict(tally)


def _section_of_seed(graph: Dict[str, Any], seed_node_id: str) -> Optional[str]:
    for node in graph.get("nodes") or []:
        if node.get("node_id") == seed_node_id:
            return node.get("section")
    return None


# --------------------------------------------------------------------------
# shadow tiers + shadow takeoff
# --------------------------------------------------------------------------
def _assign_tiers(candidates: List[Dict[str, Any]]) -> None:
    for cand in candidates:
        exist = cand["existence_confidence"]
        sect_conf = cand.get("section_confidence", 0.0)
        if exist < _EXISTENCE_WEAK_FLOOR:
            cand["status"] = SHADOW_WEAK
        elif cand.get("section_candidate") and sect_conf >= 0.72 and exist >= _EXISTENCE_AUTO_FLOOR:
            cand["status"] = SHADOW_AUTO
        elif exist >= _EXISTENCE_AUTO_FLOOR:
            cand["status"] = SHADOW_REVIEW
        else:
            cand["status"] = SHADOW_WEAK


def _shadow_takeoff(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    resolved = Counter()
    for cand in candidates:
        if cand["status"] == SHADOW_AUTO and cand.get("section_candidate"):
            resolved[cand["section_candidate"]] += 1
    tiers = Counter(c["status"] for c in candidates)
    return {
        "shadow_physical_member_count": len(candidates),
        "shadow_resolved_count": int(tiers[SHADOW_AUTO]),
        "shadow_review_count": int(tiers[SHADOW_REVIEW]),
        "shadow_weak_count": int(tiers[SHADOW_WEAK]),
        "shadow_section_histogram": dict(resolved),
    }


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def reconstruct_members_shadow(
    document: Dict[str, Any],
    geometry: Dict[str, Any],
    *,
    drawing_intelligence: Optional[Dict[str, Any]] = None,
    predictions: Optional[List[Dict[str, Any]]] = None,
    base_graph: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the whole shadow pipeline. Never raises for well-formed input;
    returns a report dict. Does not mutate any argument's production fields."""

    predictions = predictions or []
    di = drawing_intelligence or (document.get("legend_profile") or {}).get("drawing_intelligence") or {}
    if not di.get("page_categories"):
        # a cached document may carry a pre-v6 legend profile with no drawing
        # intelligence -- build the deterministic profile on the spot (cheap,
        # no model, no network).
        try:
            from services.engineering.drawing_intelligence import build_drawing_intelligence

            lp = document.get("legend_profile") or {}
            di = build_drawing_intelligence(
                document,
                context_pages=lp.get("context_pages"),
                abbreviation_rules=lp.get("abbreviation_rules"),
            )
        except Exception:  # noqa: BLE001
            di = {}

    eligible = fmc.framing_pages(di)
    detection = fmc.detect_w_member_candidates(geometry, document, eligible_pages=eligible)
    candidates = detection["candidates"]

    seed_nodes = _seed_label_nodes(predictions, document)
    graph = base_graph or {"nodes": [], "edges": []}
    graph_v2 = mgv2.augment_graph_with_members(graph, candidates, label_nodes=seed_nodes)
    # register the seed label nodes on the graph so propagation can read each
    # ``label_to_member`` edge back to its section
    graph_v2["nodes"].extend({**seed} for seed in seed_nodes)

    clusters = _cluster_bays(candidates)
    typ_rules = _typ_rules_from_di(di)
    propagation = _propagate_sections(candidates, graph_v2, clusters, typ_rules)
    _assign_tiers(candidates)
    shadow_takeoff = _shadow_takeoff(candidates)
    connectivity = mgv2.member_connectivity(graph_v2)

    return {
        "version": RECONSTRUCTION_VERSION,
        "eligible_pages": detection["eligible_pages"],
        "candidates": candidates,
        "detection": {
            "candidate_count": len(candidates),
            "by_page": detection["by_page"],
            "rejected": detection["rejected"],
            "raw_segments_kept": detection["raw_segments_kept"],
        },
        "seeds": {"label_nodes": len(seed_nodes)},
        "clusters": {"count": len(clusters), "sizes": {k: len(v) for k, v in clusters.items()}},
        "propagation": propagation,
        "graph_connectivity": connectivity,
        "shadow_takeoff": shadow_takeoff,
    }


def _typ_rules_from_di(di: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for insight in di.get("typical_conditions") or []:
        detail = insight.get("detail") or {}
        if not detail.get("present"):
            continue
        rules.append({
            "keyword": detail.get("keyword"),
            "pages": detail.get("pages") or [],
            "framing_pages": detail.get("framing_pages") or [],
            "near_sections": detail.get("near_sections") or [],
        })
    return rules
