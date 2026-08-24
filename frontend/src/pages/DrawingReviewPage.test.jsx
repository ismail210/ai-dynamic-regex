import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DrawingReviewPage from "./DrawingReviewPage";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-search">{location.search}</div>;
}

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));

const approveValidationCorrection = vi.fn().mockResolvedValue({});
const saveHumanSelection = vi.fn().mockResolvedValue({});
vi.mock("../api/client", () => ({
  approveValidationCorrection: (...args) => approveValidationCorrection(...args),
  saveHumanSelection: (...args) => saveHumanSelection(...args),
  documentPdfUrl: (id) => `/api/documents/${id}/pdf`,
}));

// PDF rendering itself is exercised separately in PdfDocumentViewer.test.jsx;
// here only the selection -> correction wiring matters.
vi.mock("../components/pdf/PdfDocumentViewer", () => ({
  default: () => <div data-testid="pdf-viewer" />,
}));

vi.mock("../components/pdf/SectionResultsList", () => ({
  default: ({ results, onSelect }) => (
    <div>
      {results.map((result, index) => (
        <button
          key={result.object_id}
          type="button"
          onClick={() =>
            onSelect({
              key: result.object_id,
              result,
              location: { pageNumber: result.page_number, boundingBox: result.bounding_box, hasLocation: true },
            })
          }
        >
          select-{index}
        </button>
      ))}
    </div>
  ),
}));

function damagedLabelResult() {
  return {
    object_id: "token_p12_7",
    raw_text: "W18X3S",
    original_token: "W18X3S",
    normalized_text: "W18X3S",
    corrected_text: "W18X35",
    section: "W18X35",
    page_number: 12,
    bounding_box: [200, 300, 260, 320],
    canonical: {
      source_text: { raw: "W18X3S", page_number: 12, bounding_box: [200, 300, 260, 320], available: true },
      prediction: { final_label: null },
      comparison: { match_status: "corrected_prediction" },
    },
  };
}

function renderPage(overrides = {}, { initialEntries } = {}) {
  mockUseAnalysis.mockReturnValue({
    document: { document_id: "doc_1" },
    data: { results: [damagedLabelResult()] },
    restoreNotice: null,
    setData: vi.fn(),
    ...overrides,
  });
  return render(
    <MemoryRouter initialEntries={initialEntries || ["/review-drawing"]}>
      <DrawingReviewPage />
    </MemoryRouter>,
  );
}

describe("DrawingReviewPage human correction", () => {
  beforeEach(() => {
    approveValidationCorrection.mockClear();
  });

  it("preserves the original OCR text as the review's raw provenance when correcting a damaged label", async () => {
    renderPage();

    fireEvent.click(screen.getByText("select-0"));

    const labelField = screen.getByLabelText("Correct label");
    expect(labelField.value).toBe("W18X35");

    fireEvent.change(labelField, { target: { value: "W18X35" } });
    fireEvent.click(screen.getByRole("button", { name: "Correct" }));

    await waitFor(() => expect(approveValidationCorrection).toHaveBeenCalledTimes(1));
    const call = approveValidationCorrection.mock.calls[0][0];

    expect(call.documentId).toBe("doc_1");
    expect(call.objectId).toBe("token_p12_7");
    expect(call.correctLabel).toBe("W18X35");
    expect(call.userDecision).toBe("correct");
    // The full prediction (carrying raw_text/original_token = "W18X3S") is
    // forwarded as-is -- the correction payload must never overwrite it with
    // the corrected/approved value.
    expect(call.prediction.raw_text).toBe("W18X3S");
    expect(call.prediction.original_token).toBe("W18X3S");
    expect(call.prediction.page_number).toBe(12);
    expect(call.prediction.bounding_box).toEqual([200, 300, 260, 320]);
  });

  it("accept confirms the current label without changing it", async () => {
    renderPage();
    fireEvent.click(screen.getByText("select-0"));
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(approveValidationCorrection).toHaveBeenCalledTimes(1));
    const call = approveValidationCorrection.mock.calls[0][0];
    expect(call.userDecision).toBe("approve");
    expect(call.prediction.raw_text).toBe("W18X3S");
  });
});

