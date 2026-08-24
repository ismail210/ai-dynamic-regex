import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TokensTable from "./TokensTable";

vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => ({ data: { results: [] }, setData: vi.fn() }),
}));

vi.mock("../api/client", () => ({
  approveValidationCorrection: vi.fn().mockResolvedValue({}),
}));

function humanReviewedRow() {
  return {
    object_id: "obj_1",
    original_token: "HSS10x10",
    corrected_token: "HSS10X10",
    family: "HSS",
    section: "HSS10X10X1/2",
    human_selected_section: "HSS10X10X1/2",
    decision_source: "human_review",
    needs_review: false,
    review_reason: null,
    confidence: { overall: 0.41, level: "Low" },
    canonical: {
      prediction: { final_label: "HSS10X10X1/2" },
      comparison: { match_status: "human_resolved" },
      needs_review: false,
      review_reason: null,
    },
  };
}

function normalRow() {
  return {
    object_id: "obj_2",
    original_token: "W8x40",
    corrected_token: "W8X40",
    family: "W",
    section: "W8X40",
    confidence: { overall: 0.95, level: "High" },
    review_status: "auto_accepted",
    canonical: {
      prediction: { final_label: "W8X40" },
      comparison: { match_status: "exact_match" },
      needs_review: false,
      review_reason: null,
    },
  };
}

function nonCatalogCorrectionRow() {
  // Real failure: "W10X24" isn't a real AISC shape at all; fuzzy/fusion
  // correction landed on an unrelated size ("W10X49") at 0 confidence. No
  // candidate_sections list exists for this (that's HSS-completion-only) --
  // the fix must still hide the guess.
  return {
    object_id: "obj_3",
    original_token: "W10X24",
    corrected_token: "W10X24",
    family: "W",
    section: "W10X49",
    confidence: { overall: 0, level: "Low" },
    review_status: "pending_review",
    needs_review: true,
    review_reason: "Source text differs from predicted label.",
    canonical: {
      prediction: { final_label: null },
      comparison: { match_status: "corrected_prediction" },
      needs_review: true,
      review_reason: "Source text differs from predicted label.",
    },
  };
}

function rowByToken(token) {
  return screen.getAllByText(token)[0].closest("tr");
}

function hssMissingThicknessRow() {
  return {
    object_id: "obj_hss",
    original_token: "HSS10x10",
    corrected_token: "HSS10X10",
    family: "HSS",
    section: "HSS10X10X1/2",
    completion_status: "missing_thickness",
    candidate_sections: [
      { designation: "HSS10X10X1/4", thickness: "1/4" },
      { designation: "HSS10X10X1/2", thickness: "1/2" },
    ],
    canonical: {
      prediction: { final_label: null },
      comparison: { match_status: "missing_dimension_field" },
      needs_review: true,
      review_reason:
        "Wall thickness is not present in the extracted designation; select the correct catalog section.",
    },
  };
}

describe("TokensTable — missing-thickness HSS shows catalog picker affordance", () => {
  it("shows Select section (N options) instead of the fusion top pick", () => {
    render(<TokensTable results={[hssMissingThicknessRow()]} />);
    const row = rowByToken("HSS10x10");
    expect(within(row).getByText("Select section (2 options)")).toBeInTheDocument();
    expect(within(row).queryByText("HSS10X10X1/2")).not.toBeInTheDocument();
  });
});

describe("TokensTable — a non-catalog-valid correction never displays as a resolved section", () => {
  it("shows Review required (no candidate count) instead of the low-confidence guess", () => {
    render(<TokensTable results={[nonCatalogCorrectionRow()]} />);
    const row = rowByToken("W10X24");
    expect(within(row).getByText("Review required")).toBeInTheDocument();
    expect(within(row).queryByText("W10X49")).not.toBeInTheDocument();
    expect(within(row).queryByText(/options\)/)).not.toBeInTheDocument();
  });
});

describe("TokensTable — human-reviewed rows suppress stale model metrics", () => {
  it("shows the selected section with Confidence/Match as — and Validation as Human Reviewed", () => {
    render(<TokensTable results={[humanReviewedRow()]} />);
    const row = rowByToken("HSS10x10");
    expect(within(row).getByText("HSS10X10X1/2")).toBeInTheDocument();
    // Two dash cells: Confidence and Match.
    expect(within(row).getAllByText("—")).toHaveLength(2);
    expect(within(row).getByText("Human Reviewed")).toBeInTheDocument();
    expect(within(row).queryByText("Low")).not.toBeInTheDocument();
    expect(within(row).queryByText("41%")).not.toBeInTheDocument();
  });

  it("leaves an ordinary model-resolved row's Confidence/Match/Validation unchanged", () => {
    render(<TokensTable results={[normalRow()]} />);
    const row = rowByToken("W8x40");
    expect(within(row).getByText("High")).toBeInTheDocument();
    expect(within(row).queryByText("Human Reviewed")).not.toBeInTheDocument();
    expect(within(row).queryAllByText("—")).toHaveLength(0);
  });
});
