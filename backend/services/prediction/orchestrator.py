"""
AI-primary prediction orchestrator.

All production prediction entry points should call ``predict_token`` or
``predict_from_context``. The database never selects ``family`` or ``section``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from config import settings
from services.component_tracker import allocate_component_id
from services.database_loader import (
    catalog_form,
    catalog_version as aisc_catalog_version,
    lookup_shape,
    search_similar_shapes,
)
from services.engineering.rule_engine import evaluate_engineering_rules
from services.engineering.document_prior import apply_prior_to_candidates
from services.entity_taxonomy import (
    CATEGORY_LABELS,
    CATEGORY_PLATE,
    EntityClassification,
    resolve_entity,
)
from services.exact_section_predictor import (
    catalog_valid_exact_section,
    predict_exact_sections,
    predict_exact_sections_for_labels,
)
from services.hss_completion import (
    detect_missing_thickness_hss,
    hss_completion_candidates,
)
from services.section_parser import plausible_against_ocr
from services.feature_extractor import extract_structural_features
from services.model_predictor import predict_with_confidence
from services.multimodal.correction_engine import (
    detect_extraction_issues,
    suggest_token_corrections,
)
from services.multimodal.feature_providers import (
    GeometryFeatureProvider,
    GraphFeatureProvider,
)
from services.multimodal.encoder_registry import encoder_registry
from services.multimodal.modular_fusion import unified_multimodal_fusion
from services.annotation.normalize import compact_normalize
from services.annotation.parser import interpret_annotation
from services.annotation.service import interpret_token_annotation
from services.annotation.taxonomy import (
    AnnotationType,
    Understandability,
    annotation_type_value,
    requires_review,
    understandability_value,
)
from services.multimodal.encoder_contracts import (
    AttentionResult,
    FusedFeatures,
    UnifiedFusionResult,
)
from services.annotation.model_governance import model_may_influence
from services.prediction.calibration import calibrate_score
from services.prediction.label_ranker_hook import apply_label_ranker_for_analyze
from services.prediction.canonical_contract import (
    build_canonical_prediction,
    determine_review_from_status,
)
from services.prediction.confidence_engine import (
    level_from_score,
)
from services.prediction.contract import derive_family_from_section, to_token_prediction
from services.prediction.explanation_engine import build_explanation
from services.prediction.ranking import build_ranking
from services.prediction.review_policy import (
    decide_review_status,
    determine_abstention_reason,
)
from services.regex_knowledge_base import knowledge_base
from services.regex_validator import full_match
from services.wildcard_matcher import has_wildcards, match_wildcard_mask


STRUCTURAL_FAMILIES = {
    "W",
    "HSS",
    "L",
    "C",
    "MC",
    "PIPE",
    "WT",
    "M",
    "S",
    "HP",
    "2L",
    "MT",
    "ST",
}

_geometry_provider = GeometryFeatureProvider()
_graph_provider = GraphFeatureProvider()


EXACT_OVERRIDE_MIN_CONFIDENCE = 0.72
EXACT_OVERRIDE_MIN_MARGIN = 0.06
LEARNED_DISAGREEMENT_GEOM_MIN = 0.75
LEARNED_DISAGREEMENT_GRAPH_MIN = 0.7


def _is_structural_family(label: Optional[str]) -> bool:
    return str(label or "").strip().upper() in STRUCTURAL_FAMILIES


def _early_confirmed_plate_type(
    token_record: Dict[str, Any],
    *,
    geometry: Dict[str, Any],
    graph: Dict[str, Any],
    document_prior: Dict[str, Any],
) -> Optional[str]:
    """Detect parser-confirmed plate annotations before AISC section fusion."""

    ctx = token_record.get("context") or {}
    nearby = list(ctx.get("neighbor_text") or [])
    page_context = str(ctx.get("line_text") or "")
    if document_prior.get("enabled"):
        from services.engineering.document_prior import prior_context_blob

        prior_blob = prior_context_blob(document_prior)
        if prior_blob:
            page_context = f"{page_context} | {prior_blob}".strip(" |")
    parsed = interpret_annotation(
        raw_text=str(token_record.get("raw_text") or token_record.get("text") or ""),
        normalized_text=str(
            token_record.get("normalized_text") or token_record.get("text") or ""
        ),
        page=token_record.get("page"),
        bbox=token_record.get("bbox"),
        text_rotation=token_record.get("rotation"),
        geometry_orientation=(
            ((geometry or {}).get("object") or {}).get("orientation")
            if ((geometry or {}).get("object") or {}).get("orientation") is not None
            else (geometry or {}).get("geometry_orientation")
        ),
        nearby_text=nearby,
        nearby_geometry=geometry,
        leader=(
            {"present": bool(ctx.get("leader"))} if ctx.get("leader") else None
        ),
        page_context=page_context,
        graph_context=graph,
        fragments=list(token_record.get("fragments") or []),
        source=str(token_record.get("extraction_method") or "pdf_text"),
        document_prior=document_prior if document_prior.get("enabled") else None,
    )
    annotation_type = annotation_type_value(parsed.annotation_type)
    if annotation_type not in {
        AnnotationType.PLATE.value,
        AnnotationType.BENT_PLATE.value,
    }:
        return None
    if not parsed.structure_confirmed:
        return None
    return annotation_type


def _plate_annotation_display_label(
    annotation_pack: Dict[str, Any],
    confirmed_plate_type: str,
    raw_text: str,
) -> str:
    """Human-readable label for a confirmed plate/bent-plate annotation."""

    annotation = annotation_pack.get("annotation") or {}
    thickness = annotation.get("thickness")
    if thickness:
        suffix = "BENT PL" if confirmed_plate_type == "BENT_PLATE" else "PL"
        thick_display = (
            str(thickness) if '"' in str(thickness) else f'{thickness}"'
        )
        return f"{thick_display} {suffix}".strip()
    dimensions = annotation.get("dimensions") or []
    if dimensions:
        body = " x ".join(str(item) for item in dimensions)
        suffix = "BENT PL" if confirmed_plate_type == "BENT_PLATE" else "PL"
        return f"{body} {suffix}".strip()
    cleaned = str(raw_text or "").strip()
    if cleaned:
        return cleaned
    return confirmed_plate_type.replace("_", " ").title()


def _skipped_section_fusion_result(reason: str) -> UnifiedFusionResult:
    """Placeholder fusion output when rolled-section prediction is not applicable."""

    return UnifiedFusionResult(
        section="",
        confidence=0.0,
        contributions={"annotation": 1.0},
        attention=AttentionResult(
            weights={"annotation": 1.0},
            logits={"annotation": 1.0},
        ),
        fused_features=FusedFeatures(
            vector=[],
            modality_slices={},
            availability={},
            encoders={},
        ),
        candidate_scores=[],
        reasons=[reason],
    )


def _candidate_confidence(candidate: Any) -> float:
    if hasattr(candidate, "confidence"):
        return float(candidate.confidence or 0.0)
    if isinstance(candidate, dict):
        return float(candidate.get("confidence") or 0.0)
    return 0.0


def _candidate_shape(candidate: Any) -> str:
    if hasattr(candidate, "shape"):
        return str(candidate.shape or "")
    if isinstance(candidate, dict):
        return str(candidate.get("shape") or "")
    return ""


def _gated_exact_override(
    fusion_section: str,
    exact_candidates: List[Any],
    ocr_text: str,
) -> tuple[str, bool]:
    """
    Compute the best available section for explanation/candidate purposes,
    and decide whether it may be treated as an automatically accepted final
    answer.

    Returns ``(section, retrieval_gate_failed)``. ``section`` is always the
    single best guess available (still useful for geometry/rule evaluation,
    entity typing, and the reviewer-facing candidate list even when not
    trustworthy enough to auto-accept). ``retrieval_gate_failed=True`` means
    the caller must abstain from treating ``section`` as a resolved final
    label and force human review instead.

    Only ``catalog_valid_exact_section`` (real AISC catalog membership) may
    ever produce a returned section. ``is_exact_section_label`` alone is a
    regex *format* check — a well-formatted but non-existent shape (e.g.
    "W12X999") must never be accepted as a final prediction just because it
    looks like a section designation.

    Catalog membership alone is NOT sufficient for automatic acceptance,
    either: fuzzy text-similarity retrieval and the learned correction
    engine can both propose a *different*, perfectly real catalog entry for
    text that does not actually spell it out (e.g. "W12X999" -> nearest
    real neighbor "W12X190"). Per the resolution contract, that is a
    candidate/suggestion, never a silently auto-accepted answer -- so gate
    failure is also forced whenever the accepted label is not exactly what
    ``ocr_text`` itself resolves to under safe, non-fuzzy normalization
    (i.e. this reduces to the same check as the protected-exact-label path
    above; it exists here too because this function's non-text-grounded
    candidates are otherwise indistinguishable from a genuine match once
    they're both catalog-valid strings).
    """

    text_grounded_label = catalog_valid_exact_section(ocr_text)

    if not (_is_structural_family(fusion_section) and exact_candidates):
        catalog_label = catalog_valid_exact_section(fusion_section)
        if catalog_label:
            return catalog_label, catalog_label != text_grounded_label
        # Family-only or non-catalog fusion output with no exact candidates → abstain.
        return "", True

    top = exact_candidates[0]
    top_shape = _candidate_shape(top)
    top_confidence = _candidate_confidence(top)
    second_confidence = (
        _candidate_confidence(exact_candidates[1])
        if len(exact_candidates) > 1
        else 0.0
    )
    margin = top_confidence - second_confidence
    if (
        top_shape
        and top_confidence >= EXACT_OVERRIDE_MIN_CONFIDENCE
        and margin >= EXACT_OVERRIDE_MIN_MARGIN
        and plausible_against_ocr(top_shape, ocr_text)
    ):
        catalog_label = catalog_valid_exact_section(top_shape)
        if catalog_label:
            return catalog_label, catalog_label != text_grounded_label

    catalog_label = catalog_valid_exact_section(fusion_section)
    if catalog_label:
        return catalog_label, catalog_label != text_grounded_label
    return "", True


def _text_locked_section(text: str, fusion_section: str) -> str:
    """Return the designation the extracted characters themselves resolve to.

    An undamaged annotation that is already a catalog designation is stronger
    evidence than a fusion Top-1 that won by a fraction of a percent. AISC is
    used here only to confirm the text is a real designation, never to generate
    a different answer.
    """

    if has_wildcards(text) or "?" in text:
        return ""
    resolved = catalog_form(compact_normalize(text))
    if not resolved:
        return ""
    if resolved == catalog_form(compact_normalize(fusion_section or "")):
        return ""
    return resolved


def predict_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full multimodal prediction for one token context.

    Context keys: token, document?, geometry?, graph?, source_file?
    """

    token_record = context["token"]
    extracted_text = str(token_record.get("text") or "")
    raw_text = str(token_record.get("raw_text") or extracted_text)
    # Alias for wildcard matching / legacy callers expecting extracted text.
    original = extracted_text or raw_text
    normalized = str(
        token_record.get("normalized_text") or extracted_text
    ).strip()
    # Spatial-association tokens carry the label section inferred from a
    # nearby text callout — there is no OCR text on the linework itself.
    if token_record.get("geometry_associated") and token_record.get("inferred_section"):
        inferred = str(token_record["inferred_section"]).strip()
        if inferred and not normalized:
            normalized = inferred
            extracted_text = inferred
            original = inferred
    source_file = str(
        context.get("source_file")
        or (context.get("document") or {}).get("source_file")
        or ""
    )

    # PROTECTED EXACT LABEL PATH: if the conservatively-normalized OCR text is
    # already a real, catalog-valid AISC section on its own, that text-exact
    # reading is authoritative. Fusion/graph/geometry may still add
    # corroborating or conflicting evidence used for review routing below,
    # but nothing downstream may silently substitute a different section for
    # a clean catalog-valid exact label (see the applied check after the
    # label-ranker hook, further down this function).
    protected_exact_section = catalog_valid_exact_section(
        normalized
    ) or catalog_valid_exact_section(raw_text)
    extraction_confidence = float(token_record.get("confidence") or 0.5)

    geometry = context.get("geometry_features") or _geometry_provider.extract(context)
    graph = context.get("graph_features") or _graph_provider.extract(context)

    document = context.get("document") or {}
    document_prior = (
        document.get("document_prior") or {}
        if settings.document_prior_enabled
        else {}
    )
    confirmed_plate_type = _early_confirmed_plate_type(
        token_record,
        geometry=geometry,
        graph=graph,
        document_prior=document_prior,
    )

    is_anonymous_dim = (
        str(token_record.get("engineering_object_type") or "") == "anonymous_dimension"
    )
    anonymous_resolution: Optional[Dict[str, Any]] = None
    resolved_semantic_annotation: Optional[Dict[str, Any]] = None
    if is_anonymous_dim and not confirmed_plate_type:
        from services.annotation.anonymous_dimension_resolver import (
            resolve_anonymous_dimension,
        )
        from services.annotation.context_evidence import build_context_evidence

        evidence = token_record.get("context_evidence") or build_context_evidence(
            token_record,
            document=document,
            geometry=context.get("geometry") or {},
            graph=context.get("graph"),
        )
        token_record["context_evidence"] = evidence
        anonymous_resolution = resolve_anonymous_dimension(evidence, raw_text=raw_text)
        if evidence.get("in_title_block") or evidence.get("layout_dimension_is_non_steel"):
            anonymous_resolution = {
                **anonymous_resolution,
                "abstain": True,
                "recommended": None,
                "review_reason": (
                    "Layout or title-block dimension; not a steel takeoff item."
                ),
            }
            token_record["_skip_unknown_queue"] = True
        recommended = anonymous_resolution.get("recommended")
        if recommended and not anonymous_resolution.get("abstain"):
            rec_type = str(recommended.get("type") or "")
            if rec_type in {"PLATE", "BENT_PLATE"}:
                confirmed_plate_type = rec_type
            elif rec_type in {"ANGLE", "CONNECTION_THICKNESS"}:
                resolved_semantic_annotation = recommended

    skip_section_fusion = bool(confirmed_plate_type) or is_anonymous_dim

    family_label = ""
    family_probability = 0.0
    family_prediction = None
    used_wildcards = False
    wildcard_hits: List[Any] = []
    exact_candidates: List[Any] = []
    corrections: List[Any] = []
    corrected_text = normalized
    encodings: Dict[str, Any]
    unified_fusion: UnifiedFusionResult
    section = ""
    retrieval_gate_failed = True
    label_ranker_meta: Dict[str, Any] = {}
    protected_label_conflict = False
    ranker_applied_effective = False
    hss_dimensions: Optional[tuple] = None
    hss_completions: List[Any] = []
    missing_thickness_needs_review = False

    if skip_section_fusion:
        provisional_rules = evaluate_engineering_rules(
            token=normalized,
            predicted_shape="",
            geometry=geometry,
            graph=context.get("graph"),
            graph_preview={
                "degree": graph.get("degree"),
                "structural_links": graph.get("structural_links"),
            },
        )
        skip_reason = (
            f"Confirmed {confirmed_plate_type}; rolled-section fusion skipped."
            if confirmed_plate_type
            else "Anonymous dimension; rolled-section fusion skipped."
        )
        unified_fusion = _skipped_section_fusion_result(skip_reason)
        encodings = encoder_registry.encode_all(
            {
                "text": {
                    "token": normalized,
                    "model_probability": 0.0,
                    "extraction_confidence": extraction_confidence,
                    "regex_confidence": 0.0,
                    "candidates": [],
                },
                "ocr": {
                    "original": raw_text,
                    "corrected": corrected_text,
                    "confidence": extraction_confidence,
                    "repairs": (
                        (token_record.get("diagnostics") or {}).get("ocr_repairs")
                        or []
                    ),
                },
                "layout": {
                    "bbox": token_record.get("bbox"),
                    "page": token_record.get("page"),
                    "reading_order": token_record.get("reading_order"),
                    "font_size": token_record.get("font_size"),
                    "rotation": token_record.get("rotation"),
                    "member_role": token_record.get("engineering_object_type"),
                    "neighbors": (
                        (token_record.get("context") or {}).get("neighbor_text") or []
                    ),
                },
                "geometry": {"geometry": geometry},
                "graph": {"graph": graph},
                "engineering_rules": {"rules": provisional_rules.to_dict()},
            }
        )
    else:
        # MISSING-THICKNESS HSS PATH: "HSS10X10" does not uniquely identify a
        # catalog section -- the two outside dimensions are KNOWN (read cleanly,
        # no wildcard/corruption marker), only thickness is absent.
        hss_dimensions = (
            None
            if protected_exact_section
            else (
                detect_missing_thickness_hss(normalized)
                or detect_missing_thickness_hss(raw_text)
            )
        )
        hss_completions = (
            hss_completion_candidates(*hss_dimensions) if hss_dimensions else []
        )
        missing_thickness_needs_review = len(hss_completions) > 1

        family_prediction = predict_with_confidence(normalized)
        family_label = family_prediction.label
        family_probability = float(family_prediction.probability)

        provisional_rules = evaluate_engineering_rules(
            token=normalized,
            predicted_shape=str(family_label or normalized),
            geometry=geometry,
            graph=context.get("graph"),
            graph_preview={
                "degree": graph.get("degree"),
                "structural_links": graph.get("structural_links"),
            },
        )

        # Deterministic wildcard/mask matching runs before fuzzy retrieval: a
        # label with explicit unknown-character markers (e.g. "W44X3**") is
        # resolved against the real AISC catalog by position, not by string
        # similarity. Fuzzy retrieval only takes over when there are no wildcard
        # characters, or the mask matched nothing in the catalog.
        used_wildcards = has_wildcards(original) or has_wildcards(normalized)
        wildcard_hits = (
            match_wildcard_mask(original or normalized, limit=8)
            if used_wildcards
            else []
        )

        # Single exact-section AI call with multimodal rerank (Priority 1).
        exact_candidates = []
        if hss_completions:
            exact_candidates = predict_exact_sections_for_labels(
                [item.designation for item in hss_completions],
                geometry=geometry,
                graph=graph,
                engineering_rules=provisional_rules.to_dict(),
                limit=len(hss_completions),
            )
        elif wildcard_hits:
            exact_candidates = predict_exact_sections_for_labels(
                [hit.label for hit in wildcard_hits],
                geometry=geometry,
                graph=graph,
                engineering_rules=provisional_rules.to_dict(),
                limit=8,
            )
        elif _is_structural_family(family_label) or not family_label:
            exact_candidates = predict_exact_sections(
                normalized,
                limit=10,
                geometry=geometry,
                graph=graph,
                engineering_rules=provisional_rules.to_dict(),
            )
        if not exact_candidates and _is_structural_family(family_label):
            exact_candidates = predict_exact_sections(
                str(family_label),
                limit=10,
                geometry=geometry,
                graph=graph,
                engineering_rules=provisional_rules.to_dict(),
            )

        if document_prior.get("enabled") and not protected_exact_section:
            exact_candidates = apply_prior_to_candidates(
                exact_candidates,
                document_prior,
                token_text=normalized or raw_text,
            )

        expected_family = (
            str(family_label) if _is_structural_family(family_label) else None
        )
        corrections = suggest_token_corrections(
            extracted_text or normalized,
            expected_family=expected_family,
            geometry=geometry,
            graph=graph,
            engineering_context=provisional_rules.to_dict(),
            similarity_candidates=exact_candidates,
            limit=8,
        )
        # Geometry vector hits contribute role/consistency evidence only — they
        # must not inject section strings into fusion (plan-view lines cannot
        # distinguish W12X26 from W21X44).
        fusion_candidates: List[Any] = list(exact_candidates)
        existing_shapes = {candidate.shape for candidate in exact_candidates}
        hss_completion_shapes = (
            {item.designation for item in hss_completions} if hss_completions else None
        )
        for correction in corrections:
            if (
                correction.corrected in existing_shapes
                or lookup_shape(correction.corrected) is None
            ):
                continue
            if (
                hss_completion_shapes is not None
                and correction.corrected not in hss_completion_shapes
            ):
                continue
            fusion_candidates.append(
                {
                    "shape": correction.corrected,
                    "evidence": {
                        "text": float(correction.confidence),
                        "geometry": float(geometry.get("similarity") or 0.0),
                        "graph": float(
                            graph.get("graph_confidence")
                            or graph.get("graph_consistency")
                            or 0.0
                        ),
                        "engineering_rules": float(provisional_rules.score),
                    },
                }
            )
        fusion_candidates = [
            candidate
            for candidate in fusion_candidates
            if lookup_shape(
                str(
                    getattr(candidate, "shape", None)
                    or (
                        candidate.get("shape")
                        if isinstance(candidate, dict)
                        else ""
                    )
                )
            )
            is not None
        ]
        if document_prior.get("enabled") and not protected_exact_section:
            fusion_candidates = apply_prior_to_candidates(
                fusion_candidates,
                document_prior,
                token_text=normalized or raw_text,
            )
        corrected_text = corrections[0].corrected if corrections else normalized
        if missing_thickness_needs_review:
            corrected_text = normalized

        encodings = encoder_registry.encode_all(
            {
                "text": {
                    "token": normalized,
                    "model_probability": (
                        float(exact_candidates[0].confidence)
                        if exact_candidates
                        else family_probability
                    ),
                    "extraction_confidence": extraction_confidence,
                    "regex_confidence": 0.0,
                    "candidates": exact_candidates,
                },
                "ocr": {
                    "original": raw_text,
                    "corrected": corrected_text,
                    "confidence": extraction_confidence,
                    "repairs": (
                        (token_record.get("diagnostics") or {}).get("ocr_repairs")
                        or []
                    ),
                },
                "layout": {
                    "bbox": token_record.get("bbox"),
                    "page": token_record.get("page"),
                    "reading_order": token_record.get("reading_order"),
                    "font_size": token_record.get("font_size"),
                    "rotation": token_record.get("rotation"),
                    "member_role": token_record.get("engineering_object_type"),
                    "neighbors": (
                        (token_record.get("context") or {}).get("neighbor_text")
                        or []
                    ),
                },
                "geometry": {"geometry": geometry},
                "graph": {"graph": graph},
                "engineering_rules": {"rules": provisional_rules.to_dict()},
            }
        )
        unified_fusion = unified_multimodal_fusion.predict(
            encodings=encodings,
            candidates=fusion_candidates,
            fallback_section=corrected_text,
        )
        section, retrieval_gate_failed = _gated_exact_override(
            str(unified_fusion.section or ""),
            exact_candidates,
            normalized or raw_text,
        )
        label_ranker_meta = apply_label_ranker_for_analyze(
            raw_text=original or normalized,
            live_section=section,
        )
        if label_ranker_meta.get("applied") and label_ranker_meta.get(
            "selected_prediction"
        ):
            ranker_label = str(label_ranker_meta["selected_prediction"])
            section = ranker_label
            retrieval_gate_failed = ranker_label != catalog_valid_exact_section(
                original or normalized
            )

        if protected_exact_section:
            if section and section != protected_exact_section:
                protected_label_conflict = True
            section = protected_exact_section
            retrieval_gate_failed = False

        ranker_applied_effective = bool(
            label_ranker_meta.get("applied")
        ) and not protected_label_conflict

    ai_reasons = list(unified_fusion.reasons)
    if skip_section_fusion:
        if confirmed_plate_type:
            ai_reasons.append(
                f"Confirmed {confirmed_plate_type}; AISC section prediction not applicable."
            )
        elif is_anonymous_dim:
            ai_reasons.append(
                "Anonymous dimension; AISC section fusion skipped pending semantic resolution."
            )
    elif retrieval_gate_failed:
        ai_reasons.append(
            "Exact-section retrieval gate failed; abstaining for human review."
        )
    if not confirmed_plate_type and label_ranker_meta.get("applied"):
        ai_reasons.append(
            "Damaged-label ranker enabled; replaced section with learned pick."
        )
    if not confirmed_plate_type and not label_ranker_meta.get("applied"):
        text_locked = _text_locked_section(normalized or raw_text, section)
        if text_locked:
            ai_reasons.append(
                f"Text evidence resolves the annotation to {text_locked}; the "
                f"fusion pick {section or 'none'} was not supported by the "
                "extracted characters."
            )
            section = text_locked
            retrieval_gate_failed = False

    annotation_pack = interpret_token_annotation(
        token_record,
        geometry=geometry,
        graph=graph,
        candidate_scores=unified_fusion.candidate_scores,
        selected_section=section,
        document_prior=document_prior if document_prior.get("enabled") else None,
    )
    annotation = annotation_pack.get("annotation") or {}
    if not confirmed_plate_type:
        late_plate_type = annotation_type_value(annotation.get("annotation_type"))
        if (
            late_plate_type
            in {AnnotationType.PLATE.value, AnnotationType.BENT_PLATE.value}
            and annotation.get("structure_confirmed")
        ):
            confirmed_plate_type = late_plate_type
            section = ""
            retrieval_gate_failed = False
            ai_reasons = [
                reason
                for reason in ai_reasons
                if "Exact-section retrieval gate failed" not in reason
                and "Damaged-label ranker" not in reason
            ]
            if not any(
                "AISC section prediction not applicable" in reason
                for reason in ai_reasons
            ):
                ai_reasons.append(
                    f"Confirmed {confirmed_plate_type}; "
                    "AISC section prediction not applicable."
                )
    understand = annotation_pack.get("understandability") or {}
    understandability_status = understandability_value(understand.get("status"))
    if requires_review(understandability_status):
        ai_reasons.append(
            f"Annotation {understandability_status}: "
            + "; ".join(str(item) for item in (understand.get("reasons") or []))
        )
        if protected_exact_section:
            # The extracted characters already resolve to a clean,
            # catalog-valid AISC section (see the protected-label check
            # above) — that text evidence outranks annotation-taxonomy
            # heuristics derived from geometry/graph context. Text
            # resolution and annotation understandability are different
            # questions: keep the label, but still force review via the
            # "annotation_*" issue tags appended further down.
            pass
        else:
            # Unreadable/unsupported text with no protected exact label must
            # not be answered from candidates.
            if not confirmed_plate_type:
                section = ""
                retrieval_gate_failed = True
    elif annotation_pack.get("abstain_for_review") and not confirmed_plate_type:
        ai_reasons.append(
            "Top-K candidates remain ambiguous; abstaining for human review."
        )
        if not protected_exact_section:
            retrieval_gate_failed = True

    if protected_label_conflict:
        ai_reasons.append(
            f"Kept catalog-valid exact text match ({protected_exact_section}); "
            "fusion/graph/ranker evidence favored a different candidate but "
            "cannot silently override a clean exact label. Flagged for review."
        )

    if missing_thickness_needs_review:
        retrieval_gate_failed = True
        ai_reasons.append(
            "Wall thickness is not present in the extracted designation "
            f"({normalized}); select the correct catalog section from "
            f"{len(hss_completions)} valid completions."
        )

    if skip_section_fusion:
        retrieval_gate_failed = False

    model_label = section
    model_probability = (
        extraction_confidence
        if confirmed_plate_type
        else (0.0 if retrieval_gate_failed else float(unified_fusion.confidence))
    )
    if protected_exact_section and not retrieval_gate_failed:
        # A clean catalog-valid exact text match is itself strong evidence;
        # do not surface the (rejected) fusion candidate's own confidence as
        # if it belonged to the protected label.
        model_probability = max(model_probability, extraction_confidence)
    elif ranker_applied_effective:
        # The ranker's own score for ITS pick, not unified_fusion's score for
        # the candidate it replaced. ranking_scores is sorted by the ranker's
        # own ordering (highest first); fall back to a conservative,
        # explicitly-not-fabricated mid value if the ranker didn't report one.
        ranker_scores = label_ranker_meta.get("ranking_scores") or []
        model_probability = float(ranker_scores[0]) if ranker_scores else 0.5
    distribution = {
        item["shape"]: float(item["score"])
        for item in unified_fusion.candidate_scores
    }
    family = (
        "Plate"
        if confirmed_plate_type
        else derive_family_from_section(section, fallback=family_label)
    )

    # Post-prediction AISC plausibility check; it never generates candidates.
    db_exact = None if confirmed_plate_type else lookup_shape(section)
    similar = search_similar_shapes(normalized, limit=8, minimum_score=0.35)
    best_similarity = (
        1.0 if db_exact else float(similar[0]["similarity"]) if similar else 0.0
    )
    db_similarity = 1.0 if db_exact else best_similarity * 0.5
    database_verified = db_exact is not None

    rules = evaluate_engineering_rules(
        token=normalized,
        predicted_shape=section,
        geometry=geometry,
        graph=context.get("graph"),
        graph_preview={
            "degree": graph.get("degree"),
            "structural_links": graph.get("structural_links"),
        },
    )
    rule_score = float(rules.score)

    kb_key = section if not _is_structural_family(section) else (family or section)
    record = knowledge_base.get(kb_key) if kb_key else {}
    regex = (record or {}).get("primary_pattern") or (record or {}).get("pattern")
    regex_contribution = 1.0 if regex and full_match(regex, normalized) else 0.0

    text_similarity = min(
        1.0,
        0.70 * model_probability
        + 0.20 * extraction_confidence
        + 0.10 * regex_contribution,
    )
    geometry_similarity = float(geometry.get("similarity") or 0.0)
    graph_consistency = float(
        graph.get("structural_consistency")
        or graph.get("graph_consistency")
        or 0.0
    )
    graph_similarity = float(
        graph.get("graph_confidence")
        if graph.get("graph_embedding")
        else graph_consistency
    )

    signals = {
        "text": text_similarity,
        "ocr": float(encodings["ocr"].confidence),
        "layout": float(encodings["layout"].confidence),
        "geometry": geometry_similarity,
        "graph": graph_similarity,
        "engineering_rules": rule_score,
        # Database is recorded for verification/explanation only.
        "database": db_similarity if database_verified else min(0.35, db_similarity),
    }
    available = {
        "text": True,
        "ocr": bool(encodings["ocr"].available),
        "layout": bool(encodings["layout"].available),
        "geometry": (
            model_may_influence("geometry_mobilenet")
            and (
                bool(geometry.get("available"))
                or bool(geometry.get("geometry_embedding"))
            )
        ),
        "graph": (
            model_may_influence("graph_graphsage")
            and (
                bool(graph.get("graph_available"))
                or bool(graph.get("graph_embedding"))
                or bool(graph.get("source_node"))
                or float(graph.get("degree") or 0) > 0
            )
        ),
        "engineering_rules": True,
        "database": True,
    }

    confidence_value = (
        extraction_confidence
        if confirmed_plate_type
        else (0.0 if retrieval_gate_failed else float(unified_fusion.confidence))
    )
    if protected_exact_section and not retrieval_gate_failed:
        confidence_value = max(confidence_value, extraction_confidence)
    elif ranker_applied_effective:
        confidence_value = model_probability
    # breakdown/weights describe WHICH modality produced ``section``'s score.
    # unified_fusion.contributions is only correct when unified_fusion's own
    # candidate is what's being reported — for the ranker-applied case those
    # per-modality shares belong to the candidate the ranker REPLACED, so
    # showing them next to the ranker's own pick would misattribute a
    # learned-ranker decision to text/geometry/graph evidence it never used.
    if ranker_applied_effective:
        contributions_for_display: Dict[str, float] = {"label_ranker": 1.0}
    else:
        contributions_for_display = dict(unified_fusion.contributions)
    confidence = {
        "overall": round(confidence_value, 4),
        "level": level_from_score(confidence_value),
        "model_probability": round(model_probability, 4),
        "breakdown": {
            "ai": round(model_probability, 4),
            **{
                name: round(float(value), 4)
                for name, value in contributions_for_display.items()
            },
        },
        "weights": dict(contributions_for_display),
        "database_role": "verification_only",
    }
    geometry_confidence = float(
        geometry.get("geometry_confidence")
        or geometry.get("geometry_role_confidence")
        or geometry.get("similarity")
        or 0.0
    )
    learned_disagreement = (
        not protected_exact_section
        and not ranker_applied_effective
        and bool(normalized)
        and bool(section)
        and section != normalized
        and geometry_confidence >= LEARNED_DISAGREEMENT_GEOM_MIN
        and graph_consistency >= LEARNED_DISAGREEMENT_GRAPH_MIN
        and bool(geometry.get("geometry_embedding"))
        and (
            bool(graph.get("graph_embedding"))
            or float(graph.get("degree") or 0) > 0
        )
    )
    final_correction = (
        None
        if confirmed_plate_type
        else (
        {
            "original": raw_text or normalized,
            "corrected": section,
            "reason": (
                "Damaged-label ranker (ENABLED) replaced the extracted "
                "label with its top-ranked learned candidate."
            ),
            "confidence": round(confidence_value, 4),
        }
        if ranker_applied_effective
        else {
            "original": raw_text or normalized,
            "corrected": section,
            "reason": (
                "Learned text, geometry, and structural-graph evidence "
                "disagreed with the extracted label."
            ),
            "confidence": round(confidence_value, 4),
            "evidence": {
                "geometry_available": bool(geometry.get("available")),
                "graph_available": bool(available.get("graph")),
                "annotation_type": (annotation_pack.get("annotation") or {}).get(
                    "annotation_type"
                ),
            },
            "reviewer_state": "suggested",
        }
        if learned_disagreement
        else (
            {
                **corrections[0].to_dict(),
                "evidence": {
                    "sources": ["correction_engine"],
                    "annotation_type": (annotation_pack.get("annotation") or {}).get(
                        "annotation_type"
                    ),
                },
                "reviewer_state": "suggested",
            }
            if corrections
            else None
        )
        )
    )
    output_corrected_text = (
        (raw_text or normalized)
        if confirmed_plate_type
        else (
            section if (learned_disagreement or ranker_applied_effective) else corrected_text
        )
    )
    # Contribution scores are normalized attention shares, not raw
    # similarities — and (see above) not valid at all for the ranker-applied
    # case, where contributions_for_display already substitutes an honest
    # {"label_ranker": 1.0} marker instead of the pre-swap candidate's shares.
    evidence = dict(contributions_for_display)
    explanation = build_explanation(
        family=family,
        section=section,
        ai_reasons=ai_reasons,
        signals=signals,
        available=available,
        ai_probability=model_probability,
        regex_contribution=regex_contribution,
        database_verified=database_verified,
        rule_findings=rules.findings,
        candidate_scores=unified_fusion.candidate_scores,
        text_evidence={
            "token": normalized,
            "raw_text": raw_text,
            "corrected_text": corrected_text,
            "normalized_text": normalized,
            "original_token": raw_text,
            "model_label": model_label,
            "model_probability": round(model_probability, 4),
            "family_label": family_label,
            "family_probability": round(family_probability, 4),
            "extraction_confidence": round(extraction_confidence, 4),
            "matched_neighbors": (
                (token_record.get("context") or {}).get("neighbor_text")
                or []
            ),
        },
        geometry_evidence={
            "available": bool(geometry.get("available")),
            "encoder": (
                "mobilenet_v3_small"
                if geometry.get("geometry_embedding")
                else geometry.get("similarity_source") or "vector_geometry"
            ),
            "object": geometry.get("object"),
            "similarity": round(geometry_similarity, 4),
            "similarity_source": geometry.get("similarity_source")
            or "vector_geometry",
            # Embedding vectors stay out of the response; only their presence
            # and size are needed to explain the evidence.
            "embedding_dimension": len(geometry.get("geometry_embedding") or []),
            "confidence": geometry.get("geometry_confidence"),
            "candidates": (geometry.get("geometry_candidates") or [])[:5],
            "top_candidates": (geometry.get("geometry_candidates") or [])[:5],
            "features": geometry.get("geometry_features") or {},
            "nearest_distance": geometry.get("nearest_distance"),
            "source": geometry.get("source"),
        },
        graph_evidence={
            "available": bool(available["graph"]),
            "model": "graphsage" if graph.get("graph_embedding") else "structural_graph",
            "node_id": graph.get("source_node"),
            "node_kind": graph.get("node_kind"),
            "degree": graph.get("degree"),
            "structural_links": graph.get("structural_links"),
            "min_distance": graph.get("min_distance"),
            "consistency": round(graph_consistency, 4),
            "structural_consistency": round(graph_consistency, 4),
            "embedding_dimension": len(graph.get("graph_embedding") or []),
            "prediction": graph.get("graph_prediction"),
            "role_prediction": graph.get("graph_prediction"),
            "confidence": graph.get("graph_confidence"),
            "missing_label_probability": graph.get("missing_label_probability"),
            "incorrect_label_probability": graph.get("incorrect_label_probability"),
        },
        engineering_evidence={
            "score": round(rule_score, 4),
            "member_role": rules.member_role,
            "material_grade": rules.material_grade,
        },
    )
    explanation["contributions"] = {
        name: round(value, 4)
        for name, value in contributions_for_display.items()
    }
    explanation["contribution_percentages"] = {
        name: round(value * 100.0, 1)
        for name, value in contributions_for_display.items()
    }
    explanation["attention"] = unified_fusion.attention.to_dict()
    explanation["encoders"] = {
        name: encoding.encoder for name, encoding in encodings.items()
    }
    if final_correction:
        correction_payload = final_correction
        explanation["correction"] = correction_payload
        reviewed_example = (
            correction_payload.get("evidence") or {}
        ).get("reviewed_example")
        explanation["correction_history"] = (
            [reviewed_example] if reviewed_example else []
        )
    if label_ranker_meta.get("invoked"):
        explanation["label_ranker"] = {
            "applied": bool(label_ranker_meta.get("applied")),
            "reason": label_ranker_meta.get("reason"),
            "selected_prediction": label_ranker_meta.get("selected_prediction"),
            "model_version": label_ranker_meta.get("model_version"),
            "shadow_disagreement": (
                (label_ranker_meta.get("shadow") or {}).get("disagreement")
                if label_ranker_meta.get("shadow")
                else None
            ),
            "live_disagreement": (
                (label_ranker_meta.get("shadow") or {}).get("live_disagreement")
                if label_ranker_meta.get("shadow")
                else None
            ),
        }
    explanation["annotation_interpretation"] = annotation_pack
    ann = (annotation_pack.get("annotation") or {})
    eng_bits = [
        f"Annotation typed as {ann.get('annotation_type') or 'UNKNOWN'}"
        + (f"/{ann.get('subtype')}" if ann.get("subtype") else "")
        + f" ({understandability_status})."
    ]
    if ann.get("dimensions"):
        eng_bits.append(
            "Parsed dimensions "
            + " × ".join(str(d) for d in ann.get("dimensions") or [])
            + (f", thickness {ann.get('thickness')}" if ann.get("thickness") else "")
            + (" (plate semantics confirmed)." if ann.get("structure_confirmed") else " (semantics not confirmed from text alone).")
        )
    if (annotation_pack.get("ambiguity") or {}).get("reason"):
        eng_bits.append(str(annotation_pack["ambiguity"]["reason"]))
    if ann.get("text_rotation") is not None or ann.get("geometry_orientation") is not None:
        eng_bits.append(
            f"Text rotation={ann.get('text_rotation')}; "
            f"geometry orientation={ann.get('geometry_orientation')} (independent signals)."
        )
    existing_eng = explanation.get("engineer_explanation") or {}
    bullets = list(existing_eng.get("bullets") or []) + eng_bits
    explanation["engineer_explanation"] = {
        **existing_eng,
        "bullets": bullets,
        "summary": existing_eng.get("summary")
        or (
            f"Confirmed {confirmed_plate_type}; no AISC section applied ({understandability_status})."
            if confirmed_plate_type
            else (
                f"Selected {section} with understandability={understandability_status}."
                if section
                else f"No automatic section — {understandability_status}."
            )
        ),
    }

    # Entity metadata — AI family/section first; AISC only for category enrichment.
    entity = (
        EntityClassification(
            CATEGORY_PLATE,
            CATEGORY_LABELS[CATEGORY_PLATE],
            confirmed_plate_type,
            "annotation_parser",
            1.0,
        )
        if confirmed_plate_type
        else resolve_entity(
            section,
            aisc_type=None,  # do not let AISC override class_name
            model_class=family or family_label,
            database_type=(db_exact or {}).get("type"),
        )
    )

    issues = detect_extraction_issues(token_record)
    if corrected_text != normalized:
        issues.append("automatic_correction_suggested")
    if not database_verified and not confirmed_plate_type:
        issues.append("database_unverified")
    if rule_score < 0.55 and not confirmed_plate_type:
        issues.append("engineering_rule_conflict")
    if geometry.get("available") and geometry_similarity < 0.45:
        issues.append("geometry_conflict")
    if float(graph.get("degree") or 0) > 0 and graph_consistency < 0.45:
        issues.append("graph_conflict")
    if retrieval_gate_failed or (not section and not confirmed_plate_type):
        issues.append("retrieval_gate_failed")
    if annotation_pack.get("abstain_for_review"):
        issues.append("annotation_requires_review")
    if understandability_status == Understandability.UNREADABLE.value:
        issues.append("annotation_unreadable")
    if understandability_status == Understandability.UNSUPPORTED.value:
        issues.append("annotation_unsupported")
    if (
        understandability_status == Understandability.AMBIGUOUS.value
        and not confirmed_plate_type
    ):
        issues.append("annotation_ambiguous")
    if protected_label_conflict:
        issues.append("protected_label_conflict")
    if token_record.get("schedule_sourced"):
        issues.append("schedule_sourced_member")
    if token_record.get("geometry_associated"):
        issues.append("geometry_spatial_association")
    if skip_section_fusion:
        issues.append("plate_annotation_not_structural_section")

    review_status = decide_review_status(
        confidence=float(confidence["overall"]),
        issues=issues,
        corrected=corrected_text != normalized,
        regex_matches=bool(confirmed_plate_type),
        model_probability=model_probability,
        database_verified=database_verified,
        abstain=(retrieval_gate_failed or (not section and not confirmed_plate_type)),
        protected_label_conflict=protected_label_conflict,
    )
    if confirmed_plate_type and review_status != "pending_review":
        review_status = "auto_accepted"
    if token_record.get("schedule_sourced") or token_record.get("geometry_associated"):
        review_status = "pending_review"
    abstention_reason = determine_abstention_reason(
        review_status=review_status,
        confidence=float(confidence["overall"]),
        issues=issues,
        model_probability=model_probability,
        database_verified=database_verified,
        regex_matches=bool(confirmed_plate_type),
        protected_label_conflict=protected_label_conflict,
        retrieval_gate_failed=retrieval_gate_failed
        or (not section and not confirmed_plate_type),
        pipeline_error=label_ranker_meta.get("ranker_status") == "error",
    )

    component_id = allocate_component_id(
        role=rules.member_role or entity.category,
        page=token_record.get("page"),
        bbox=token_record.get("bbox"),
        text=section or raw_text or normalized,
        source_file=source_file,
    )

    # --- Canonical prediction contract (additive) ---------------------------
    # Single ranking stage: merge fusion candidate scores with any
    # deterministic wildcard-mask candidates into one catalog-checked,
    # human-readable candidate list instead of several disconnected
    # weighted-sum stages.
    ranking = build_ranking(
        fusion_candidate_scores=unified_fusion.candidate_scores,
        wildcard_candidates=wildcard_hits,
        limit=8,
    )
    ranking_score = float(confidence["overall"])
    final_confidence, confidence_is_calibrated = calibrate_score(ranking_score)
    document_id = str((context.get("document") or {}).get("document_id") or "") or None
    bbox = token_record.get("bbox")
    line_info = token_record.get("line") or {}
    block_info = token_record.get("block") or {}
    plate_annotation_label = (
        _plate_annotation_display_label(annotation_pack, confirmed_plate_type, raw_text)
        if confirmed_plate_type
        else None
    )
    semantic_annotation_type = confirmed_plate_type
    semantic_annotation_label = plate_annotation_label
    if resolved_semantic_annotation:
        section = str(resolved_semantic_annotation.get("label") or section or "")
        semantic_annotation_type = resolved_semantic_annotation.get("type")
        semantic_annotation_label = resolved_semantic_annotation.get("label")
    elif (
        is_anonymous_dim
        and anonymous_resolution
        and anonymous_resolution.get("abstain")
        and not confirmed_plate_type
    ):
        section = ""
        retrieval_gate_failed = True
    needs_context_review = bool(
        is_anonymous_dim
        and anonymous_resolution
        and anonymous_resolution.get("abstain")
        and not confirmed_plate_type
        and not resolved_semantic_annotation
    )
    canonical = build_canonical_prediction(
        object_id=str(token_record.get("token_id") or component_id),
        document_id=document_id,
        raw_text=original,
        normalized_text=normalized,
        page_number=token_record.get("page"),
        bounding_box=list(bbox) if bbox else None,
        block_number=block_info.get("number"),
        line_number=line_info.get("number"),
        word_number=None,  # a token may merge several source words; see token_extractor
        extraction_method=(
            "schedule_on_drawing"
            if token_record.get("schedule_sourced")
            else "spatial_association"
            if token_record.get("geometry_associated")
            else "geometry_inference"
            if token_record.get("missing_label") or not original.strip()
            else "pdf_text"
            if bbox
            else "unknown"
        ),
        source_available=bool(original.strip()),
        final_label=section,
        family=family,
        ranking_score=ranking_score,
        final_confidence=final_confidence,
        confidence_is_calibrated=confidence_is_calibrated,
        used_text=bool(original.strip()),
        used_geometry=bool(geometry.get("available")),
        used_graph=float(graph.get("degree") or 0) > 0,
        used_engineering_rules=True,
        used_catalog=True,
        candidates=[item.to_dict() for item in ranking.candidates],
        evidence=dict(evidence),
        catalog_version=aisc_catalog_version(),
        review_status=review_status,
        near_tie=ranking.near_tie,
        used_wildcards=used_wildcards,
        used_missing_dimension=missing_thickness_needs_review,
        confirmed_annotation=bool(confirmed_plate_type or resolved_semantic_annotation),
        annotation_type=semantic_annotation_type,
        annotation_label=semantic_annotation_label,
        section_applicable=not bool(confirmed_plate_type or resolved_semantic_annotation),
        confidence_basis=(
            "extraction_confidence"
            if confirmed_plate_type or resolved_semantic_annotation
            else None
        ),
        used_needs_context=needs_context_review,
    )

    alternatives = []
    for candidate in corrections:
        if candidate.corrected != section:
            alternatives.append(
                {
                    "shape": candidate.corrected,
                    "confidence": round(candidate.confidence, 4),
                    "entity_type": resolve_entity(candidate.corrected).category,
                }
            )
    existing_alternatives = {item["shape"] for item in alternatives}
    for label, probability in sorted(
        distribution.items(), key=lambda item: item[1], reverse=True
    ):
        label = str(label)
        if label == section or label in existing_alternatives:
            continue
        alternatives.append(
            {
                "shape": label,
                "confidence": round(float(probability), 4),
                "entity_type": resolve_entity(label).category,
            }
        )
        existing_alternatives.add(label)
        if len(alternatives) >= 5:
            break

    text_features = {
        "engineered": extract_structural_features(normalized),
        "model_label": model_label,
        "model_probability": model_probability,
        "exact_section_candidates": [
            candidate.to_dict() for candidate in exact_candidates
        ],
        "wildcard_candidates": [hit.to_dict() for hit in wildcard_hits],
        "family_fallback": (
            family_prediction.to_dict()
            if family_prediction is not None
            else {"label": "", "probability": 0.0}
        ),
        "distribution": distribution,
        "extraction_confidence": extraction_confidence,
        "extraction_status": token_record.get("extraction_status")
        or token_record.get("status"),
        "extraction_diagnostics": token_record.get("diagnostics") or {},
        "context": token_record.get("context") or {},
        "surrounding_text": token_record.get("surrounding_text") or "",
        "normalized_text": normalized,
        "page": token_record.get("page"),
        "bbox": token_record.get("bbox"),
        "line": line_info or None,
        "block": block_info or None,
        "reading_order": token_record.get("reading_order"),
        "rotation": token_record.get("rotation"),
        "font_size": token_record.get("font_size"),
        "neighbors": (
            (token_record.get("context") or {}).get("neighbor_text") or []
        ),
        "quantity": token_record.get("quantity"),
        "line_context": (
            (token_record.get("context") or {}).get("line_text") or ""
        ),
        "nearby_dimensions": (
            (token_record.get("context") or {}).get("nearby_dimensions")
            or []
        ),
    }

    canonical_dict = canonical.model_dump(mode="json")
    extras = {
        "object_id": str(token_record.get("token_id") or component_id),
        "document_id": document_id,
        "component_id": component_id,
        "raw_text": raw_text,
        "corrected_text": output_corrected_text,
        "normalized_text": normalized,
        "original_token": raw_text,
        "corrected_token": output_corrected_text,
        "page_number": token_record.get("page"),
        "bounding_box": token_record.get("bbox"),
        "evidence_source": (
            ["annotation"]
            if confirmed_plate_type
            else [
                name
                for name, is_available in available.items()
                if is_available and name != "database"
            ]
            + ["fusion"]
        ),
        "prediction_source": (
            "Annotation"
            if confirmed_plate_type
            else (
                "Correction"
                if final_correction and output_corrected_text != normalized
                else "Geometry"
                if not raw_text and geometry.get("geometry_embedding")
                else "Fusion"
            )
        ),
        "section_prediction_not_applicable": bool(confirmed_plate_type),
        "plate_annotation_type": confirmed_plate_type,
        "missing_label_prediction": (
            {
                "predicted_missing_label": section,
                "family": family,
                "member_role": rules.member_role
                or graph.get("graph_prediction"),
                "confidence": round(confidence_value, 4),
                "reason": ai_reasons,
            }
            if not raw_text
            else None
        ),
        # Additive: lets consumers distinguish "known dimensions, missing
        # thickness, N catalog-valid completions" from an ordinary
        # correction/prediction without guessing from review_reason text.
        "completion_status": (
            "missing_thickness" if hss_completions else "complete"
        ),
        "known_dimensions": list(hss_dimensions) if hss_dimensions else None,
        "candidate_sections": [
            item.to_dict() for item in hss_completions
        ] or None,
        "semantic_candidates": (
            anonymous_resolution.get("semantic_candidates")
            if anonymous_resolution
            else None
        ),
        "context_evidence": token_record.get("context_evidence"),
        "evidence_summary": (
            (anonymous_resolution or {}).get("evidence_summary")
            or (token_record.get("context_evidence") or {}).get("evidence_summary")
        ),
        "_skip_unknown_queue": bool(token_record.get("_skip_unknown_queue")),
        "correction": final_correction,
        "annotation_interpretation": annotation_pack,
        "entity_type": entity.category,
        "category": entity.category,
        "category_label": entity.category_label,
        "entity": entity.to_dict(),
        "material": rules.material_grade,
        "alternatives": alternatives[:5],
        "review_status": review_status,
        "abstention_reason": abstention_reason,
        # Canonical contract (see services.prediction.canonical_contract).
        # New consumers should read from here rather than guessing across
        # the legacy top-level aliases kept below for migration.
        "canonical": canonical_dict,
        "source_text": canonical_dict["source_text"],
        "comparison": canonical_dict["comparison"],
        "decision": canonical_dict["decision"],
        "ranking_score": canonical_dict["prediction"]["ranking_score"],
        "final_confidence": canonical_dict["prediction"]["final_confidence"],
        "confidence_is_calibrated": canonical_dict["prediction"][
            "confidence_is_calibrated"
        ],
        "canonical_candidates": canonical_dict["candidates"],
        "catalog_version": canonical_dict["catalog_version"],
        "needs_review": canonical_dict["needs_review"],
        "review_reason": canonical_dict["review_reason"],
        "region_id": token_record.get("region_id"),
        "schedule_sourced": bool(token_record.get("schedule_sourced")),
        "geometry_associated": bool(token_record.get("geometry_associated")),
        "spatial_association": token_record.get("spatial_association"),
        "document_prior_applied": bool(document_prior.get("enabled")),
        # Internal only — lets predict_token() keep needs_review/review_reason
        # in sync after it recomputes review_status from regex matching.
        # Popped before the response is returned; not part of the contract.
        "_ranking_near_tie": ranking.near_tie,
        "geometry_preview": geometry.get("object"),
        "graph_preview": {
            "degree": graph.get("degree"),
            "structural_links": graph.get("structural_links"),
            "min_distance": graph.get("min_distance"),
            "consistency": graph_consistency,
        },
        "shape": (db_exact or {}).get("shape"),
        "type": (db_exact or {}).get("type"),
        "known": database_verified,  # AISC confirmed — not "AI known"
        "aisc_confirmed": database_verified,
        "features": {
            "text": text_features,
            "ocr": encodings["ocr"].to_dict(include_vector=False),
            "layout": encodings["layout"].to_dict(include_vector=False),
            "geometry": {
                **{
                    key: value
                    for key, value in geometry.items()
                    if key != "geometry_embedding"
                },
                "embedding_dimension": len(
                    geometry.get("geometry_embedding") or []
                ),
            },
            "graph": {
                **{
                    key: value
                    for key, value in graph.items()
                    if key != "graph_embedding"
                },
                "embedding_dimension": len(graph.get("graph_embedding") or []),
            },
            "database": {
                "exact_match": db_exact,
                "similar_shapes": similar,
                "role": "verification_only",
                "verified_prediction": database_verified,
                "verified_shape": (db_exact or {}).get("shape"),
                "verified_type": (db_exact or {}).get("type"),
            },
            "engineering_rules": rules.to_dict(),
            "fusion": {
                "engine": unified_multimodal_fusion.name,
                "signals": signals,
                "evidence_contributions": evidence,
                "available_modalities": available,
                "weights": dict(contributions_for_display),
                "attention": unified_fusion.attention.to_dict(),
                "fused_features": unified_fusion.fused_features.to_dict(),
                "encodings": {
                    name: encoding.to_dict(include_vector=False)
                    for name, encoding in encodings.items()
                },
                "candidate_scores": unified_fusion.candidate_scores,
                "contribution_percentages": {
                    name: round(value * 100.0, 1)
                    for name, value in contributions_for_display.items()
                },
                "detected_issues": sorted(set(issues)),
                "ai_first": True,
                "database_decides_prediction": False,
                "component_id": component_id,
                "material": rules.material_grade,
            },
        },
        "prediction_details": {
            "label": section,
            "probability": round(model_probability, 4),
            "target": (
                "exact_section"
                if exact_candidates
                else "correction_candidate"
            ),
            "family": {"label": family, "probability": round(family_probability, 4)},
            "top_classes": [
                {"class": a["shape"], "probability": a["confidence"]}
                for a in alternatives[:5]
            ],
            "family_fallback": (
            family_prediction.to_dict()
            if family_prediction is not None
            else {"label": "", "probability": 0.0}
        ),
        },
    }

    return to_token_prediction(
        token=raw_text or normalized,
        family=family,
        section=section,
        confidence=confidence,
        explanation=explanation,
        evidence=evidence,
        database_match=database_verified,
        extras=extras,
    )


def predict_token(
    token: str,
    *,
    source_file: str = "",
    queue_unknown: bool = False,
    persist_learning: bool = True,
) -> Dict[str, Any]:
    """Token-only AI prediction (used by /api/analyze and takeoff export)."""

    from services.dataset_manager import dataset_manager
    from services.regex_knowledge_base import knowledge_base
    from services.regex_validator import full_match
    from services.self_learning_engine import process_token

    token = str(token).strip()
    context = {
        "token": {
            "text": token,
            "normalized_text": token.upper().replace(" ", ""),
            "confidence": 0.5,
            "token_id": f"token:{token}",
        },
        "geometry": {"objects": []},
        "graph": {"nodes": [], "edges": []},
        "source_file": source_file,
    }
    result = predict_from_context(context)
    section = result["section"]
    family = result.get("family")

    # Dynamic regex remains an output helper and cannot change AI confidence.
    conf = dict(result.get("confidence") or {})
    result["confidence"] = conf

    # Carry forward the REAL issues/gate signals predict_from_context already
    # computed (protected_label_conflict, retrieval_gate_failed, ...) rather
    # than recomputing review_status from an empty issues list. Discarding
    # them here previously let a genuine protected-label conflict (exact
    # text kept, but fusion/graph disagreed -- see the protected-exact-label
    # path above) come back as review_status="auto_accepted" from this
    # token-only entry point, even though a human is supposed to look at it.
    inner_issues = list(
        (result.get("features") or {}).get("fusion", {}).get("detected_issues") or []
    )
    protected_label_conflict = "protected_label_conflict" in inner_issues
    confirmed_plate = bool(result.get("section_prediction_not_applicable"))
    abstain = "retrieval_gate_failed" in inner_issues or (
        not section and not confirmed_plate
    )

    review_status = decide_review_status(
        confidence=float(conf.get("overall") or 0.0),
        issues=inner_issues,
        corrected=False,
        regex_matches=True,
        model_probability=float(conf.get("model_probability") or 0.0),
        database_verified=bool(result.get("database_match")),
        abstain=abstain,
        protected_label_conflict=protected_label_conflict,
    )
    result["review_status"] = review_status
    # Recomputed with the same inputs as review_status just above, so the two
    # stay consistent — the inner predict_from_context() abstention_reason
    # would otherwise go stale relative to this final, regex-informed status.
    result["abstention_reason"] = determine_abstention_reason(
        review_status=review_status,
        confidence=float(conf.get("overall") or 0.0),
        issues=inner_issues,
        model_probability=float(conf.get("model_probability") or 0.0),
        database_verified=bool(result.get("database_match")),
        regex_matches=True,
        protected_label_conflict=protected_label_conflict,
        retrieval_gate_failed=abstain,
    )
    result["uncertain"] = review_status == "pending_review"

    # review_status above is recomputed from fusion/gate signals after the
    # canonical contract was already built inside predict_from_context —
    # refresh needs_review/review_reason so they reflect this final status.
    near_tie = bool(result.pop("_ranking_near_tie", False))
    match_status = str((result.get("comparison") or {}).get("match_status") or "unresolved")
    needs_review, review_reason = determine_review_from_status(
        match_status=match_status, near_tie=near_tie, review_status=review_status
    )
    result["needs_review"] = needs_review
    result["review_reason"] = review_reason
    if isinstance(result.get("canonical"), dict):
        result["canonical"]["needs_review"] = needs_review
        result["canonical"]["review_reason"] = review_reason

    # --- Self-learning persistence gate --------------------------------
    # Only a trusted, human-verifiable resolution may be learned into the
    # self-learning regex knowledge base as ground truth: an exact catalog
    # match read straight from source text, or a safe formatting-only
    # normalization that resolves to one (canonical_contract.MatchStatus
    # EXACT_MATCH / NORMALIZED_MATCH -- the same two statuses
    # canonical_contract accepts as ``final_label`` without nulling it).
    # ``needs_review`` is checked too, on top of ``match_status``, so a
    # near-tie or protected-label conflict layered on an otherwise-exact
    # match still blocks learning. Everything else -- fuzzy correction,
    # wildcard/mask completion, ranker prediction, geometry-only inference,
    # ambiguous OCR, anything requiring review -- may still be SHOWN as a
    # suggestion (via ``learning``/``suggested_regex`` below) but must never
    # be merged into the knowledge base as an example (``learn=False``).
    trusted_match = match_status in {"exact_match", "normalized_match"}
    learn_from_prediction = trusted_match and not needs_review
    learning = process_token(
        section, token, persist=persist_learning, learn=learn_from_prediction
    )
    regex = learning.pattern
    regex_matches = learning.matched or full_match(regex, token)
    result["regex"] = regex
    result["suggested_regex"] = learning.detail.get("candidate_pattern", regex)
    result["regex_matches_token"] = regex_matches
    result["learning"] = learning.to_dict()
    result["regex_variants"] = (
        (knowledge_base.get(section) or {}).get("variants", []) if section else []
    )
    result["validation"] = {
        "matched": regex_matches,
        "regex_confidence": round(learning.regex_confidence, 4),
        "regex_level": learning.regex_level,
        "database_verified": bool(result.get("database_match")),
    }

    unknown_id = None
    if queue_unknown and review_status == "pending_review":
        queued = dataset_manager.enqueue_unknown(
            token=token,
            prediction=section or family or "",
            model_probability=float(conf.get("model_probability") or 0.0),
            overall_confidence=float(conf.get("overall") or 0.0),
            confidence_level=str(conf.get("level") or "Low"),
            uncertain=True,
            source_file=source_file,
            regex_suggested=result.get("suggested_regex") or "",
            category=result.get("category"),
        )
        unknown_id = queued.get("id") if queued else None
        result["review_status"] = "queued" if unknown_id else "already_reviewed"
    result["unknown_id"] = unknown_id
    return result
