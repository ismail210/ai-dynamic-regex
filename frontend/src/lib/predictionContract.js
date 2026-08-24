/**
 * Prediction contract helpers.
 *
 * `getCanonical*` functions below read the canonical backend contract (see
 * backend/services/prediction/canonical_contract.py) and are the preferred
 * way to read a prediction going forward — they never guess across
 * differently-named aliases.
 *
 * The plain `get*` functions further down (getSection/getFamily/
 * getConfidence/getExplanation) are the pre-canonical migration adapter: they
 * fall back across legacy field-name variants (`multimodal_confidence`,
 * `overall_confidence`, `prediction`, `predicted_shape`, ...) for responses
 * that predate the canonical contract, or for the few call sites not yet
 * migrated. New code should prefer the canonical helpers.
 * DEPRECATED — remove the fallback chains once every producer/consumer is
 * confirmed on the canonical contract.
 */

const DEFAULT_CANONICAL = {
  object_id: null,
  document_id: null,
  source_text: {
    raw: null,
    normalized: null,
    page_number: null,
    bounding_box: null,
    block_number: null,
    line_number: null,
    word_number: null,
    extraction_method: "unknown",
    available: false,
  },
  prediction: {
    final_label: null,
    family: null,
    ranking_score: 0,
    final_confidence: null,
    confidence_is_calibrated: false,
  },
  comparison: {
    exact_match: false,
    normalized_match: false,
    prediction_required: true,
    match_status: "unresolved",
  },
  decision: {
    source: "none",
    used_text: false,
    used_geometry: false,
    used_graph: false,
    used_engineering_rules: false,
    used_catalog: false,
  },
  candidates: [],
  evidence: {},
  catalog_version: null,
  needs_review: false,
  review_reason: null,
};

/** True once `result` carries the canonical contract (backend has been updated). */
export function hasCanonicalContract(result = {}) {
  return Boolean(result.canonical || result.comparison || result.source_text);
}

/** Shown wherever a legacy prediction would otherwise need to fabricate or
 * omit provenance the pipeline never recorded for it. */
export const LEGACY_PROVENANCE_MESSAGE =
  "Provenance unavailable — this document was analyzed with an older pipeline " +
  "version. Re-analysis is required.";

/**
 * True when a prediction record exists but predates the canonical provenance
 * contract — i.e. it carries none of `canonical`/`comparison`/`source_text`.
 * This is a pipeline-compatibility gap, not a prediction outcome: a genuinely
 * new canonical prediction that happens to resolve to `unresolved` still
 * carries `comparison`/`source_text` (with `available: false`), so it is
 * never misclassified as legacy by this check.
 *
 * The single source of truth for "is this record legacy" — call sites should
 * use this rather than re-deriving the same check from raw fields.
 */
export function isLegacyPrediction(result = {}) {
  return !hasCanonicalContract(result);
}

/** Read the canonical prediction contract, defaulting missing pieces rather
 * than fabricating them — an absent field stays absent/unavailable. */
export function getCanonicalPrediction(result = {}) {
  const canonical = result.canonical || {};
  return {
    objectId: canonical.object_id ?? result.object_id ?? DEFAULT_CANONICAL.object_id,
    documentId:
      canonical.document_id ?? result.document_id ?? DEFAULT_CANONICAL.document_id,
    sourceText: {
      ...DEFAULT_CANONICAL.source_text,
      ...(canonical.source_text || result.source_text || {}),
    },
    prediction: {
      ...DEFAULT_CANONICAL.prediction,
      ...(canonical.prediction || {
        final_label: getSection(result) || null,
        family: getFamily(result) || null,
        ranking_score: result.ranking_score ?? getConfidence(result).overall,
        final_confidence: result.final_confidence ?? null,
        confidence_is_calibrated: result.confidence_is_calibrated ?? false,
      }),
    },
    comparison: {
      ...DEFAULT_CANONICAL.comparison,
      ...(canonical.comparison || result.comparison || {}),
    },
    decision: {
      ...DEFAULT_CANONICAL.decision,
      ...(canonical.decision || result.decision || {}),
    },
    candidates: canonical.candidates || result.canonical_candidates || [],
    evidence: canonical.evidence || result.evidence || {},
    catalogVersion: canonical.catalog_version ?? result.catalog_version ?? null,
    needsReview: canonical.needs_review ?? result.needs_review ?? false,
    reviewReason: canonical.review_reason ?? result.review_reason ?? null,
  };
}

