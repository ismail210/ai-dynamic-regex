import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ResultsPage from "./ResultsPage";

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));

// The exclusion note lives directly in ResultsPage; the chart/table children
// pull in recharts (needs ResizeObserver) and are not under test here.
vi.mock("../components/Charts", () => ({ default: () => null }));
vi.mock("../components/StatsCards", () => ({ default: () => null }));
vi.mock("../components/TokensTable", () => ({ default: () => null }));
vi.mock("../components/DownloadButtons", () => ({ default: () => null }));

function renderResultsPage() {
  return render(
    <MemoryRouter>
      <ResultsPage />
    </MemoryRouter>,
  );
}

describe("ResultsPage empty states", () => {
  it("shows the generic empty state when nothing has ever been analyzed", () => {
    mockUseAnalysis.mockReturnValue({ data: null, restoreNotice: null });
    renderResultsPage();
    expect(screen.getByText("No analysis results")).toBeInTheDocument();
  });

  it("shows a clear re-upload message instead of a blank state when the original file is gone", () => {
    mockUseAnalysis.mockReturnValue({
      data: null,
      restoreNotice: {
        kind: "missing-source",
        message:
          "The original uploaded file is no longer available. Upload the PDF again " +
          "and run the analysis to restore provenance.",
      },
    });
    renderResultsPage();
    expect(screen.getByText("Original file no longer available")).toBeInTheDocument();
    expect(
      screen.getByText(/original uploaded file is no longer available/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Upload the PDF again")).toBeInTheDocument();
    expect(screen.queryByText("No analysis results")).not.toBeInTheDocument();
  });

  it("notes how many legend / general-note definitions were excluded from the takeoff", () => {
    mockUseAnalysis.mockReturnValue({
      data: {
        results: [{ object_id: "t1", token: "W12X19" }],
        context_definitions: [{ object_id: "c1" }, { object_id: "c2" }, { object_id: "c3" }],
        summary: {},
      },
      restoreNotice: null,
    });
    renderResultsPage();
    expect(
      screen.getByText(/3 steel designations on legend \/ general-note pages are excluded/i),
    ).toBeInTheDocument();
  });

  it("shows no exclusion note when there are no context definitions", () => {
    mockUseAnalysis.mockReturnValue({
      data: { results: [{ object_id: "t1", token: "W12X19" }], context_definitions: [], summary: {} },
      restoreNotice: null,
    });
    renderResultsPage();
    expect(screen.queryByText(/excluded from the takeoff/i)).not.toBeInTheDocument();
  });

  it("shows a distinct re-analysis message for a generic restore failure", () => {
    mockUseAnalysis.mockReturnValue({
      data: null,
      restoreNotice: {
        kind: "restore-failed",
        message: "The previous analysis could not be restored. Start a new analysis to continue.",
      },
    });
    renderResultsPage();
    expect(screen.getByText("Previous analysis could not be restored")).toBeInTheDocument();
    expect(screen.getByText("Start new analysis")).toBeInTheDocument();
    expect(screen.queryByText("No analysis results")).not.toBeInTheDocument();
  });
});
