/**
 * Sole boundary for reading the semantic_preprocessor contract
 * (SemanticDocument / SemanticAnnotation / Correction / GeometryEvidence).
 * Components read annotation state through these helpers -- never by
 * poking `.correction.operation` etc. directly in JSX -- so the visual
 * language (colors, labels, badges) stays defined in exactly one place.
 *
 * Backend shape reference: backend/services/semantic_preprocessor/models.py
 */

export const OPERATION = {
  NONE: "none",
  NORMALIZATION: "normalization",
  REPAIR: "repair",
  COMPLETION: "completion",
};

export const REVIEW_STATUS = {
  ACCEPTED: "accepted",
  AUTO_ACCEPTED: "auto_accepted",
  NEEDS_REVIEW: "needs_review",
  PENDING: "pending",
};

const OPERATION_META = {
  [OPERATION.NORMALIZATION]: {
    label: "Normalized",
    short: "N",
    colorKey: "info",
    explanation: "Equivalent representation only. No new structural information was inferred.",
  },
  [OPERATION.REPAIR]: {
    label: "Repaired",
    short: "R",
    colorKey: "warning",
    explanation: "Original text appears corrupted. Replacement selected from valid structural candidates.",
  },
  [OPERATION.COMPLETION]: {
    label: "Completed",
    short: "C",
    colorKey: "success",
    explanation: "Missing structural information was filled using a source-verified rule from this drawing.",
  },
  [OPERATION.NONE]: {
    label: "Unchanged",
    short: "—",
    colorKey: "neutral",
    explanation: "Text already matched its canonical structural designation.",
  },
};

export function getOperation(annotation) {
  return annotation?.correction?.operation || OPERATION.NONE;
}

export function getOperationMeta(operation) {
  return OPERATION_META[operation] || OPERATION_META[OPERATION.NONE];
}

export function hasGeometryConflict(annotation) {
  return (annotation?.geometry_associations || []).some((candidate) =>
    (candidate.association_reason || []).some((reason) =>
      reason === "GHX_PDF_DISAGREEMENT" || reason === "AMBIGUOUS_MULTIPLE_BEAMS",
    ),
  );
}

export function isDemoSynthetic(annotation) {
  return (annotation?.correction?.reason_codes || []).includes("demo_synthetic_case");
}

/**
 * Overlay visual treatment for one annotation. Two independent channels,
 * not one seven-color palette: `colorKey` signals review urgency (four
 * hues total: neutral / info / warning / success, plus error reserved for
 * a genuine geometry conflict), `dashed` is the second, color-independent
 * signal for "needs a human" so the distinction never depends on color
 * alone.
 */
export function getOverlayStyle(annotation) {
  const operation = getOperation(annotation);
  const conflict = hasGeometryConflict(annotation);
  const needsReview = annotation?.review_status === REVIEW_STATUS.NEEDS_REVIEW;

  let colorKey = OPERATION_META[operation].colorKey;
  if (conflict) colorKey = "error";
  else if (needsReview) colorKey = "warning";

  return {
    colorKey,
    dashed: needsReview || conflict,
    badge: OPERATION_META[operation].short,
  };
}

export function annotationsForPage(document, pageNumber) {
  if (!document?.annotations) return [];
  return document.annotations.filter((a) => Number(a.page) === Number(pageNumber));
}

export function needsReviewAnnotations(document) {
  if (!document?.annotations) return [];
  return document.annotations.filter((a) => a.review_status === REVIEW_STATUS.NEEDS_REVIEW);
}

/** Every distinct source-verified drawing rule referenced by any annotation,
 * for the Document Intelligence panel. */
export function drawingRules(document) {
  return document?.drawing_language_rules || [];
}

export function ruleById(document, ruleId) {
  return drawingRules(document).find((r) => r.rule_id === ruleId) || null;
}

/** The evidence rule(s) behind a completion, resolved to full rule objects
 * (with source page/bbox/quote) via `correction.evidence_ids`. */
export function evidenceRulesFor(document, annotation) {
  const ids = new Set(annotation?.correction?.evidence_ids || []);
  if (!ids.size) return [];
  return drawingRules(document).filter((r) => ids.has(r.rule_id));
}

export function primaryGeometryAssociation(annotation) {
  const list = annotation?.geometry_associations || [];
  if (!list.length) return null;
  return [...list].sort((a, b) => (b.score ?? -1) - (a.score ?? -1))[0];
}

export function geometryForId(document, geometryId) {
  return (document?.grasshopper_geometry || []).find((g) => g.geometry_id === geometryId) || null;
}
