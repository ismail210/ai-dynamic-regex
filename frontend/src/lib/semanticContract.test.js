import { describe, expect, it } from "vitest";
import {
  annotationsForPage,
  describeScore,
  evidenceRulesFor,
  getOperation,
  getOverlayStyle,
  getPendingProposalOperation,
  getProcessSteps,
  getRepairCandidates,
  hasGeometryConflict,
  isDemoSynthetic,
  needsReviewAnnotations,
  OPERATION,
  REVIEW_STATUS,
} from "./semanticContract";

function annotation(overrides = {}) {
  return {
    annotation_id: "ann_1",
    page: 1,
    correction: { operation: OPERATION.NONE, reason_codes: [] },
    geometry_associations: [],
    review_status: REVIEW_STATUS.PENDING,
    ...overrides,
  };
}

describe("getOperation / getOverlayStyle", () => {
  it("normalized annotations get the info color and no dashed border", () => {
    const a = annotation({ correction: { operation: OPERATION.NORMALIZATION, reason_codes: [] } });
    expect(getOperation(a)).toBe(OPERATION.NORMALIZATION);
    expect(getOverlayStyle(a)).toMatchObject({ colorKey: "info", dashed: false });
  });

  it("needs-review annotations are dashed regardless of operation", () => {
    const a = annotation({
      correction: { operation: OPERATION.NORMALIZATION, reason_codes: [] },
      review_status: REVIEW_STATUS.NEEDS_REVIEW,
    });
    expect(getOverlayStyle(a)).toMatchObject({ colorKey: "warning", dashed: true });
  });

  it("a genuine geometry conflict escalates to the error color", () => {
    const a = annotation({
      geometry_associations: [
        { reason_codes: ["GHX_PDF_DISAGREEMENT"] },
      ],
    });
    expect(hasGeometryConflict(a)).toBe(true);
    expect(getOverlayStyle(a).colorKey).toBe("error");
  });

  it("unchanged annotations render neutral", () => {
    expect(getOverlayStyle(annotation()).colorKey).toBe("neutral");
  });
});

describe("isDemoSynthetic", () => {
  it("flags only annotations carrying the demo_synthetic_case reason code", () => {
    const synthetic = annotation({ correction: { operation: OPERATION.REPAIR, reason_codes: ["demo_synthetic_case"] } });
    const real = annotation({ correction: { operation: OPERATION.REPAIR, reason_codes: ["x"] } });
    expect(isDemoSynthetic(synthetic)).toBe(true);
    expect(isDemoSynthetic(real)).toBe(false);
  });
});

describe("annotationsForPage / needsReviewAnnotations", () => {
  const document = {
    annotations: [
      annotation({ annotation_id: "a1", page: 1, review_status: REVIEW_STATUS.NEEDS_REVIEW }),
      annotation({ annotation_id: "a2", page: 2 }),
      annotation({ annotation_id: "a3", page: 1 }),
    ],
  };

  it("filters annotations by page", () => {
    expect(annotationsForPage(document, 1).map((a) => a.annotation_id)).toEqual(["a1", "a3"]);
  });

  it("filters to only needs_review annotations", () => {
    expect(needsReviewAnnotations(document).map((a) => a.annotation_id)).toEqual(["a1"]);
  });

  it("returns an empty array for a missing document", () => {
    expect(annotationsForPage(null, 1)).toEqual([]);
    expect(needsReviewAnnotations(undefined)).toEqual([]);
  });
});

describe("evidenceRulesFor", () => {
  it("resolves a completion's evidence_ids to full rule objects", () => {
    const document = {
      drawing_language_rules: [
        { rule_id: "note_W8", trigger: "W8", result: "W8X10" },
        { rule_id: "note_W10", trigger: "W10", result: "W10X12" },
      ],
    };
    const a = annotation({
      correction: { operation: OPERATION.COMPLETION, reason_codes: [], evidence_ids: ["note_W8"] },
    });
    const rules = evidenceRulesFor(document, a);
    expect(rules).toHaveLength(1);
    expect(rules[0].rule_id).toBe("note_W8");
  });

  it("returns nothing when there is no evidence", () => {
    expect(evidenceRulesFor({ drawing_language_rules: [] }, annotation())).toEqual([]);
  });
});

