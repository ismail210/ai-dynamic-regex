import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PredictionExplainability from "./PredictionExplainability";
import { LEGACY_PROVENANCE_MESSAGE } from "../lib/predictionContract";

const canonicalResult = {
  canonical: {
    object_id: "token_1",
    source_text: {
      raw: "W18X35",
      normalized: "W18X35",
      page_number: 1,
      bounding_box: [1, 2, 3, 4],
      extraction_method: "pdf_text",
      available: true,
    },
    prediction: {
      final_label: "W18X35",
      family: "W",
      ranking_score: 0.9,
      final_confidence: null,
      confidence_is_calibrated: false,
    },
    comparison: {
      exact_match: true,
      normalized_match: true,
      prediction_required: false,
      match_status: "exact_match",
    },
    decision: {
      source: "text",
      used_text: true,
      used_geometry: false,
      used_graph: false,
      used_engineering_rules: false,
      used_catalog: true,
    },
    candidates: [],
    evidence: {},
    needs_review: false,
    review_reason: null,
  },
  confidence: { overall: 0.9, level: "High" },
  section: "W18X35",
  family: "W",
};

// A pre-canonical record: none of canonical/comparison/source_text present.
const legacyResult = {
  section: "W18X35",
  family: "W",
  confidence: { overall: 0.8, level: "High" },
};

// A genuinely new canonical prediction that could not be resolved — distinct
// from a legacy record because it still carries the canonical structure.
const newUnresolvedResult = {
  canonical: {
    object_id: "token_2",
    source_text: {
      raw: null,
      normalized: null,
      page_number: null,
      bounding_box: null,
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
    needs_review: true,
    review_reason: "No valid candidate could be resolved.",
  },
  confidence: { overall: 0, level: "Low" },
};

describe("PredictionExplainability legacy handling", () => {
  it("renders the normal match-status badge for a canonical prediction", () => {
    render(<PredictionExplainability result={canonicalResult} />);
    expect(screen.getByText("Exact PDF Match")).toBeInTheDocument();
    expect(screen.queryByText(LEGACY_PROVENANCE_MESSAGE)).not.toBeInTheDocument();
  });

  it("renders the legacy provenance message for a pre-canonical record", () => {
    render(<PredictionExplainability result={legacyResult} />);
    expect(screen.getByText(LEGACY_PROVENANCE_MESSAGE)).toBeInTheDocument();
  });

  it("does not render the red unresolved badge for a legacy-only record", () => {
    render(<PredictionExplainability result={legacyResult} />);
    expect(screen.queryByText("Unresolved — Review Required")).not.toBeInTheDocument();
    expect(screen.getByText("Legacy — Re-analysis Required")).toBeInTheDocument();
  });

  it("still renders the normal unresolved review status for a genuine new unresolved prediction", () => {
    render(<PredictionExplainability result={newUnresolvedResult} />);
    expect(screen.getByText("Unresolved — Review Required")).toBeInTheDocument();
    expect(screen.queryByText(LEGACY_PROVENANCE_MESSAGE)).not.toBeInTheDocument();
  });
});
