"""
One transparent, final ranking stage over candidate steel-section labels.

Consolidates the same signals the pipeline already computes — text/model
similarity, geometry, graph/GNN, engineering-rule evidence (from
``services.exact_section_predictor`` and
``services.multimodal.modular_fusion``) plus deterministic wildcard-mask
candidates (``services.wildcard_matcher``) and AISC catalog validity
(``services.database_loader``) — into a single per-candidate breakdown with
human-readable match reasons, instead of weighted sums applied silently at
several disconnected pipeline stages.

Weights mirror ``services.multimodal.modular_fusion.ATTENTION_PRIORS`` — this
module documents and re-presents the existing attention-fusion decision, it
does not compute a second, competing ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.database_loader import is_catalog_label
from services.multimodal.modular_fusion import ATTENTION_PRIORS

# Top two candidates within this margin are a near-tie: the system must not
# silently pick a winner and hide that it was a close call.
NEAR_TIE_MARGIN = 0.04


@dataclass
class RankedCandidate:
    label: str
    catalog_valid: bool
    mask_match: bool
    text_similarity: float
    geometry_score: float
    graph_score: float
    engineering_score: float
    combined_score: float
    match_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "catalog_valid": self.catalog_valid,
            "mask_match": self.mask_match,
            "text_similarity": round(self.text_similarity, 4),
            "geometry_score": round(self.geometry_score, 4),
            "graph_score": round(self.graph_score, 4),
            "engineering_score": round(self.engineering_score, 4),
            "combined_score": round(self.combined_score, 4),
            "match_reasons": list(self.match_reasons),
        }


@dataclass
class RankingResult:
    candidates: List[RankedCandidate]
    weights: Dict[str, float]
    near_tie: bool
    near_tie_margin: Optional[float]

    def to_dict(self) -> dict:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "weights": dict(self.weights),
            "near_tie": self.near_tie,
            "near_tie_margin": (
                round(self.near_tie_margin, 4)
                if self.near_tie_margin is not None
                else None
            ),
        }


def build_ranking(
    *,
    fusion_candidate_scores: Optional[List[Dict[str, Any]]] = None,
    wildcard_candidates: Optional[List[Any]] = None,
    limit: int = 8,
) -> RankingResult:
    """Merge fusion candidate scores and wildcard-mask candidates into one
    ranked, catalog-checked candidate list. A wildcard-mask hit that is also
    present in the fusion candidates is merged (not duplicated); a
    wildcard-only hit (no text/geometry/graph signal at all) is kept with its
    own zeroed evidence fields, matching the deterministic nature of a mask
    match."""

    by_label: Dict[str, RankedCandidate] = {}

    for item in fusion_candidate_scores or []:
        label = str(item.get("shape") or "")
        if not label:
            continue
        modality = item.get("modality_scores") or {}
        text_score = float(modality.get("text") or 0.0)
        geometry_score = float(modality.get("geometry") or 0.0)
        graph_score = float(modality.get("graph") or 0.0)
        engineering_score = float(modality.get("engineering_rules") or 0.0)
        catalog_valid = is_catalog_label(label)
        reasons = [
            "Label exists in the loaded AISC catalog"
            if catalog_valid
            else "Label does not exist in the loaded AISC catalog"
        ]
        if text_score:
            reasons.append(f"Text evidence {text_score:.0%}")
        if geometry_score:
            reasons.append(f"Geometry evidence {geometry_score:.0%}")
        if graph_score:
            reasons.append(f"Graph evidence {graph_score:.0%}")
        by_label[label] = RankedCandidate(
            label=label,
            catalog_valid=catalog_valid,
            mask_match=False,
            text_similarity=text_score,
            geometry_score=geometry_score,
            graph_score=graph_score,
            engineering_score=engineering_score,
            combined_score=float(item.get("score") or 0.0),
            match_reasons=reasons,
        )

    for candidate in wildcard_candidates or []:
        payload = (
            candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
        )
        label = str(payload.get("label") or "")
        if not label:
            continue
        existing = by_label.get(label)
        if existing:
            existing.mask_match = True
            existing.catalog_valid = existing.catalog_valid or bool(
                payload.get("catalog_valid")
            )
            existing.match_reasons = list(
                dict.fromkeys(
                    existing.match_reasons + list(payload.get("match_reasons") or [])
                )
            )
        else:
            by_label[label] = RankedCandidate(
                label=label,
                catalog_valid=bool(payload.get("catalog_valid")),
                mask_match=True,
                text_similarity=0.0,
                geometry_score=0.0,
                graph_score=0.0,
                engineering_score=0.0,
                combined_score=0.0,
                match_reasons=list(payload.get("match_reasons") or []),
            )

    ranked = sorted(
        by_label.values(), key=lambda item: (-item.combined_score, item.label)
    )[: max(1, limit)]

    near_tie = False
    margin: Optional[float] = None
    if len(ranked) >= 2 and ranked[0].combined_score > 0:
        margin = ranked[0].combined_score - ranked[1].combined_score
        near_tie = margin < NEAR_TIE_MARGIN

    return RankingResult(
        candidates=ranked,
        weights=dict(ATTENTION_PRIORS),
        near_tie=near_tie,
        near_tie_margin=margin,
    )