describe("describeScore (Section 8: never caption a raw score as calibrated)", () => {
  it("labels a raw model score honestly, uncalibrated", () => {
    const described = describeScore({ value: 6.6994, kind: "raw_model_score", calibrated: false });
    expect(described.label).toBe("Model score");
    expect(described.calibrated).toBe(false);
    expect(described.valueText).toBe("6.699");
  });

  it("only formats as a percentage when genuinely calibrated", () => {
    const described = describeScore({ value: 0.82, kind: "calibrated_probability", calibrated: true });
    expect(described.calibrated).toBe(true);
    expect(described.valueText).toBe("82%");
  });

  it("labels a similarity ratio distinctly from a model score", () => {
    const described = describeScore({ value: 0.9091, kind: "similarity_ratio", calibrated: false });
    expect(described.label).toBe("Similarity");
  });

  it("returns null for no score", () => {
    expect(describeScore(null)).toBeNull();
  });
});

describe("getRepairCandidates / getPendingProposalOperation", () => {
  it("returns the attached candidates, or an empty array", () => {
    const withCandidates = annotation({ repair_candidates: [{ candidate_text: "W18X40", rank: 1 }] });
    expect(getRepairCandidates(withCandidates)).toHaveLength(1);
    expect(getRepairCandidates(annotation())).toEqual([]);
  });

  it("finds the most recent unaccepted REPAIR operation", () => {
    const a = annotation({
      operations: [
        { operation: OPERATION.REPAIR, output_text: "W18X40", accepted: true },
        { operation: OPERATION.REPAIR, output_text: "W18X40", accepted: false },
      ],
    });
    const pending = getPendingProposalOperation(a);
    expect(pending).not.toBeNull();
    expect(pending.accepted).toBe(false);
  });

  it("returns null once every operation is accepted", () => {
    const a = annotation({ operations: [{ operation: OPERATION.REPAIR, output_text: "W18X40", accepted: true }] });
    expect(getPendingProposalOperation(a)).toBeNull();
  });
});

describe("getProcessSteps", () => {
  it("shows a warning step for a non-exact-catalog structural parse and a candidates-found step", () => {
    const a = annotation({
      structural_parse: { is_structural: true, family: "W", grammar: "depth_weight", catalog_exact_match: false },
      repair_candidates: [{ candidate_text: "W18X40", rank: 1 }],
      review_status: REVIEW_STATUS.NEEDS_REVIEW,
      review: { reason: "repair_candidate_available" },
      effective_text: "W18X4O",
    });
    const steps = getProcessSteps(a);
    const labels = steps.map((s) => s.label);
    expect(labels.some((l) => l.includes("not an exact catalog match"))).toBe(true);
    expect(labels.some((l) => l.includes("repair candidate"))).toBe(true);
    expect(labels.some((l) => l === "Human review required")).toBe(true);
  });

  it("ends on a pending-confirmation step when a proposal is unaccepted", () => {
    const a = annotation({
      structural_parse: { is_structural: false, parser_reason: "no_known_grammar_matched" },
      repair_candidates: [{ candidate_text: "W18X40", rank: 1 }],
      operations: [{ operation: OPERATION.REPAIR, output_text: "W18X40", accepted: false }],
      effective_text: "W18X4O",
    });
    const steps = getProcessSteps(a);
    expect(steps[steps.length - 1].key).toBe("pending");
  });

  it("ends on a final step once accepted", () => {
    const a = annotation({
      structural_parse: { is_structural: true, family: "W", grammar: "depth_weight", catalog_exact_match: true },
      review_status: REVIEW_STATUS.HUMAN_ACCEPTED,
      effective_text: "W18X40",
    });
    const steps = getProcessSteps(a);
    expect(steps[steps.length - 1].key).toBe("final");
    expect(steps[steps.length - 1].label).toContain("W18X40");
  });
});
