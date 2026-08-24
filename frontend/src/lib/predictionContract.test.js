import { describe, expect, it } from "vitest";
import {
  getCanonicalPrediction,
  getDisplayConfidence,
  getDisplaySection,
  getMatchStatus,
  getPredictionLocation,
  getResultKey,
  hasCanonicalContract,
  isHumanReviewed,
  isLegacyPrediction,
  LEGACY_PROVENANCE_MESSAGE,
  reviewOnDrawingPath,
} from "./predictionContract";

describe("predictionContract canonical helpers", () => {
  it("reads a full canonical response without guessing", () => {
    const result = {
      canonical: {
        object_id: "token_1",
        document_id: "doc_1",
        source_text: {
          raw: "W18 X 35",
          normalized: "W18X35",
          page_number: 3,
          bounding_box: [1, 2, 3, 4],
          block_number: 1,
          line_number: 2,
          word_number: null,
          extraction_method: "pdf_text",
          available: true,
        },
        prediction: {
          final_label: "W18X35",
          family: "W",
          ranking_score: 0.91,
          final_confidence: null,
          confidence_is_calibrated: false,
        },
        comparison: {
          exact_match: false,
          normalized_match: true,
          prediction_required: false,
          match_status: "normalized_match",
        },
        decision: {
          source: "text",
          used_text: true,
          used_geometry: false,
          used_graph: false,
          used_engineering_rules: true,
          used_catalog: true,
        },
        candidates: [{ label: "W18X35", combined_score: 0.91 }],
        evidence: {},
        catalog_version: "aisc-shapes-database-v160-2.xlsx#Database v16.0",
        needs_review: false,
        review_reason: null,
      },
    };

    expect(hasCanonicalContract(result)).toBe(true);
    const canonical = getCanonicalPrediction(result);
    expect(canonical.sourceText.raw).toBe("W18 X 35");
    expect(canonical.prediction.final_label).toBe("W18X35");
    expect(getMatchStatus(result)).toBe("normalized_match");
  });

  it("falls back gracefully for a pre-canonical (legacy) response", () => {
    const legacy = {
      section: "W18X35",
      family: "W",
      confidence: { overall: 0.8, level: "High" },
    };
    expect(hasCanonicalContract(legacy)).toBe(false);
    const canonical = getCanonicalPrediction(legacy);
    expect(canonical.prediction.final_label).toBe("W18X35");
    expect(canonical.sourceText.available).toBe(false);
    expect(getMatchStatus(legacy)).toBe("unresolved");
  });

  it("never presents an uncalibrated score as a probability", () => {
    const uncalibrated = {
      canonical: {
        prediction: {
          final_label: "W18X35",
          ranking_score: 0.91,
          final_confidence: null,
          confidence_is_calibrated: false,
        },
      },
    };
    const display = getDisplayConfidence(uncalibrated);
    expect(display.isCalibrated).toBe(false);
    expect(display.value).toBe(0.91);
  });

  it("surfaces a calibrated probability distinctly when available", () => {
    const calibrated = {
      canonical: {
        prediction: {
          final_label: "W18X35",
          ranking_score: 0.91,
          final_confidence: 0.77,
          confidence_is_calibrated: true,
        },
      },
    };
    const display = getDisplayConfidence(calibrated);
    expect(display.isCalibrated).toBe(true);
    expect(display.value).toBe(0.77);
  });
});

