import { useEffect } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnalysisProvider, useAnalysis } from "../context/AnalysisContext";
import TokensTable from "../components/TokensTable";
import DrawingReviewPage from "./DrawingReviewPage";

/**
 * Results and Drawing Review are not two separate review systems -- they
 * are two views over one AnalysisContext `data.results` array, kept in
 * sync by the same `saveHumanSelection` mutation (services.human_selections
 * via routers.engineering.post_correction). This suite mounts both real
 * components under one real AnalysisProvider (only the PDF canvas, the
 * network client, and the heavy explainability chart are mocked) to prove
 * that mutation is genuinely shared, not something either page infers from
 * its own local/UI-only state.
 */

const saveHumanSelection = vi.fn();
vi.mock("../api/client", () => ({
  saveHumanSelection: (...args) => saveHumanSelection(...args),
  approveValidationCorrection: vi.fn().mockResolvedValue({}),
  documentPdfUrl: (id) => `/api/documents/${id}/pdf`,
}));

vi.mock("../components/pdf/PdfDocumentViewer", () => ({
  // Exposes the resolved locate target's key as text so tests can assert
  // exactly which object the PDF pane is pointed at, without needing the
  // real canvas/pdf.js rendering pipeline.
  default: ({ selection }) => (
    <div data-testid="pdf-viewer">{selection?.key || ""}</div>
  ),
}));

vi.mock("../components/PredictionExplainability", () => ({
  default: () => <div data-testid="explainability" />,
}));

function hssResult(overrides = {}) {
  return {
    object_id: "obj_hss",
    document_id: "doc_1",
    raw_text: "HSS10x10",
    original_token: "HSS10x10",
    normalized_text: "HSS10X10",
    corrected_token: "HSS10X10",
    token: "HSS10x10",
    section: "HSS10X10X3/16",
    family: "HSS",
    page_number: 7,
    bounding_box: [10, 20, 30, 40],
    needs_review: true,
    candidate_sections: [
      { designation: "HSS10X10X1/4" },
      { designation: "HSS10X10X3/16" },
      { designation: "HSS10X10X3/8" },
    ],
    canonical: {
      source_text: { raw: "HSS10x10", page_number: 7, bounding_box: [10, 20, 30, 40], available: true },
      prediction: { final_label: null },
      comparison: { match_status: "missing_dimension_field" },
      needs_review: true,
    },
    ...overrides,
  };
}

