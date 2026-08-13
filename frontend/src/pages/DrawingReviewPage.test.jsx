import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DrawingReviewPage from "./DrawingReviewPage";

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));

const approveValidationCorrection = vi.fn().mockResolvedValue({});
vi.mock("../api/client", () => ({
  approveValidationCorrection: (...args) => approveValidationCorrection(...args),
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

function renderPage(overrides = {}) {
  mockUseAnalysis.mockReturnValue({
    document: { document_id: "doc_1" },
    data: { results: [damagedLabelResult()] },
    restoreNotice: null,
    ...overrides,
  });
  return render(
    <MemoryRouter>
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