// A missing-thickness HSS read (services.hss_completion /
// canonical_contract.MatchStatus.MISSING_DIMENSION_FIELD) must show as
// "needs a human choice", never as one candidate presented as the answer.
describe("getDisplaySection — missing-thickness HSS never shows a guess as final", () => {
  it("reports review-required with no value when candidates remain and final_label is null", () => {
    const result = {
      canonical: {
        prediction: { final_label: null },
        comparison: { match_status: "missing_dimension_field" },
        needs_review: true,
        review_reason:
          "Wall thickness is not present in the extracted designation; select the correct catalog section.",
      },
      section: "HSS10X10X1/2",
      completion_status: "missing_thickness",
      known_dimensions: ["10", "10"],
      candidate_sections: [
        { designation: "HSS10X10X3/16", thickness: "3/16" },
        { designation: "HSS10X10X1/2", thickness: "1/2" },
      ],
    };
    const display = getDisplaySection(result);
    expect(display.reviewRequired).toBe(true);
    expect(display.value).toBeNull();
    expect(display.reason).toMatch(/wall thickness/i);
    expect(display.hasCandidates).toBe(true);
  });

  it("shows the resolved value for an ordinary complete prediction", () => {
    const result = {
      canonical: {
        prediction: { final_label: "W16X26" },
        comparison: { match_status: "exact_match" },
        needs_review: false,
        review_reason: null,
      },
      section: "W16X26",
      completion_status: "complete",
    };
    const display = getDisplaySection(result);
    expect(display.reviewRequired).toBe(false);
    expect(display.value).toBe("W16X26");
  });

  it("is review-required (with no candidate list) when needs_review is true and final_label is null even without a candidate_sections array", () => {
    // Real failure: OCR read a complete-LOOKING but non-catalog-valid label
    // (e.g. "W10X24", which isn't a real AISC shape), and fuzzy/fusion
    // correction landed on an unrelated size ("W10X49") with 0 confidence.
    // The canonical contract already nulls final_label for this
    // (match_status "corrected_prediction" is in _REVIEW_REASONS) -- the
    // display must never fall back to showing that low-confidence guess as
    // if it were a resolved section just because there's no HSS-style
    // candidate_sections list to pick from instead.
    const result = {
      canonical: {
        prediction: { final_label: null },
        comparison: { match_status: "corrected_prediction" },
        needs_review: true,
        review_reason: "Source text differs from predicted label.",
      },
      section: "W10X49",
    };
    const display = getDisplaySection(result);
    expect(display.reviewRequired).toBe(true);
    expect(display.value).toBeNull();
    expect(display.hasCandidates).toBe(false);
  });
});

describe("isHumanReviewed — explicit provenance only, never inferred from needs_review", () => {
  it("is true when decision_source is human_review", () => {
    expect(isHumanReviewed({ decision_source: "human_review" })).toBe(true);
  });

  it("is true when only the canonical match_status says human_resolved", () => {
    expect(
      isHumanReviewed({
        canonical: { comparison: { match_status: "human_resolved" } },
      }),
    ).toBe(true);
  });

  it("is false for an ordinary auto-accepted row with no review needed", () => {
    // needs_review === false must NOT be mistaken for human review -- most
    // model-resolved rows also have no review requirement.
    expect(
      isHumanReviewed({
        needs_review: false,
        canonical: { comparison: { match_status: "exact_match" } },
      }),
    ).toBe(false);
  });

  it("is false for a row still pending review", () => {
    expect(
      isHumanReviewed({
        needs_review: true,
        canonical: { comparison: { match_status: "missing_dimension_field" } },
      }),
    ).toBe(false);
  });
});

describe("isLegacyPrediction", () => {
  it("is false for a full canonical response", () => {
    const result = {
      canonical: {
        source_text: { raw: "W18X35", available: true },
        comparison: { match_status: "exact_match" },
      },
    };
    expect(isLegacyPrediction(result)).toBe(false);
  });

  it("is true for a pre-canonical record with none of canonical/comparison/source_text", () => {
    const legacy = {
      section: "W18X35",
      family: "W",
      confidence: { overall: 0.8, level: "High" },
    };
    expect(isLegacyPrediction(legacy)).toBe(true);
  });

  it("is false for a genuinely new prediction that merely resolves to unresolved", () => {
    // A fresh canonical prediction with no source text still carries the
    // comparison/source_text structure (marked unavailable) — it must not
    // be mistaken for a legacy record just because match_status is unresolved.
    const newUnresolved = {
      canonical: {
        source_text: { raw: null, available: false },
        prediction: { final_label: null },
        comparison: { match_status: "unresolved", prediction_required: true },
      },
    };
    expect(isLegacyPrediction(newUnresolved)).toBe(false);
  });

  it("exposes the exact required legacy-provenance message", () => {
    expect(LEGACY_PROVENANCE_MESSAGE).toBe(
      "Provenance unavailable — this document was analyzed with an older pipeline " +
        "version. Re-analysis is required.",
    );
  });
});

