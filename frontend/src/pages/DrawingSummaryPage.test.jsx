import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import DrawingSummaryPage from "./DrawingSummaryPage";

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));

function renderPage(analysis) {
  mockUseAnalysis.mockReturnValue({
    document: { document_id: "doc-1", source_file: "a.pdf" },
    extraction: null,
    data: null,
    stage: "extracted",
    ...analysis,
  });
  return render(
    <MemoryRouter>
      <DrawingSummaryPage />
    </MemoryRouter>,
  );
}

describe("DrawingSummaryPage", () => {
  it("requires extraction first", () => {
    renderPage({ extraction: null });
    expect(screen.getByText("Extract a drawing first")).toBeInTheDocument();
  });

  it("renders the summary panel and the analyze CTA when a profile is present", () => {
    renderPage({
      extraction: {
        tokens: [],
        legend_profile: {
          status: "SUCCESS",
          executive_summary: "A three-storey steel-framed office building.",
          abbreviation_rules: [],
          drawing_language: [],
          project_rules: [],
          derived_insights: [],
          warnings_and_conflicts: [],
          estimator_attention_items: [],
        },
      },
    });
    expect(screen.getByText("Important Project Notes")).toBeInTheDocument();
    expect(screen.getByText(/three-storey steel-framed office/)).toBeInTheDocument();
    expect(screen.getByText("Analyze Steel Takeoff")).toBeInTheDocument();
  });

  it("still offers the analyze CTA when the drawing has no context pages", () => {
    renderPage({ extraction: { tokens: [], legend_profile: null } });
    expect(screen.getByText(/no project-language summary/i)).toBeInTheDocument();
    expect(screen.getByText("Analyze Steel Takeoff")).toBeInTheDocument();
  });
});