export function getMatchStatus(result = {}) {
  return getCanonicalPrediction(result).comparison.match_status || "unresolved";
}

/** ``{ value, isCalibrated }`` — value is either a calibrated probability
 * (0-1) or the raw ranking/fusion score; callers must label it accordingly
 * and never present an uncalibrated score as a probability. */
export function getDisplayConfidence(result = {}) {
  const { prediction } = getCanonicalPrediction(result);
  if (prediction.confidence_is_calibrated && prediction.final_confidence != null) {
    return { value: prediction.final_confidence, isCalibrated: true };
  }
  return { value: prediction.ranking_score, isCalibrated: false };
}

export function getSection(result = {}) {
  return (
    result.section
    || result.prediction
    || result.predicted_shape
    || result.suggested_shape
    || ""
  );
}

/**
 * What the SECTION cell should actually show. The canonical contract nulls
 * `prediction.final_label` any time the match status requires review (see
 * canonical_contract.MatchStatus / `_REVIEW_REASONS`) — that covers not
 * only the HSS missing-thickness case (several catalog-valid completions,
 * genuine irreducible ambiguity), but ALSO an ordinary "source text isn't a
 * catalog-valid designation at all" correction (match_status
 * "corrected_prediction"), where a fuzzy/fusion guess like W10X24 -> W10X49
 * must not be presented as a resolved answer just because a `section`
 * string exists on the record. Trust `final_label == null` generally, not
 * only when `candidate_sections` (the HSS-specific completion list) happens
 * to be populated — a low-confidence non-HSS correction has no such list,
 * but is exactly as unresolved.
 */
export function getDisplaySection(result = {}) {
  const { prediction, needsReview, reviewReason } = getCanonicalPrediction(result);
  const candidateSections = result.candidate_sections || [];
  if (needsReview && !prediction.final_label) {
    return {
      value: null,
      reviewRequired: true,
      reason: reviewReason,
      hasCandidates: candidateSections.length > 0,
    };
  }
  return { value: getSection(result), reviewRequired: false, reason: null, hasCandidates: false };
}

/**
 * True only for an explicit, persisted human-review resolution (see
 * services.human_selections / services.staged_pipeline
 * ._apply_human_selections) — never inferred from needs_review being false,
 * since plenty of ordinary model-resolved rows also have no review
 * requirement. `decision_source` is the primary signal the backend sets;
 * `match_status === "human_resolved"` is the same fact surfaced through the
 * canonical contract, checked as a fallback for any caller that only has
 * the canonical view.
 */
export function isHumanReviewed(result = {}) {
  if (result.decision_source === "human_review") return true;
  return getCanonicalPrediction(result).comparison.match_status === "human_resolved";
}

/**
 * The one identity a result is keyed by everywhere reviewer state is
 * matched back to a prediction (services.human_selections, the drawing
 * review list, the direct-to-drawing link below) — object_id first, since
 * that is what the backend keys human selections and canonical predictions
 * by; component_id as the only fallback for older/legacy records that
 * predate object_id. Never derived from label text, so it stays correct
 * even when the same designation appears many times on a sheet.
 */
export function getResultKey(result = {}) {
  return String(result.object_id || result.component_id || "");
}

/**
 * URL for jumping straight from a result (Results table, Corrections queue,
 * prediction detail) to its exact source location on Drawing Review —
 * resolved by entity id, never by searching the PDF for label text. This is
 * the one canonical way to link into a located review; Drawing Review reads
 * the same `object` param back out and reuses its existing selection/locate
 * logic (see DrawingReviewPage), so there is a single locate implementation.
 */
export function reviewOnDrawingPath(result = {}) {
  const key = getResultKey(result);
  return key ? `/review-drawing?object=${encodeURIComponent(key)}` : "/review-drawing";
}

/**
 * Catalog-backed structural families — mirrors the structural set in
 * services.prediction.contract.derive_family_from_section, the backend's
 * own definition of "this is an AISC catalog section family". Kept as a
 * literal mirror (not fetched) because it is a small, effectively-closed
 * taxonomy; if the backend set changes, update both.
 *
 * Used only to decide whether the section-review picker (candidates +
 * "Other") applies to a result — never to gate candidate GENERATION, which
 * stays whatever services.hss_completion (or, for other families, nothing
 * yet) actually supports. A family with no generated candidates still gets
 * the picker, just with an empty candidate list and manual "Other" entry
 * only (see SectionReviewSelector).
 */