function hssResult(objectId, { resolved = false } = {}) {
  // Two independent objects with the exact same raw OCR text -- locating by
  // object_id must never let a text match resolve the wrong one.
  return {
    object_id: objectId,
    raw_text: "HSS8X8",
    original_token: "HSS8X8",
    normalized_text: "HSS8X8",
    section: resolved ? "HSS8X8X1/4" : "HSS8X8X3/16",
    page_number: 7,
    bounding_box: objectId === "obj_a" ? [10, 20, 30, 40] : [50, 60, 70, 80],
    human_selected_section: resolved ? "HSS8X8X1/4" : undefined,
    decision_source: resolved ? "human_review" : undefined,
    needs_review: !resolved,
    candidate_sections: [{ designation: "HSS8X8X1/4" }, { designation: "HSS8X8X3/16" }],
    canonical: {
      source_text: { raw: "HSS8X8", page_number: 7, bounding_box: objectId === "obj_a" ? [10, 20, 30, 40] : [50, 60, 70, 80], available: true },
      prediction: { final_label: resolved ? "HSS8X8X1/4" : null },
      comparison: { match_status: resolved ? "human_resolved" : "missing_dimension_field" },
      needs_review: !resolved,
    },
  };
}

function lowConfidenceResult() {
  // Test F: an ordinary low-confidence correction, unrelated to the HSS
  // completion workflow, must be locatable the same way.
  return {
    object_id: "obj_low_conf",
    raw_text: "W10X24",
    original_token: "W10X24",
    normalized_text: "W10X24",
    section: "W10X49",
    confidence: { overall: 0.12, level: "Low" },
    needs_review: true,
    review_reason: "Source text differs from predicted label.",
    page_number: 4,
    bounding_box: [5, 6, 7, 8],
    canonical: {
      source_text: { raw: "W10X24", page_number: 4, bounding_box: [5, 6, 7, 8], available: true },
      prediction: { final_label: null },
      comparison: { match_status: "corrected_prediction" },
      needs_review: true,
    },
  };
}

describe("DrawingReviewPage deep link from a result elsewhere in the app", () => {
  it("locates the exact object referenced by ?object=, not a text match, when the source text is duplicated", () => {
    // Test C/D: object obj_b must be selected even though obj_a shares the
    // identical raw_text "HSS8X8" -- resolution is by entity id, never by
    // searching the PDF for the label string.
    renderPage(
      { data: { results: [hssResult("obj_a"), hssResult("obj_b", { resolved: true })] } },
      { initialEntries: ["/review-drawing?object=obj_b"] },
    );

    expect(screen.getByText(/Locating HSS8X8X1\/4 on page 7\./)).toBeInTheDocument();
    // obj_b is already human-resolved -- the shared SectionReviewSelector
    // must show the collapsed "already answered" state, not the picker.
    expect(screen.getByText("Selected section")).toBeInTheDocument();
    expect(screen.getByText("Human review")).toBeInTheDocument();
  });

  it("locates a normal low-confidence (non-HSS) result the same way, without offering a section picker it has no candidates for", () => {
    renderPage(
      { data: { results: [lowConfidenceResult()] } },
      { initialEntries: ["/review-drawing?object=obj_low_conf"] },
    );

    // No candidate_sections and no recognized structural family on this
    // fixture -- falls back to the plain generic correction field, exactly
    // as it did before the section-review picker existed for other cases.
    expect(screen.getByLabelText("Correct label").value).toBe("W10X49");
  });

  it("clears the object param after locating so it does not re-fire on later state changes", async () => {
    mockUseAnalysis.mockReturnValue({
      document: { document_id: "doc_1" },
      data: { results: [hssResult("obj_a")] },
      restoreNotice: null,
      setData: vi.fn(),
    });
    render(
      <MemoryRouter initialEntries={["/review-drawing?object=obj_a"]}>
        <LocationProbe />
        <DrawingReviewPage />
      </MemoryRouter>,
    );

    // obj_a is unresolved; the model's own top pick ("HSS8X8X3/16") is
    // pre-selected in the candidate picker rather than an arbitrary option.
    expect(screen.getByDisplayValue("HSS8X8X3/16").checked).toBe(true);
    await waitFor(() =>
      expect(screen.getByTestId("location-search").textContent).toBe(""),
    );
  });

  it("selecting a candidate directly from Drawing Review persists through the shared human_review_selection path", async () => {
    const setData = vi.fn();
    renderPage(
      { data: { results: [hssResult("obj_a")] }, setData },
      { initialEntries: ["/review-drawing?object=obj_a"] },
    );

    fireEvent.click(screen.getByDisplayValue("HSS8X8X1/4"));
    fireEvent.click(screen.getByText("Use this section"));

    await waitFor(() => expect(saveHumanSelection).toHaveBeenCalledTimes(1));
    const call = saveHumanSelection.mock.calls[0][0];
    expect(call.documentId).toBe("doc_1");
    expect(call.objectId).toBe("obj_a");
    expect(call.correctLabel).toBe("HSS8X8X1/4");

    // The panel itself must flip to "Human Reviewed" immediately (Direction
    // B: Drawing Review -> Results updates shared state, not just this
    // page's own local copy).
    await waitFor(() => expect(screen.getByText("Selected section")).toBeInTheDocument());
    expect(setData).toHaveBeenCalled();
  });
});
