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
  NONE: "keep",
  NORMALIZATION: "normalization",
  REPAIR: "repair",
  COMPLETION: "completion",
};

export const REVIEW_STATUS = {
  HUMAN_ACCEPTED: "human_accepted",
  HUMAN_REJECTED: "human_rejected",
  AUTO_ACCEPTED: "auto_accepted",
  NEEDS_REVIEW: "needs_review",
  PENDING: "pending",
  UNRESOLVED: "unresolved",
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
    (candidate.reason_codes || []).some((reason) =>
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

  const meta = getOperationMeta(operation);
  let colorKey = meta.colorKey;
  if (conflict) colorKey = "error";
  else if (needsReview) colorKey = "warning";

  return {
    colorKey,
    dashed: needsReview || conflict,
    badge: meta.short,
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
  const scoreOf = (c) => c.score?.value ?? -1;
  return [...list].sort((a, b) => scoreOf(b) - scoreOf(a))[0];
}

export function geometryForId(document, geometryId) {
  return (document?.grasshopper_geometry || []).find((g) => g.geometry_id === geometryId) || null;
}

/** Ranked repair proposals attached by services.semantic.repair_shadow, if any. */
export function getRepairCandidates(annotation) {
  return annotation?.repair_candidates || [];
}

/** The most recent NOT-yet-accepted repair proposal operation, if one
 * exists -- this is what "Accept" acts on by default. Distinct from
 * `correction` (which only ever reflects the currently ACCEPTED value). */
export function getPendingProposalOperation(annotation) {
  const ops = annotation?.operations || [];
  for (let i = ops.length - 1; i >= 0; i -= 1) {
    if (ops[i].operation === OPERATION.REPAIR && !ops[i].accepted) return ops[i];
  }
  return null;
}

/**
 * Honest, kind-aware caption for a ScoreValue (Section 8 of the repair-
 * trace brief) -- a raw ranker score must never be captioned as though it
 * were a calibrated probability. One place to read `score.kind` so no
 * component has to know the taxonomy itself.
 */
const SCORE_KIND_LABELS = {
  raw_model_score: "Model score",
  calibrated_probability: "Confidence",
  rule_confidence: "Rule confidence",
  association_distance: "Distance",
  deterministic: "Deterministic",
  similarity_ratio: "Similarity",
};

export function describeScore(score) {
  if (!score) return null;
  const label = SCORE_KIND_LABELS[score.kind] || score.kind;
  if (score.calibrated && score.kind === "calibrated_probability") {
    return { label, valueText: `${Math.round(score.value * 100)}%`, calibrated: true };
  }
  return { label, valueText: score.value.toFixed(3), calibrated: false };
}

/**
 * Real per-annotation process steps for the compact vertical timeline
 * (Section 15) -- every step is derived from fields the backend actually
 * populated, never a hand-written demo narrative.
 */
export function getProcessSteps(annotation) {
  if (!annotation) return [];
  const parse = annotation.structural_parse;
  const candidates = getRepairCandidates(annotation);
  const pending = getPendingProposalOperation(annotation);
  const steps = [
    { key: "extracted", label: "Extracted", status: "done", detail: annotation.extraction_source || "Native PDF text" },
  ];

  if (annotation.grouping_reasons?.length) {
    steps.push({
      key: "grouped",
      label: "Grouped into one label",
      status: "done",
      detail: annotation.grouping_reasons.join(", "),
    });
  }

  if (parse) {
    if (!parse.is_structural) {
      steps.push({ key: "parse", label: "Not a recognized structural designation", status: "warning", detail: parse.parser_reason });
    } else if (parse.grammar === "incomplete") {
      steps.push({ key: "parse", label: "Structural family detected, missing size", status: "warning", detail: `Family ${parse.family}` });
    } else if (!parse.catalog_exact_match) {
      steps.push({ key: "parse", label: "Structural shape parsed, not an exact catalog match", status: "warning", detail: `Family ${parse.family}` });
    } else {
      steps.push({ key: "parse", label: "Exact catalog designation", status: "done", detail: `Family ${parse.family}` });
    }
  }

  if (candidates.length > 0) {
    steps.push({
      key: "candidates",
      label: `${candidates.length} repair candidate${candidates.length > 1 ? "s" : ""} found`,
      status: "done",
      detail: candidates[0].candidate_text,
    });
  }

  const status = annotation.review_status;
  if (status === REVIEW_STATUS.NEEDS_REVIEW) {
    steps.push({ key: "review", label: "Human review required", status: "warning", detail: annotation.review?.reason });
  } else if (status === REVIEW_STATUS.HUMAN_ACCEPTED) {
    steps.push({ key: "review", label: "Human accepted", status: "done" });
  } else if (status === REVIEW_STATUS.HUMAN_REJECTED) {
    steps.push({ key: "review", label: "Human rejected the proposal", status: "error" });
  } else if (status === REVIEW_STATUS.AUTO_ACCEPTED) {
    steps.push({ key: "review", label: "Auto-accepted (deterministic)", status: "done" });
  }

  if (pending) {
    steps.push({ key: "pending", label: "Correction pending confirmation", status: "pending", detail: pending.output_text });
  } else {
    steps.push({ key: "final", label: `Final: ${annotation.effective_text}`, status: "done" });
  }

  return steps;
}
