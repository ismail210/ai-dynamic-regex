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
    annotation_type: null,
    annotation_label: null,
    section_applicable: true,
    confidence_basis: null,
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

function getAnnotationRecord(result = {}) {
  return (
    result.annotation_interpretation?.annotation
    || result.explanation?.annotation_interpretation?.annotation
    || {}
  );
}

/** True when the backend confirmed a plate/bent-plate annotation (no AISC section). */
export function isConfirmedPlateAnnotation(result = {}) {
  const canonical = getCanonicalPrediction(result);
  if (canonical.comparison.match_status === "confirmed_annotation") {
    return true;
  }
  if (result.section_prediction_not_applicable) {
    const annotation = getAnnotationRecord(result);
    const annotationType = String(
      canonical.prediction.annotation_type
      || result.plate_annotation_type
      || annotation.annotation_type
      || "",
    ).toUpperCase();
    if (annotationType === "PLATE" || annotationType === "BENT_PLATE") {
      return Boolean(annotation.structure_confirmed);
    }
  }
  if (
    canonical.prediction.section_applicable === false
    && canonical.prediction.annotation_type
  ) {
    return true;
  }
  return false;
}

export function getAnnotationLabel(result = {}) {
  const { prediction } = getCanonicalPrediction(result);
  if (prediction.annotation_label) {
    return prediction.annotation_label;
  }
  if (result.annotation_label) {
    return result.annotation_label;
  }
  const annotation = getAnnotationRecord(result);
  const thickness = annotation.thickness;
  const annotationType = String(
    prediction.annotation_type
    || result.plate_annotation_type
    || annotation.annotation_type
    || "",
  ).toUpperCase();
  if (thickness) {
    const suffix = annotationType === "BENT_PLATE" ? "BENT PL" : "PL";
    const thickDisplay = String(thickness).includes('"') ? thickness : `${thickness}"`;
    return `${thickDisplay} ${suffix}`.trim();
  }
  return result.raw_text || result.original_token || "";
}

export function getDisplayFamily(result = {}) {
  if (isConfirmedPlateAnnotation(result)) {
    const annotationType = String(
      getCanonicalPrediction(result).prediction.annotation_type
      || result.plate_annotation_type
      || getAnnotationRecord(result).annotation_type
      || "",
    ).toUpperCase();
    return annotationType === "BENT_PLATE" ? "Bent Plate" : "Plate";
  }
  return getFamily(result) || "";
}

export function getDisplaySection(result = {}) {
  if (isConfirmedPlateAnnotation(result)) {
    return {
      value: getAnnotationLabel(result) || "Not applicable",
      reviewRequired: false,
      reason: null,
      hasCandidates: false,
    };
  }
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