// Locator rule: the drawing must be located by stable source provenance
// (page/bbox of the ACTUAL extracted characters), never by re-searching for
// the predicted/corrected label string. getPredictionLocation is the single
// function both SectionResultsList and DrawingReviewPage rely on for this,
// so it is the right place to pin the contract down directly.
describe("getPredictionLocation — locates source text, never the prediction", () => {
  function canonicalResult({ raw, pageNumber, boundingBox, matchStatus, finalLabel }) {
    return {
      canonical: {
        source_text: {
          raw,
          normalized: raw,
          page_number: pageNumber,
          bounding_box: boundingBox,
          available: boundingBox != null,
        },
        prediction: { final_label: finalLabel },
        comparison: { match_status: matchStatus },
      },
    };
  }

  it("exact text match: locates using the source bbox", () => {
    const result = canonicalResult({
      raw: "W18X35",
      pageNumber: 7,
      boundingBox: [10, 20, 60, 40],
      matchStatus: "exact_match",
      finalLabel: "W18X35",
    });
    const location = getPredictionLocation(result);
    expect(location).toEqual({ pageNumber: 7, boundingBox: [10, 20, 60, 40], hasLocation: true });
  });

  it("formatting normalization: still locates the ORIGINAL source span, not a re-search for the normalized string", () => {
    // Raw text "W18 X 35" would not be found by searching the page for the
    // normalized "W18X35" -- the bbox must come from where "W18 X 35"
    // itself was extracted, independent of what it normalizes to.
    const result = canonicalResult({
      raw: "W18 X 35",
      pageNumber: 7,
      boundingBox: [10, 20, 75, 40],
      matchStatus: "normalized_match",
      finalLabel: "W18X35",
    });
    const location = getPredictionLocation(result);
    expect(location).toEqual({ pageNumber: 7, boundingBox: [10, 20, 75, 40], hasLocation: true });
  });

  it("OCR correction: locates the damaged RAW text's own position, not a position derived from the corrected suggestion", () => {
    // "W18X3S" is what is actually on the page; "W18X35" is only a
    // suggestion. The highlight must stay on W18X3S's own bbox regardless
    // of what gets suggested/predicted.
    const result = canonicalResult({
      raw: "W18X3S",
      pageNumber: 12,
      boundingBox: [200, 300, 260, 320],
      matchStatus: "corrected_prediction",
      finalLabel: null,
    });
    const location = getPredictionLocation(result);
    expect(location).toEqual({
      pageNumber: 12,
      boundingBox: [200, 300, 260, 320],
      hasLocation: true,
    });
  });

  it("missing/incomplete label with no resolvable source position reports hasLocation=false rather than guessing", () => {
    const result = canonicalResult({
      raw: "W44X3**",
      pageNumber: null,
      boundingBox: null,
      matchStatus: "incomplete_label",
      finalLabel: null,
    });
    const location = getPredictionLocation(result);
    expect(location.hasLocation).toBe(false);
  });

  it("multiple identical labels on the same page: each result's own bbox is used, not a shared/first match", () => {
    const first = canonicalResult({
      raw: "W16X26",
      pageNumber: 7,
      boundingBox: [100, 100, 140, 120],
      matchStatus: "exact_match",
      finalLabel: "W16X26",
    });
    const second = canonicalResult({
      raw: "W16X26",
      pageNumber: 7,
      boundingBox: [400, 500, 440, 520],
      matchStatus: "exact_match",
      finalLabel: "W16X26",
    });
    expect(getPredictionLocation(first).boundingBox).toEqual([100, 100, 140, 120]);
    expect(getPredictionLocation(second).boundingBox).toEqual([400, 500, 440, 520]);
    expect(getPredictionLocation(first).boundingBox).not.toEqual(
      getPredictionLocation(second).boundingBox,
    );
  });
});

describe("getResultKey / reviewOnDrawingPath", () => {
  it("keys by object_id first, the same id services.human_selections and the drawing review list use", () => {
    expect(getResultKey({ object_id: "obj_1", component_id: "comp_1" })).toBe("obj_1");
  });

  it("falls back to component_id only when object_id is absent", () => {
    expect(getResultKey({ component_id: "comp_1" })).toBe("comp_1");
  });

  it("never derives the key from label text, so duplicate designations stay distinguishable", () => {
    const a = { object_id: "obj_a", section: "HSS8X8X1/4" };
    const b = { object_id: "obj_b", section: "HSS8X8X1/4" };
    expect(getResultKey(a)).not.toBe(getResultKey(b));
  });

  it("builds a Drawing Review deep link keyed by the same object id", () => {
    expect(reviewOnDrawingPath({ object_id: "obj_1" })).toBe(
      "/review-drawing?object=obj_1",
    );
  });

  it("falls back to a bare Drawing Review link when no id is available", () => {
    expect(reviewOnDrawingPath({})).toBe("/review-drawing");
  });
});