function Seed({ results }) {
  const { setDocument, setData } = useAnalysis();
  useEffect(() => {
    setDocument({ document_id: "doc_1" });
    setData({ results });
    // Seed once on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

function ResultsView() {
  const { data } = useAnalysis();
  return <TokensTable results={data?.results || []} />;
}

function Harness({ initialResults }) {
  return (
    <AnalysisProvider>
      <Seed results={initialResults} />
      <div data-testid="results-page">
        <ResultsView />
      </div>
      <div data-testid="drawing-review-page">
        <DrawingReviewPage />
      </div>
    </AnalysisProvider>
  );
}

function renderHarness(initialResult = hssResult(), { initialEntries } = {}) {
  const initialResults = Array.isArray(initialResult) ? initialResult : [initialResult];
  return render(
    <MemoryRouter initialEntries={initialEntries || ["/results"]}>
      <Harness initialResults={initialResults} />
    </MemoryRouter>,
  );
}

describe("Results <-> Drawing Review share one human-review decision", () => {
  beforeEach(() => {
    saveHumanSelection.mockReset();
    saveHumanSelection.mockResolvedValue({});
  });

  it("Direction A: a candidate chosen in Results is immediately selected and marked Human Reviewed on Drawing Review", async () => {
    renderHarness();
    const resultsPage = screen.getByTestId("results-page");
    const drawingReview = screen.getByTestId("drawing-review-page");

    fireEvent.click(within(resultsPage).getByText("HSS10x10"));
    fireEvent.click(await screen.findByDisplayValue("HSS10X10X1/4"));
    fireEvent.click(screen.getByText("Use this section"));
    await waitFor(() => expect(saveHumanSelection).toHaveBeenCalledTimes(1));

    // Results row itself must already show the resolved section + status.
    expect(within(resultsPage).getByText("HSS10X10X1/4")).toBeInTheDocument();
    expect(within(resultsPage).getByText("Human Reviewed")).toBeInTheDocument();

    // Drawing Review's own list (already mounted the whole time, per
    // AnalysisContext being process-wide, not remounted on navigation) must
    // reflect the exact same resolved section for the exact same object.
    fireEvent.click(await within(drawingReview).findByText(/HSS10X10X1\/4/));
    expect(within(drawingReview).getByText("Selected section")).toBeInTheDocument();
    expect(within(drawingReview).getByText("Human review")).toBeInTheDocument();
    expect(within(drawingReview).queryByText("Possible catalog sections")).not.toBeInTheDocument();
  });

  it("Direction B: a candidate chosen on Drawing Review immediately updates the Results row, without re-running Analyze", async () => {
    renderHarness();
    const resultsPage = screen.getByTestId("results-page");
    const drawingReview = screen.getByTestId("drawing-review-page");

    fireEvent.click(within(drawingReview).getByText(/HSS10x10/));
    fireEvent.click(await within(drawingReview).findByDisplayValue("HSS10X10X3/8"));
    fireEvent.click(within(drawingReview).getByText("Use this section"));
    await waitFor(() => expect(saveHumanSelection).toHaveBeenCalledTimes(1));

    expect(within(drawingReview).getByText("Selected section")).toBeInTheDocument();

    // Results, already mounted, must show the same answer without a
    // refetch/Analyze -- it only ever reads from the shared context array.
    expect(within(resultsPage).getByText("HSS10X10X3/8")).toBeInTheDocument();
    expect(within(resultsPage).getByText("Human Reviewed")).toBeInTheDocument();
  });

  it("changing a prior decision updates both pages, not just a fresh selection", async () => {
    renderHarness(
      hssResult({
        section: "HSS10X10X1/4",
        human_selected_section: "HSS10X10X1/4",
        decision_source: "human_review",
        needs_review: false,
        canonical: {
          source_text: { raw: "HSS10x10", page_number: 7, bounding_box: [10, 20, 30, 40], available: true },
          prediction: { final_label: "HSS10X10X1/4" },
          comparison: { match_status: "human_resolved" },
          needs_review: false,
        },
      }),
    );
    const resultsPage = screen.getByTestId("results-page");
    const drawingReview = screen.getByTestId("drawing-review-page");

    expect(within(resultsPage).getByText("HSS10X10X1/4")).toBeInTheDocument();

    fireEvent.click(within(resultsPage).getByText("HSS10x10"));
    fireEvent.click(await screen.findByText("Change selection"));
    fireEvent.click(screen.getByDisplayValue("HSS10X10X3/16"));
    fireEvent.click(screen.getByText("Save selection"));
    await waitFor(() => expect(saveHumanSelection).toHaveBeenCalledTimes(1));
    expect(saveHumanSelection.mock.calls[0][0].correctLabel).toBe("HSS10X10X3/16");

    expect(within(resultsPage).getByText("HSS10X10X3/16")).toBeInTheDocument();
    expect(within(resultsPage).queryByText("HSS10X10X1/4")).not.toBeInTheDocument();
    fireEvent.click(await within(drawingReview).findByText(/HSS10X10X3\/16/));
    expect(within(drawingReview).getByText("Selected section")).toBeInTheDocument();
  });

  it("manual Other correction on Drawing Review syncs to Results and reopens with Other pre-filled", async () => {
    renderHarness();
    const resultsPage = screen.getByTestId("results-page");
    const drawingReview = screen.getByTestId("drawing-review-page");

    fireEvent.click(within(drawingReview).getByText(/HSS10x10/));
    fireEvent.click(await within(drawingReview).findByText("Other / Enter corrected section"));
    fireEvent.change(within(drawingReview).getByLabelText("Correct section"), {
      target: { value: "HSS10X10X5/8" },
    });
    fireEvent.click(within(drawingReview).getByText("Use this section"));
    await waitFor(() => expect(saveHumanSelection).toHaveBeenCalledTimes(1));
    expect(saveHumanSelection.mock.calls[0][0].correctLabel).toBe("HSS10X10X5/8");

    expect(within(resultsPage).getByText("HSS10X10X5/8")).toBeInTheDocument();

    // Reopening the picker on either page must show Other pre-selected with
    // the saved value, not silently fall back to the candidate list.
    // Drawing Review's own panel is also still showing "Change selection"
    // for the same object, so scope to the modal (a portal, outside both
    // page containers) to disambiguate.
    fireEvent.click(within(resultsPage).getByText("HSS10x10"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText("Change selection"));
    expect(within(dialog).getByDisplayValue("HSS10X10X5/8")).toBeInTheDocument();
  });
});

function duplicateHssResult(objectId, boundingBox) {
  // Same raw OCR text on three independent objects -- exactly the "same
  // designation appears multiple times on a page" scenario. Only object_id
  // and bounding_box distinguish them.
  return hssResult({
    object_id: objectId,
    section: "HSS8X8X1/2",
    human_selected_section: "HSS8X8X1/2",
    decision_source: "human_review",
    needs_review: false,
    candidate_sections: [
      { designation: "HSS8X8X1/4" },
      { designation: "HSS8X8X1/2" },
      { designation: "HSS8X8X3/4" },
    ],
    raw_text: "HSS8X8",
    original_token: "HSS8X8",
    normalized_text: "HSS8X8",
    bounding_box: boundingBox,
    canonical: {
      source_text: { raw: "HSS8X8", page_number: 7, bounding_box: boundingBox, available: true },
      prediction: { final_label: "HSS8X8X1/2" },
      comparison: { match_status: "human_resolved" },
      needs_review: false,
    },
  });
}

describe("Drawing Review: PDF target and the Steel Sections list stay tied to one object identity", () => {
  beforeEach(() => {
    saveHumanSelection.mockReset();
    saveHumanSelection.mockResolvedValue({});
  });

  it("Test A: Review on Drawing (?object=) selects the matching list row and points the PDF at the same object, not the first with matching text", async () => {
    const results = [
      duplicateHssResult("obj_1", [10, 20, 30, 40]),
      duplicateHssResult("obj_2", [50, 60, 70, 80]),
      duplicateHssResult("obj_3", [90, 100, 110, 120]),
    ];
    renderHarness(results, { initialEntries: ["/review-drawing?object=obj_2"] });

    // The PDF pane (mocked to expose its target key) must point at obj_2,
    // not obj_1 (which shares the exact same raw_text/section).
    expect(await screen.findByTestId("pdf-viewer")).toHaveTextContent("obj_2");

    // The matching list row (and only that one) must carry MUI's active
    // "selected" styling -- proving list selection is keyed by object_id,
    // not by re-deriving from the section text.
    const drawingReview = screen.getByTestId("drawing-review-page");
    const rows = within(drawingReview)
      .getAllByRole("button")
      .filter((el) => el.textContent.includes("HSS8X8X1/2"));
    expect(rows).toHaveLength(3);
    expect(rows[0].className).not.toMatch(/Mui-selected/);
    expect(rows[1].className).toMatch(/Mui-selected/);
    expect(rows[2].className).not.toMatch(/Mui-selected/);
  });

  it("Test B: clicking a different list row moves the PDF target and the review panel to that row", async () => {
    const results = [
      duplicateHssResult("obj_1", [10, 20, 30, 40]),
      duplicateHssResult("obj_2", [50, 60, 70, 80]),
    ];
    renderHarness(results);
    const drawingReview = screen.getByTestId("drawing-review-page");

    const rows = within(drawingReview)
      .getAllByRole("button")
      .filter((el) => el.textContent.includes("HSS8X8X1/2"));
    fireEvent.click(rows[0]);
    expect(await screen.findByTestId("pdf-viewer")).toHaveTextContent("obj_1");

    fireEvent.click(rows[1]);
    expect(await screen.findByTestId("pdf-viewer")).toHaveTextContent("obj_2");
  });

  it("Test E (duplicate labels): choosing a candidate for one of several identical-text objects only resolves that object", async () => {
    const results = [
      hssResult({ object_id: "obj_1", bounding_box: [10, 20, 30, 40] }),
      hssResult({ object_id: "obj_2", bounding_box: [50, 60, 70, 80] }),
    ];
    renderHarness(results, { initialEntries: ["/review-drawing?object=obj_2"] });
    const drawingReview = screen.getByTestId("drawing-review-page");

    fireEvent.click(await within(drawingReview).findByDisplayValue("HSS10X10X1/4"));
    fireEvent.click(within(drawingReview).getByText("Use this section"));
    await waitFor(() => expect(saveHumanSelection).toHaveBeenCalledTimes(1));
    expect(saveHumanSelection.mock.calls[0][0].objectId).toBe("obj_2");

    const resultsPage = screen.getByTestId("results-page");
    const rows = within(resultsPage).getAllByText("HSS10x10").map((el) => el.closest("tr"));
    expect(rows).toHaveLength(2);
    // obj_1's row must still show the unresolved placeholder; only obj_2
    // resolved.
    expect(within(rows[0]).getByText("Select section (3 options)")).toBeInTheDocument();
    expect(within(rows[1]).getByText("HSS10X10X1/4")).toBeInTheDocument();
  });

  it("Test F: a human-reviewed row shows the resolved section while the raw drawing text stays visible and unchanged", async () => {
    renderHarness(
      duplicateHssResult("obj_1", [10, 20, 30, 40]),
      { initialEntries: ["/review-drawing?object=obj_1"] },
    );
    const drawingReview = screen.getByTestId("drawing-review-page");

    expect(await within(drawingReview).findByText("Detected text: HSS8X8")).toBeInTheDocument();
    expect(within(drawingReview).getByText("HSS8X8X1/2")).toBeInTheDocument();
    expect(within(drawingReview).getByText("Human review")).toBeInTheDocument();
    // Still locating the ORIGINAL drawing text's position, not the resolved
    // label -- provenance is never rewritten.
    expect(screen.getByText(/Locating HSS8X8X1\/2 on page 7\./)).toBeInTheDocument();
  });
});
