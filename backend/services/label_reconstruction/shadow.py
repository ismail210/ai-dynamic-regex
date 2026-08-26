"""Shadow-mode entry point for damaged-label reconstruction (Part O/P).

This is the intended eventual inference flow:

    raw text (never overwritten)
        -> conservative normalization
        -> exact AISC match? --yes--> deterministic result
                              --no--> deterministic candidate generation
                                      -> [shadow] learned ranker scores candidates
                                      -> top-K, confidence/margin

``ML_LABEL_RANKER_ENABLED`` (default false) gates whether the ranker's
ordering is ever used for ``selected_prediction`` -- the field a real caller
would act on. ``ML_LABEL_RANKER_SHADOW`` (default false, independent flag)
gates whether the ranker runs at all and its output is logged; it can be on
while ``ML_LABEL_RANKER_ENABLED`` stays off, which is exactly shadow mode:
the ranker runs, disagreement with the deterministic pick is recorded, and
NOTHING about the returned prediction changes. With both flags off (the
default) this module still normalizes/generates candidates deterministically
but never imports xgboost or touches the shadow log at all.

Live analyze traffic reaches this module only through
``services.prediction.label_ranker_hook`` (never via a direct import from
orchestrator / pipeline / routers — see the isolation tests). With both
flags at defaults the hook is a no-op and production behavior is unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import settings
from services.database_loader import is_catalog_label
from services.label_reconstruction.candidates import (
    CandidateSet,
    conservative_normalize,
    generate_candidates,
    ineligible_for_section_reconstruction,
    is_missing_thickness_hss,
)


@dataclass
class LabelReconstructionResult:
    raw_text: str
    normalized_text: str
    parsed_family: str
    candidate_labels: List[str]
    ranking_scores: Optional[List[float]]
    selected_prediction: Optional[str]
    reason: str
    model_version: Optional[str]
    shadow: Optional[dict] = field(default=None)

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "parsed_family": self.parsed_family,
            "candidate_labels": self.candidate_labels,
            "ranking_scores": self.ranking_scores,
            "selected_prediction": self.selected_prediction,
            "reason": self.reason,
            "model_version": self.model_version,
            "shadow": self.shadow,
        }


def _append_shadow_log(entry: dict) -> None:
    path = settings.ml_label_ranker_shadow_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")


def reconstruct(
    raw_text: str,
    *,
    corruption_type_hint: Optional[List[str]] = None,
    live_prediction: Optional[str] = None,
) -> LabelReconstructionResult:
    """Never invents a label -- ``selected_prediction`` is always either an
    exact catalog match or the deterministic generator's top pick, UNLESS
    ``ML_LABEL_RANKER_ENABLED`` is explicitly true, in which case it is the
    ranker's top pick from that SAME catalog-valid candidate set.

    ``live_prediction`` is optional analyze-path context (the multimodal
    section already chosen). When shadow logging is on it is recorded for
    offline comparison; it never becomes ``selected_prediction`` by itself.
    """

    normalized = conservative_normalize(raw_text)

    if ineligible_for_section_reconstruction(raw_text, normalized):
        return LabelReconstructionResult(
            raw_text=raw_text,
            normalized_text=normalized,
            parsed_family="",
            candidate_labels=[],
            ranking_scores=None,
            selected_prediction=None,
            reason="no_candidates",
            model_version=None,
        )

    if is_catalog_label(normalized):
        return LabelReconstructionResult(
            raw_text=raw_text,
            normalized_text=normalized,
            parsed_family="",
            candidate_labels=[normalized],
            ranking_scores=None,
            selected_prediction=normalized,
            reason="exact_match",
            model_version=None,
        )

    candidate_set: CandidateSet = generate_candidates(raw_text)
    deterministic_pick = candidate_set.candidates[0] if candidate_set.candidates else None
    # Missing-thickness square/rect HSS is a review set, never a unique pick.
    if is_missing_thickness_hss(normalized):
        return LabelReconstructionResult(
            raw_text=raw_text,
            normalized_text=normalized,
            parsed_family=candidate_set.family,
            candidate_labels=candidate_set.candidates,
            ranking_scores=None,
            selected_prediction=None,
            reason="no_candidates",
            model_version=None,
        )
    selected = deterministic_pick
    reason = "deterministic_top_candidate" if deterministic_pick else "no_candidates"
    model_version = None
    ranking_scores: Optional[List[float]] = None
    shadow_payload: Optional[dict] = None

    if (settings.ml_label_ranker_enabled or settings.ml_label_ranker_shadow) and candidate_set.candidates:
        from services.label_reconstruction.ranker import get_active_ranker

        ranker = get_active_ranker()
        if ranker is not None:
            # RAW text, not `normalized` -- the ranker was trained with
            # pairwise "query" = raw_corrupted text (see
            # generate_label_corruption_dataset.py's build_pairwise_rows),
            # so scoring with the normalized string here would be an
            # inference/training preprocessing mismatch: the exact failure
            # mode this package's own design docs warn about elsewhere.
            scores = ranker.score(
                raw_text,
                candidate_set.candidates,
                generation_reasons=candidate_set.generation_reasons,
                fuzzy_ranks=getattr(candidate_set, "fuzzy_ranks", None),
            )
            ranked_pairs = sorted(
                zip(candidate_set.candidates, scores), key=lambda pair: -pair[1]
            )
            ranker_pick = ranked_pairs[0][0] if ranked_pairs else None
            margin = (
                ranked_pairs[0][1] - ranked_pairs[1][1]
                if len(ranked_pairs) > 1
                else ranked_pairs[0][1]
                if ranked_pairs
                else None
            )

            if settings.ml_label_ranker_shadow:
                shadow_payload = {
                    "current_prediction": deterministic_pick,
                    "ml_prediction": ranker_pick,
                    "disagreement": ranker_pick != deterministic_pick,
                    "top_k_candidates": [label for label, _score in ranked_pairs],
                    "ranking_scores": [round(score, 4) for _label, score in ranked_pairs],
                    "margin": round(margin, 4) if margin is not None else None,
                    "corruption_type_hint": corruption_type_hint,
                    "live_prediction": live_prediction,
                    "live_disagreement": (
                        bool(live_prediction)
                        and ranker_pick is not None
                        and ranker_pick != live_prediction
                    ),
                    "model_version": ranker.version_id,
                    "logged_at": datetime.now(timezone.utc).isoformat(),
                }
                _append_shadow_log(shadow_payload)

            if settings.ml_label_ranker_enabled:
                selected = ranker_pick
                reason = "learned_ranker_top_candidate"
                model_version = ranker.version_id
                ranking_scores = [round(score, 4) for _label, score in ranked_pairs]

    return LabelReconstructionResult(
        raw_text=raw_text,
        normalized_text=normalized,
        parsed_family=candidate_set.family,
        candidate_labels=candidate_set.candidates,
        ranking_scores=ranking_scores,
        selected_prediction=selected,
        reason=reason,
        model_version=model_version,
        shadow=shadow_payload,
    )