export const STRUCTURAL_SECTION_FAMILIES = new Set([
  "W", "WT", "S", "M", "HP", "C", "MC", "HSS", "L", "2L", "PIPE", "MT", "ST",
]);

/**
 * True when a result is a catalog-backed structural section review case —
 * eligible for the shared SectionReviewSelector (candidate picker + manual
 * "Other" correction) on both Results and Drawing Review — rather than a
 * non-section annotation (BENT_PLATE, PLATE, DIMENSION, ...) that uses a
 * different, free-text correction path and must never be forced into an
 * AISC section contract.
 *
 * Eligible when the result still needs review (so the reviewer can resolve
 * it) OR was already human-resolved (so the reviewer can revisit/change the
 * decision) — never for an ordinary already-correct exact/normalized match
 * that was never flagged for review.
 *
 * A generated candidate list is itself sufficient evidence (whatever family
 * produced it), independent of whether `family` happens to be populated on
 * this particular record — `family` is the fallback signal for the case
 * that actually needs generalizing: a review-required section with NO
 * candidate list yet (so only manual "Other" entry applies).
 */
export function isSectionReviewEligible(result = {}) {
  if ((result.candidate_sections || []).length > 0) return true;
  const family = String(getFamily(result) || "").toUpperCase();
  if (!STRUCTURAL_SECTION_FAMILIES.has(family)) return false;
  return Boolean(getCanonicalPrediction(result).needsReview) || isHumanReviewed(result);
}

/**
 * Local fallback for the same overlay the backend applies (see
 * services.human_selections.apply_human_selection_overlay) — used only when
 * a save response has no `resolved_prediction` (e.g. the caller didn't have
 * the full prediction object to send). Prefer the server's record when
 * available; this exists so the UI never regresses to "unresolved" while
 * still reflecting the save immediately.
 */
export function buildLocalSelectionOverlay(result = {}, section) {
  const canonical = result.canonical
    ? {
        ...result.canonical,
        prediction: { ...result.canonical.prediction, final_label: section },
        comparison: { ...result.canonical.comparison, match_status: "human_resolved" },
        needs_review: false,
        review_reason: null,
      }
    : result.canonical;
  return {
    ...result,
    section,
    human_selected_section: section,
    decision_source: "human_review",
    needs_review: false,
    review_reason: null,
    canonical,
    comparison: canonical?.comparison || result.comparison,
  };
}

/**
 * Patch the one matching row in shared analysis state (AnalysisContext
 * `data.results`) with a save's resolved record — the single merge used by
 * both Results and Drawing Review after `saveHumanSelection`, so neither
 * page keeps its own copy of "what the human decided". `resolved` should be
 * the API response's `resolved_prediction` when present, else the output of
 * `buildLocalSelectionOverlay`.
 */
export function mergeResolvedPrediction(data, objectId, resolved) {
  if (!data?.results || !resolved) return data;
  return {
    ...data,
    results: data.results.map((row) =>
      getResultKey(row) === objectId ? resolved : row
    ),
  };
}

/**
 * Page + bbox for drawing review. Prefers canonical source_text; falls back
 * to top-level prediction fields used by the multimodal API payload.
 */
export function getPredictionLocation(result = {}) {
  const { sourceText } = getCanonicalPrediction(result);
  const pageNumber = sourceText.page_number ?? result.page_number ?? null;
  const rawBox = sourceText.bounding_box ?? result.bounding_box ?? null;
  const boundingBox =
    Array.isArray(rawBox) && rawBox.length >= 4
      ? rawBox.slice(0, 4).map(Number)
      : null;
  const hasLocation =
    pageNumber != null
    && Number.isFinite(Number(pageNumber))
    && boundingBox != null
    && boundingBox.every((value) => Number.isFinite(value));
  return {
    pageNumber: hasLocation ? Number(pageNumber) : pageNumber != null ? Number(pageNumber) : null,
    boundingBox: hasLocation ? boundingBox : null,
    hasLocation,
  };
}

/** True when the highlight comes from geometry inference, not OCR text. */
export function isInferredLocation(result = {}) {
  const { sourceText, comparison } = getCanonicalPrediction(result);
  return (
    comparison.match_status === "geometry_only"
    || !sourceText.available
    || Boolean(result.missing_label_prediction)
    || result.prediction_source === "Geometry"
  );
}

export function getFamily(result = {}) {
  return (
    result.family
    || result.prediction_details?.family?.label
    || result.prediction_details?.family_fallback?.label
    || result.entity?.class
    || ""
  );
}

