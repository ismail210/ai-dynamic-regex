import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PredictionDetailModal from "./PredictionDetailModal";

function renderModal(props) {
  return render(
    <MemoryRouter>
      <PredictionDetailModal {...props} />
    </MemoryRouter>,
  );
}

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));

const saveHumanSelection = vi.fn().mockResolvedValue({});
vi.mock("../api/client", () => ({
  saveHumanSelection: (...args) => saveHumanSelection(...args),
}));

// Explainability's own rendering is exercised elsewhere; only the
// selection -> persistence wiring matters here.
vi.mock("./PredictionExplainability", () => ({
  default: () => <div data-testid="explainability" />,
}));

function missingThicknessResult(overrides = {}) {
  return {
    object_id: "obj_1",
    document_id: "doc_1",
    raw_text: "HSS10x10",
    original_token: "HSS10x10",
    normalized_text: "HSS10X10",
    corrected_token: "HSS10X10",
    section: "HSS10X10X1/2",
    completion_status: "missing_thickness",
    known_dimensions: ["10", "10"],
    candidate_sections: [
      { designation: "HSS10X10X3/16", thickness: "3/16" },
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
    ...overrides,
  };
}

describe("PredictionDetailModal — missing-thickness HSS candidate selection", () => {
  let setData;

  beforeEach(() => {
    saveHumanSelection.mockClear();
    saveHumanSelection.mockResolvedValue({});
    setData = vi.fn();
    mockUseAnalysis.mockReturnValue({ data: { results: [] }, setData });
  });

  it("never shows a recommendation badge for candidate options", () => {
    renderModal({ result: missingThicknessResult(), onClose: () => {} });
    expect(screen.queryByText(/suggested by model/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/recommended/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/best match/i)).not.toBeInTheDocument();
    expect(screen.getByText("HSS10X10X1/2")).toBeInTheDocument();
  });

  it("shows Review required and the candidate picker before a human decision", () => {
    renderModal({ result: missingThicknessResult(), onClose: () => {} });
    expect(screen.getByText("Review required")).toBeInTheDocument();
    expect(screen.getByText("Possible catalog sections")).toBeInTheDocument();
  });

  it("saves the reviewer's choice via the safe human_review_selection decision and patches shared state without touching source text", async () => {
    const { rerender } = renderModal({ result: missingThicknessResult(), onClose: () => {} });

    fireEvent.click(screen.getByDisplayValue("HSS10X10X1/2"));
    fireEvent.click(screen.getByText("Use this section"));

    await waitFor(() => expect(saveHumanSelection).toHaveBeenCalledTimes(1));
    // saveHumanSelection (api/client.js) is the one function that always
    // sends the safe "human_review_selection" decision -- calling it at all
    // (rather than approveValidationCorrection with some other decision) is
    // what proves this path, not a userDecision string on the call site.
    const call = saveHumanSelection.mock.calls[0][0];
    expect(call.correctLabel).toBe("HSS10X10X1/2");
    expect(call.documentId).toBe("doc_1");
    expect(call.objectId).toBe("obj_1");

    // The optimistic local-state updater (what TokensTable's live-result
    // lookup re-renders the modal with, via AnalysisContext) must turn
    // "Select section" into the chosen designation without a refetch, and
    // must never touch original/normalized text.
    expect(setData).toHaveBeenCalledTimes(1);
    const updater = setData.mock.calls[0][0];
    const before = { results: [missingThicknessResult()] };
    const after = updater(before).results[0];
    expect(after.section).toBe("HSS10X10X1/2");
    expect(after.human_selected_section).toBe("HSS10X10X1/2");
    expect(after.decision_source).toBe("human_review");
    expect(after.needs_review).toBe(false);
    expect(after.canonical.prediction.final_label).toBe("HSS10X10X1/2");
    expect(after.canonical.comparison.match_status).toBe("human_resolved");
    expect(after.original_token).toBe("HSS10x10");
    expect(after.normalized_text).toBe("HSS10X10");

    // Simulate TokensTable re-deriving `selected` from the patched
    // `results` array and passing the fresh object back in as `result` --
    // the still-open modal must reflect the save immediately.
    rerender(
      <MemoryRouter>
        <PredictionDetailModal result={after} onClose={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Selected section")).toBeInTheDocument();
    expect(screen.queryByText("Review required")).not.toBeInTheDocument();
  });

  it("shows the already-resolved section (not the picker) once human_selected_section is set, and allows changing it", () => {
    const resolved = missingThicknessResult({
      section: "HSS10X10X1/2",
      human_selected_section: "HSS10X10X1/2",
      needs_review: false,
      review_reason: null,
      canonical: {
        prediction: { final_label: "HSS10X10X1/2" },
        comparison: { match_status: "human_resolved" },
        needs_review: false,
        review_reason: null,
      },
    });
    renderModal({ result: resolved, onClose: () => {} });

    expect(screen.queryByText("Review required")).not.toBeInTheDocument();
    expect(screen.getByText("Selected section")).toBeInTheDocument();
    expect(screen.queryByText(/suggested by model/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Change selection"));
    expect(screen.getByText("Possible catalog sections")).toBeInTheDocument();
  });

  it("suppresses stale model Confidence and shows Human Reviewed for Validation once resolved", () => {
    const resolved = missingThicknessResult({
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
    });
    renderModal({ result: resolved, onClose: () => {} });

    expect(screen.getByText("Human Reviewed")).toBeInTheDocument();
    expect(screen.queryByText("41%")).not.toBeInTheDocument();
    expect(screen.queryByText("Low")).not.toBeInTheDocument();
  });
});
