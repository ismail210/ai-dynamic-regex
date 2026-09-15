import { describe, expect, it } from "vitest";
import {
  caseMatchesFilter,
  compareExpectedVsActual,
  matchCaseToAnnotation,
  normalizeDamageText,
  resolveDamageManifest,
} from "./semanticDamageManifest";

describe("semanticDamageManifest", () => {
  it("resolves manifests by uploaded filename stem", () => {
    expect(resolveDamageManifest("burrville_SEMANTIC_DAMAGE_TEST.pdf")?.project).toMatch(/Burrville/i);
    expect(resolveDamageManifest("st_SEMANTIC_DAMAGE_TEST.pdf")?.project).toBe("ST");
    expect(resolveDamageManifest("structure_SEMANTIC_DAMAGE_TEST.pdf")?.project).toMatch(/Structure/i);
    expect(resolveDamageManifest("ordinary_customer.pdf")).toBeNull();
  });

  it("normalizes spaced / multiply glyphs for matching", () => {
    expect(normalizeDamageText("W 8 × 10")).toBe("W8X10");
  });

  it("matches cases by page + bbox proximity", () => {
    const testCase = {
      source_page: 10,
      test_text: "W1BX35",
      original_text: "W18X35",
      modified_bbox: [100, 100, 140, 120],
    };
    const annotations = [
      {
        annotation_id: "far",
        page: 10,
        semantic_bbox: [900, 900, 940, 920],
        correction: { original: "W1BX35" },
        primary_label: "W1BX35",
      },
      {
        annotation_id: "near",
        page: 10,
        semantic_bbox: [102, 101, 138, 119],
        correction: { original: "W1BX35" },
        primary_label: "W1BX35",
      },
    ];
    expect(matchCaseToAnnotation(testCase, annotations)?.annotation_id).toBe("near");
  });

  it("filters repair / normalization / incomplete / clean buckets", () => {
    const pairs = [
      { testCase: { category: "char_corruption" }, annotation: null },
      { testCase: { category: "spacing" }, annotation: null },
      { testCase: { category: "incomplete" }, annotation: null },
      { testCase: { category: "clean_control" }, annotation: { review_status: "auto_accepted" } },
      { testCase: { category: "deletion" }, annotation: { review_status: "needs_review" } },
    ];
    expect(pairs.filter((p) => caseMatchesFilter(p, "repair"))).toHaveLength(2);
    expect(pairs.filter((p) => caseMatchesFilter(p, "normalization"))).toHaveLength(1);
    expect(pairs.filter((p) => caseMatchesFilter(p, "incomplete"))).toHaveLength(1);
    expect(pairs.filter((p) => caseMatchesFilter(p, "clean"))).toHaveLength(1);
    expect(pairs.filter((p) => caseMatchesFilter(p, "needs_review"))).toHaveLength(1);
    expect(pairs.filter((p) => caseMatchesFilter(p, "reviewed"))).toHaveLength(1);
  });

  it("keeps expected metadata separate from actual model fields", () => {
    const testCase = {
      category: "char_corruption",
      expected_normalized: "W8X10",
      intended_semantic_result: "W8X10",
      expected_operation: "repair",
      expected_status: "needs_review",
      expected_abstention: false,
      test_text: "W8XI0",
    };
    const annotation = {
      correction: { original: "W8XI0", canonical: "W8X10", operation: "repair" },
      primary_label: "W8X10",
      review_status: "needs_review",
      structural_parse: { family: "W" },
    };
    const cmp = compareExpectedVsActual(testCase, annotation);
    expect(cmp.status).toBe("PASS");
    expect(cmp.expected.normalized).toBe("W8X10");
    expect(cmp.actual.normalized).toBe("W8X10");
    expect(cmp.expected).not.toBe(cmp.actual);
  });

  it("marks incomplete cases PASS only when abstention signals are present", () => {
    const testCase = {
      category: "incomplete",
      expected_normalized: "L4X4",
      expected_abstention: true,
      expected_operation: "abstention",
      expected_status: "incomplete",
      test_text: "L4X4",
    };
    const invented = compareExpectedVsActual(testCase, {
      correction: { original: "L4X4", canonical: "L4X4X3/8", operation: "completion" },
      review_status: "auto_accepted",
      takeoff_eligible: true,
    });
    expect(invented.status).toBe("REVIEW");

    const abstained = compareExpectedVsActual(testCase, {
      correction: { original: "L4X4", canonical: "L4X4", operation: "keep" },
      review_status: "needs_review",
      takeoff_eligible: false,
      structural_parse: { grammar: "incomplete", family: "L" },
    });
    expect(abstained.status).toBe("PASS");
  });
});