export function getConfidence(result = {}) {
  const conf = result.confidence;
  if (typeof conf === "number") {
    return { overall: conf, score: conf, level: confidenceLevel(conf) };
  }
  if (conf && typeof conf === "object") {
    const overall = Number(
      conf.overall ?? conf.score ?? conf.value ?? result.overall_confidence ?? 0
    );
    return {
      ...conf,
      overall,
      score: Number(conf.score ?? overall),
      level: conf.level || confidenceLevel(overall),
    };
  }
  const overall = Number(result.overall_confidence ?? 0);
  return {
    overall,
    score: overall,
    level: result.confidence_level || confidenceLevel(overall),
  };
}

export function getExplanation(result = {}) {
  const explanation = result.explanation || result.reasoning || {};
  return {
    ...explanation,
    prediction: explanation.prediction || {
      family: getFamily(result),
      section: getSection(result),
    },
    confidence: explanation.confidence ?? getConfidence(result).overall,
    top_candidate_sections:
      explanation.top_candidate_sections
      || result.top_candidate_sections
      || result.prediction_details?.top_classes?.map((item) => ({
        shape: item.class,
        score: item.probability,
      }))
      || result.alternatives
      || [],
    why_selected: explanation.why_selected || result.why_selected || explanation.reasons || [],
    why_rejected: explanation.why_rejected || result.why_rejected || [],
    text_evidence: explanation.text_evidence || result.text_evidence || {},
    geometry_evidence: explanation.geometry_evidence || result.geometry_evidence || {},
    graph_evidence: explanation.graph_evidence || result.graph_evidence || {},
    engineering_evidence:
      explanation.engineering_evidence || result.engineering_evidence || {},
  };
}

/** Plain-language explanation, rebuilt from evidence for legacy payloads. */
export function getEngineerExplanation(result = {}) {
  const explanation = getExplanation(result);
  const engineer = explanation.engineer_explanation || {};
  if ((engineer.bullets || []).length > 0) return engineer;

  const evidence = (key) => explanation[key] || {};
  const asPercent = (value) =>
    Number.isFinite(Number(value)) ? `${Math.round(Number(value) * 100)}%` : "—";
  const bullets = [
    `Extracted text reads ${result.raw_text || result.original_token || "—"}${
      result.corrected_text && result.corrected_text !== result.raw_text
        ? `, corrected to ${result.corrected_text}.`
        : "."
    }`,
    evidence("geometry_evidence").available === false
      ? "No geometry was linked to this label."
      : `Drawing geometry agrees at ${asPercent(
          evidence("geometry_evidence").score ?? explanation.geometry_similarity,
        )}.`,
    evidence("graph_evidence").available === false
      ? "No structural connections were linked to this label."
      : `Structural connections agree at ${asPercent(
          evidence("graph_evidence").score ?? explanation.graph_consistency,
        )}.`,
    `Engineering constraints score ${asPercent(
      evidence("engineering_evidence").score,
    )}.`,
    result.aisc_confirmed || result.database_match
      ? "AISC confirms this section is physically plausible."
      : "AISC could not confirm the section; review is recommended.",
  ];
  return {
    summary: engineer.summary || explanation.summary || "",
    bullets,
    aisc_plausibility:
      engineer.aisc_plausibility
      || (result.aisc_confirmed || result.database_match ? "verified" : "unverified"),
  };
}

/** Technical explanation, falling back to modality scores when absent. */
export function getTechnicalExplanation(result = {}) {
  const explanation = getExplanation(result);
  const technical = explanation.ai_engineer_explanation || {};
  return {
    text_confidence: technical.text_confidence ?? explanation.text_similarity ?? 0,
    ocr_confidence: technical.ocr_confidence ?? explanation.ocr_score ?? 0,
    geometry_embedding_similarity:
      technical.geometry_embedding_similarity ?? explanation.geometry_similarity ?? 0,
    graph_embedding_similarity:
      technical.graph_embedding_similarity ?? explanation.graph_consistency ?? 0,
    fusion_score: technical.fusion_score ?? explanation.fusion_score ?? 0,
    confidence_calibration: technical.confidence_calibration || "—",
    database_plausibility_filter:
      technical.database_plausibility_filter
      || (result.aisc_confirmed || result.database_match ? "passed" : "not_verified"),
  };
}

export function confidenceLevel(score) {
  if (score >= 0.8) return "High";
  if (score >= 0.55) return "Medium";
  return "Low";
}
