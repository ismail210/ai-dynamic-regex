import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ExtractPage from "./ExtractPage";

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));

vi.mock("../api/client", () => ({
  extractDocument: vi.fn(),
}));

const baseAnalysis = {
  document: { document_id: "doc-1", source_file: "test.pdf", page_count: 3 },
  setExtraction: vi.fn(),
  setData: vi.fn(),
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ExtractPage />
    </MemoryRouter>,
  );
}

describe("ExtractPage legend profile panel", () => {
  it("renders nothing extra when legend_profile is absent (feature disabled / not yet extracted)", () => {
    mockUseAnalysis.mockReturnValue({
      ...baseAnalysis,
      extraction: { tokens: [], object_counts: {}, layout: {} },
    });
    renderPage();
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("renders nothing when legend_profile is present but empty", () => {
    mockUseAnalysis.mockReturnValue({
      ...baseAnalysis,
      extraction: {
        tokens: [],
        object_counts: {},
        layout: {},
        legend_profile: {
          project_summary: "",
          important_conventions: [],
          abbreviation_rules: [],
          warnings_or_conflicts: [],
        },
      },
    });
    renderPage();
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("renders the summary, abbreviation shorthand, conventions, and warnings when present", () => {
    mockUseAnalysis.mockReturnValue({
      ...baseAnalysis,
      extraction: {
        tokens: [],
        object_counts: {},
        layout: {},
        legend_profile: {
          project_summary: "This project uses abbreviated W-shape notation on framing plans.",
          important_conventions: [
            {
              category: "GENERAL_STRUCTURAL",
              summary: "Cantilevered beams inherit the adjacent backspan size.",
              source_page: 5,
              source_quote: '"CANT" INDICATES CANTILEVERED BEAM.',
              confidence: 0.7,
            },
          ],
          abbreviation_rules: [
            {
              lhs: "W8",
              rhs: "W8X10",
              source_page: 5,
              source_quote: '"W8" = W8x10',
              confidence: 0.95,
            },
          ],
          warnings_or_conflicts: [
            { summary: "Conflicting note found.", source_page: 6, source_quote: "..." },
          ],
        },
      },
    });
    renderPage();
    expect(screen.getByText("Important Project Notes")).toBeInTheDocument();
    expect(
      screen.getByText("This project uses abbreviated W-shape notation on framing plans."),
    ).toBeInTheDocument();
    expect(screen.getByText("W8 → W8X10")).toBeInTheDocument();
    expect(
      screen.getByText("Cantilevered beams inherit the adjacent backspan size."),
    ).toBeInTheDocument();
    expect(screen.getByText("Conflicting note found.")).toBeInTheDocument();
  });

  it("does not render a legend panel affordance that could be mistaken for an editable prediction", () => {
    mockUseAnalysis.mockReturnValue({
      ...baseAnalysis,
      extraction: {
        tokens: [],
        object_counts: {},
        layout: {},
        legend_profile: {
          project_summary: "Summary text.",
          important_conventions: [],
          abbreviation_rules: [],
          warnings_or_conflicts: [],
        },
      },
    });
    renderPage();
    expect(
      screen.getByText(/Informational only -- does not change any predicted section\./),
    ).toBeInTheDocument();
  });
});
