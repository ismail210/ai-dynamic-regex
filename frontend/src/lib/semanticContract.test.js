import { describe, expect, it } from "vitest";
import {
  annotationsForPage,
  evidenceRulesFor,
  getOperation,
  getOverlayStyle,
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
        { association_reason: ["GHX_PDF_DISAGREEMENT"] },
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
