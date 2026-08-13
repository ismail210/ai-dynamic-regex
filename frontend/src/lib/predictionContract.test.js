import { describe, expect, it } from "vitest";
import {
  getCanonicalPrediction,
  getDisplayConfidence,
  getMatchStatus,
  getPredictionLocation,
  hasCanonicalContract,
  isLegacyPrediction,
  LEGACY_PROVENANCE_MESSAGE,
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
