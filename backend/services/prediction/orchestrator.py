"""
AI-primary prediction orchestrator.

All production prediction entry points should call ``predict_token`` or
``predict_from_context``. The database never selects ``family`` or ``section``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.component_tracker import allocate_component_id
from services.database_loader import (
    catalog_version as aisc_catalog_version,
    lookup_shape,
    search_similar_shapes,
)
from services.engineering.rule_engine import evaluate_engineering_rules
from services.entity_taxonomy import resolve_entity
from services.exact_section_predictor import (
    predict_exact_sections,
    predict_exact_sections_for_labels,
)
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
from services.prediction.calibration import calibrate_score
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
from services.prediction.review_policy import decide_review_status
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


def _is_structural_family(label: Optional[str]) -> bool:
    return str(label or "").strip().upper() in STRUCTURAL_FAMILIES


def predict_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full multimodal prediction for one token context.

    Context keys: token, document?, geometry?, graph?, source_file?
    """

    token_record = context["token"]
    original = str(token_record.get("text") or "")
    normalized = str(token_record.get("normalized_text") or original).strip()
    source_file = str(
        context.get("source_file")
        or (context.get("document") or {}).get("source_file")
        or ""
    )

    family_prediction = predict_with_confidence(normalized)
    family_label = family_prediction.label
    family_probability = float(family_prediction.probability)

    geometry = context.get("geometry_features") or _geometry_provider.extract(context)
    graph = context.get("graph_features") or _graph_provider.extract(context)

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
        match_wildcard_mask(original or normalized, limit=8) if used_wildcards else []
    )

    # Single exact-section AI call with multimodal rerank (Priority 1).
    exact_candidates = []
    if wildcard_hits:
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
            limit=8,
            geometry=geometry,
            graph=graph,
            engineering_rules=provisional_rules.to_dict(),
        )

    expected_family = (
        str(family_label) if _is_structural_family(family_label) else None
    )
    corrections = suggest_token_corrections(
        original or normalized,
        expected_family=expected_family,
        geometry=geometry,
        graph=graph,
        engineering_context=provisional_rules.to_dict(),
        similarity_candidates=exact_candidates,
        limit=8,
    )
    fusion_candidates: List[Any] = list(exact_candidates)
    existing_shapes = {candidate.shape for candidate in exact_candidates}
    for correction in corrections:
        if correction.corrected in existing_shapes:
            continue
        fusion_candidates.append(
            {
                "shape": correction.corrected,
                "evidence": {
                    "text": float(correction.confidence),
                    "geometry": float(geometry.get("similarity") or 0.35),
                    "graph": float(graph.get("graph_consistency") or 0.35),
                    "engineering_rules": float(provisional_rules.score),
                },
            }
        )
    if not fusion_candidates and family_label:
        fusion_candidates.append(
            {
                "shape": str(family_label),
                "evidence": {
                    "text": family_probability,
                    "geometry": float(geometry.get("similarity") or 0.35),
                    "graph": float(graph.get("graph_consistency") or 0.35),
                    "engineering_rules": float(provisional_rules.score),
                },
            }
        )

    encodings = encoder_registry.encode_all(
        {
            "text": {
                "token": normalized,
                "model_probability": (
                    float(exact_candidates[0].confidence)
                    if exact_candidates
                    else family_probability
                ),
                "extraction_confidence": float(
                    token_record.get("confidence") or 0.5
                ),
                "regex_confidence": 0.0,
                "candidates": exact_candidates,
            },
            "ocr": {
                "original": original,
                "corrected": (
                    corrections[0].corrected if corrections else normalized
                ),
                "confidence": float(token_record.get("confidence") or 0.5),
                "repairs": (
                    (token_record.get("diagnostics") or {}).get(
                        "ocr_repairs"
                    )
                    or []
                ),
            },
            "layout": {
                "bbox": token_record.get("bbox"),
                "page": token_record.get("page"),
                "reading_order": token_record.get("reading_order"),
                "font_size": token_record.get("font_size"),
                "rotation": token_record.get("rotation"),
                "member_role": token_record.get(
                    "engineering_object_type"
                ),
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
        fallback_section=normalized or str(family_label or ""),
    )
    section = unified_fusion.section
    corrected = section
    ai_reasons = list(unified_fusion.reasons)
    model_label = section
    model_probability = float(unified_fusion.confidence)
    distribution = {
        item["shape"]: float(item["score"])
        for item in unified_fusion.candidate_scores
    }
    family = derive_family_from_section(section, fallback=family_label)

    # Priority 6 — database verification only (never overrides section/family).
    db_exact = lookup_shape(section)
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

    extraction_confidence = float(token_record.get("confidence") or 0.5)
    text_similarity = min(
        1.0,
        0.70 * model_probability
        + 0.20 * extraction_confidence
        + 0.10 * regex_contribution,
    )
    geometry_similarity = float(geometry.get("similarity") or 0.35)
    graph_consistency = float(graph.get("graph_consistency") or 0.35)

    signals = {
        "text": text_similarity,
        "ocr": float(encodings["ocr"].confidence),
        "layout": float(encodings["layout"].confidence),
        "geometry": geometry_similarity,
        "graph": graph_consistency,
        "engineering_rules": rule_score,
        # Database is recorded for verification/explanation only.
        "database": db_similarity if database_verified else min(0.35, db_similarity),
    }
    available = {
        "text": True,
        "ocr": bool(encodings["ocr"].available),
        "layout": bool(encodings["layout"].available),
        "geometry": bool(geometry.get("available")),
        "graph": float(graph.get("degree") or 0) > 0,
        "engineering_rules": True,
        "database": True,
    }

    confidence_value = float(unified_fusion.confidence)
    confidence = {
        "overall": round(confidence_value, 4),
        "score": round(confidence_value, 4),
        "level": level_from_score(confidence_value),
        "model_probability": round(model_probability, 4),
        "regex_confidence": round(regex_contribution, 4),
        "database_signal": 1.0 if database_verified else 0.0,
        "breakdown": {
            "ai": round(model_probability, 4),
            **{
                name: round(float(value), 4)
                for name, value in unified_fusion.contributions.items()
            },
        },
        "weights": dict(unified_fusion.contributions),
        "database_role": "verification_only",
    }
    # Contribution scores are normalized attention shares, not raw similarities.
    evidence = dict(unified_fusion.contributions)
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
            "original_token": original,
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
            "object": geometry.get("object"),
            "similarity": round(geometry_similarity, 4),
            "source": geometry.get("source"),
        },
        graph_evidence={
            "degree": graph.get("degree"),
            "structural_links": graph.get("structural_links"),
            "min_distance": graph.get("min_distance"),
            "consistency": round(graph_consistency, 4),
        },
        engineering_evidence={
            "score": round(rule_score, 4),
            "member_role": rules.member_role,
            "material_grade": rules.material_grade,
        },
    )
    explanation["contributions"] = {
        name: round(value, 4)
        for name, value in unified_fusion.contributions.items()
    }
    explanation["contribution_percentages"] = {
        name: round(value * 100.0, 1)
        for name, value in unified_fusion.contributions.items()
    }
    explanation["attention"] = unified_fusion.attention.to_dict()
    explanation["candidate_scores"] = unified_fusion.candidate_scores
    explanation["encoders"] = {
        name: encoding.encoder for name, encoding in encodings.items()
    }
    if corrections:
        correction_payload = corrections[0].to_dict()
        explanation["correction"] = correction_payload
        reviewed_example = (
            correction_payload.get("evidence") or {}
        ).get("reviewed_example")
        explanation["correction_history"] = (
            [reviewed_example] if reviewed_example else []
        )

    # Entity metadata — AI family/section first; AISC only for category enrichment.
    entity = resolve_entity(
        section,
        aisc_type=None,  # do not let AISC override class_name
        model_class=family or family_label,
        database_type=(db_exact or {}).get("type"),
    )

    issues = detect_extraction_issues(token_record)
    if corrected != normalized:
        issues.append("automatic_correction_suggested")
    if not database_verified:
        issues.append("database_unverified")
    if rule_score < 0.55:
        issues.append("engineering_rule_conflict")
    if geometry.get("available") and geometry_similarity < 0.45:
        issues.append("geometry_conflict")
    if float(graph.get("degree") or 0) > 0 and graph_consistency < 0.45:
        issues.append("graph_conflict")

    review_status = decide_review_status(
        confidence=float(confidence["overall"]),
        issues=issues,
        corrected=corrected != normalized,
        regex_matches=bool(regex_contribution),
        model_probability=model_probability,
        database_verified=database_verified,
    )

    component_id = allocate_component_id(
        role=rules.member_role or entity.category,
        page=token_record.get("page"),
        bbox=token_record.get("bbox"),
        text=section,
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
        extraction_method="pdf_text" if bbox else "unknown",
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
    if not alternatives:
        for label, probability in sorted(
            distribution.items(), key=lambda item: item[1], reverse=True
        )[:4]:
            if str(label) != section:
                alternatives.append(
                    {
                        "shape": str(label),
                        "confidence": round(float(probability), 4),
                        "entity_type": resolve_entity(str(label)).category,
                    }
                )

    text_features = {
        "engineered": extract_structural_features(normalized),
        "model_label": model_label,
        "model_probability": model_probability,
        "exact_section_candidates": [
            candidate.to_dict() for candidate in exact_candidates
        ],
        "wildcard_candidates": [hit.to_dict() for hit in wildcard_hits],
        "family_fallback": family_prediction.to_dict(),
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
        "original_token": original,
        "corrected_token": corrected,
        "correction": corrections[0].to_dict() if corrections else None,
        "entity_type": entity.category,
        "category": entity.category,
        "category_label": entity.category_label,
        "entity": entity.to_dict(),
        "material": rules.material_grade,
        "alternatives": alternatives[:4],
        "review_status": review_status,
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
            "ocr": encodings["ocr"].to_dict(),
            "layout": encodings["layout"].to_dict(),
            "geometry": geometry,
            "graph": graph,
            "database": {
                "exact_match": db_exact,
                "similar_shapes": similar,
                "best_similarity": best_similarity,
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
                "weights": dict(unified_fusion.contributions),
                "attention": unified_fusion.attention.to_dict(),
                "fused_features": unified_fusion.fused_features.to_dict(),
                "encodings": {
                    name: encoding.to_dict()
                    for name, encoding in encodings.items()
                },
                "candidate_scores": unified_fusion.candidate_scores,
                "contribution_percentages": {
                    name: round(value * 100.0, 1)
                    for name, value in unified_fusion.contributions.items()
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
            "target": "exact_section" if exact_candidates else "family_fallback",
            "family": {"label": family, "probability": round(family_probability, 4)},
            "top_classes": [
                {"class": a["shape"], "probability": a["confidence"]}
                for a in alternatives[:4]
            ],
            "family_fallback": family_prediction.to_dict(),
        },
    }

    return to_token_prediction(
        token=original or normalized,
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

    learning = process_token(section, token, persist=persist_learning)
    regex = learning.pattern
    regex_matches = learning.matched or full_match(regex, token)
    result["regex"] = regex
    result["suggested_regex"] = learning.detail.get("candidate_pattern", regex)
    result["regex_matches_token"] = regex_matches
    result["learning"] = learning.to_dict()
    result["regex_variants"] = (
        (knowledge_base.get(section) or {}).get("variants", []) if section else []
    )

    # Refresh confidence regex signal for token-only path.
    conf = dict(result.get("confidence") or {})
    conf["regex_confidence"] = round(float(learning.regex_confidence), 4)
    result["confidence"] = conf
    result["validation"] = {
        "matched": regex_matches,
        "regex_confidence": round(learning.regex_confidence, 4),
        "regex_level": learning.regex_level,
        "database_verified": bool(result.get("database_match")),
    }

    review_status = decide_review_status(
        confidence=float(conf.get("overall") or 0.0),
        issues=[] if regex_matches else ["regex_mismatch"],
        corrected=False,
        regex_matches=regex_matches,
        model_probability=float(conf.get("model_probability") or 0.0),
        database_verified=bool(result.get("database_match")),
    )
    result["review_status"] = review_status
    result["uncertain"] = review_status == "pending_review"

    # review_status above is recomputed from regex matching after the
    # canonical contract was already built inside predict_from_context —
    # refresh needs_review/review_reason so they reflect this final status
    # rather than the one computed before regex learning ran.
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
