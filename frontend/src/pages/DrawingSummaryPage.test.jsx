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
          abbreviation_rules: [],
          project_rules: [],
          derived_insights: [],
          drawing_intelligence: {
            version: "drawing_intelligence_v1",
            method: "deterministic",
            page_count: 3,
            steel_system: { families: [], representative_sections: [] },
            page_groups: [{ detail: { category: "floor_framing", pages: [2] } }],
            typical_conditions: [],
            schedule_insights: [],
            scope_signals: [],
            structural_notes: [],
            uncertainties: [],
            narrative: {
              project_overview: "A three-storey steel-framed office building.",
              structural_content: "Page make-up: 1 floor framing.",
              steel_system: "Wide-flange framing dominates.",
              drawing_language: "No project-specific shorthand substitutions were found.",
              typical_conditions: "No TYP / U.N.O. / repeated-condition language detected.",
              schedules: "No structural schedules identified.",
              scope_revision: "No explicit issue/revision/phase markings detected.",
              important_notes: [],
              uncertainties: ["No unresolved conflicts or ambiguous page roles detected."],
            },
          },
        },
      },
    });
    expect(screen.getByText("What Estima3D read from this drawing set")).toBeInTheDocument();
    expect(screen.getByText(/three-storey steel-framed office/)).toBeInTheDocument();
    expect(screen.getByText("Analyze Steel Takeoff")).toBeInTheDocument();
  });

  it("still offers the analyze CTA when the drawing has no context pages", () => {
    renderPage({ extraction: { tokens: [], legend_profile: null } });
    expect(screen.getByText(/no project-language summary/i)).toBeInTheDocument();
    expect(screen.getByText("Analyze Steel Takeoff")).toBeInTheDocument();
  });
});
