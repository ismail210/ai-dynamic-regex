import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import AnalysisResultsPage from "./AnalysisResultsPage";

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));

// ResultsBody's chart/table children pull recharts / TanStack Table; the
// exclusion note itself lives in ResultsBody and stays under test.
vi.mock("../components/Charts", () => ({ default: () => null }));
vi.mock("../components/StatsCards", () => ({ default: () => null }));
vi.mock("../components/TokensTable", () => ({ default: () => null }));
vi.mock("../components/DownloadButtons", () => ({ default: () => null }));
vi.mock("../components/AnalyzeLauncher", () => ({
  default: () => <div data-testid="analyze-launcher">Analyze Drawing</div>,
}));

function renderPage(analysis) {
  mockUseAnalysis.mockReturnValue({
    document: { document_id: "doc-1", source_file: "test.pdf" },
    extraction: null,
    data: null,
    restoreNotice: null,
    stage: "empty",
    ...analysis,
  });
  return render(
    <MemoryRouter>
      <AnalysisResultsPage />
    </MemoryRouter>,
  );
}

describe("AnalysisResultsPage", () => {
  it("requires extraction before anything else", () => {
    renderPage({ extraction: null });
    expect(screen.getByText("Extraction is required")).toBeInTheDocument();
    expect(screen.getByText("Go to Upload & Extract")).toBeInTheDocument();
  });

  it("shows a re-upload message when the original file is gone", () => {
    renderPage({
      extraction: null,
      restoreNotice: {
        kind: "missing-source",
        message: "The original uploaded file is no longer available.",
      },
    });
    expect(screen.getByText("Original file no longer available")).toBeInTheDocument();
    expect(screen.getByText("Upload the PDF again")).toBeInTheDocument();
  });

  it("shows the analyze launcher once extracted but not yet analyzed", () => {
    renderPage({ extraction: { tokens: [] }, data: null, stage: "extracted" });
    expect(screen.getByTestId("analyze-launcher")).toBeInTheDocument();
    expect(screen.queryByText("Extraction is required")).not.toBeInTheDocument();
  });

  it("notes how many legend / general-note definitions were excluded", () => {
    renderPage({
      extraction: { tokens: [] },
      stage: "analyzed",
      data: {
        results: [{ object_id: "t1", token: "W12X19" }],
        context_definitions: [{ object_id: "c1" }, { object_id: "c2" }, { object_id: "c3" }],
        summary: {},
      },
    });
    expect(
      screen.getByText(/3 steel designations on legend \/ general-note pages are excluded/i),
    ).toBeInTheDocument();
  });

  it("shows no exclusion note when there are no context definitions", () => {
    renderPage({
      extraction: { tokens: [] },
      stage: "analyzed",
      data: { results: [{ object_id: "t1" }], context_definitions: [], summary: {} },
    });
    expect(screen.queryByText(/excluded from the takeoff/i)).not.toBeInTheDocument();
  });
});
