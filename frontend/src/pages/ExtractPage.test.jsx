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

function withProfile(profile) {
  return {
    ...baseAnalysis,
    extraction: { tokens: [], object_counts: {}, layout: {}, legend_profile: profile },
  };
}

describe("ExtractPage legend profile panel", () => {
  it("renders nothing extra when legend_profile is absent", () => {
    mockUseAnalysis.mockReturnValue({
      ...baseAnalysis,
      extraction: { tokens: [], object_counts: {}, layout: {} },
    });
    renderPage();
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("renders nothing when status is DISABLED", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "DISABLED",
        executive_summary: "",
        source_facts: [],
        derived_insights: [],
        abbreviation_rules: [],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("renders nothing when status is NO_CONTEXT_PAGES", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "NO_CONTEXT_PAGES",
        executive_summary: "",
        source_facts: [],
        derived_insights: [],
        abbreviation_rules: [],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("shows an explicit message when the model is unavailable, instead of a blank panel", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "MODEL_UNAVAILABLE",
        executive_summary: "",
        source_facts: [],
        derived_insights: [],
        abbreviation_rules: [],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    expect(screen.getByText("Important Project Notes")).toBeInTheDocument();
    expect(
      screen.getByText(/Project notes analysis unavailable/),
    ).toBeInTheDocument();
  });

  it("shows an explicit message when the model errored", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "MODEL_ERROR",
        executive_summary: "",
        source_facts: [],
        derived_insights: [],
        abbreviation_rules: [],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    expect(screen.getByText(/Project notes analysis failed/)).toBeInTheDocument();
  });

  it("renders the full deep analysis: summary, facts, derived insights, shorthand, attention items, and warnings", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "SUCCESS",
        executive_summary: "This project uses abbreviated W-shape notation and delegates connection design.",
        source_facts: [
          {
            category: "MATERIAL",
            statement: "Structural steel wide-flange shapes conform to ASTM A992.",
            source_page: 2,
            source_quote: "STRUCTURAL STEEL SHALL CONFORM TO ASTM A992.",
            confidence: 0.95,
          },
        ],
        derived_insights: [
          {
            inference: "The project likely uses nominal-depth shorthand systematically for wide-flange beams.",
            evidence_refs: ["W8 → W8X10", "W10 → W10X12"],
            reasoning_summary: "Multiple explicit abbreviation mappings follow the same notation pattern.",
            confidence: 0.91,
            impact: "Incomplete W labels elsewhere may be intentional shorthand, not OCR failures.",
            human_review_recommended: true,
          },
        ],
        abbreviation_rules: [
          { lhs: "W8", rhs: "W8X10", source_page: 5, source_quote: '"W8" = W8x10', confidence: 0.95 },
        ],
        warnings_and_conflicts: [
          { summary: "Conflicting camber note found.", source_page: 6, source_quote: "..." },
        ],
        estimator_attention_items: ["Verify exceptions marked U.N.O. before assuming shorthand applies."],
      }),
    );
    renderPage();
    expect(screen.getByText("Important Project Notes")).toBeInTheDocument();
    expect(screen.getByText(/abbreviated W-shape notation/)).toBeInTheDocument();
    expect(screen.getByText("W8 → W8X10")).toBeInTheDocument();
    expect(
      screen.getByText("Structural steel wide-flange shapes conform to ASTM A992."),
    ).toBeInTheDocument();
    expect(screen.getByText("Project inference")).toBeInTheDocument();
    expect(
      screen.getByText(/nominal-depth shorthand systematically/),
    ).toBeInTheDocument();
    expect(screen.getByText("Review recommended")).toBeInTheDocument();
    expect(
      screen.getByText(/Verify exceptions marked U.N.O./),
    ).toBeInTheDocument();
    expect(screen.getByText("Conflicting camber note found.")).toBeInTheDocument();
  });

  it("visually distinguishes a derived insight from an explicit source fact", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "SUCCESS",
        executive_summary: "",
        source_facts: [
          {
            category: "SECTION_NOTATION",
            statement: "W8 beam notation represents W8X10 unless otherwise noted.",
            source_page: 5,
            source_quote: "BEAMS NOTED W8 SHALL BE W8X10 U.N.O.",
            confidence: 0.9,
          },
        ],
        derived_insights: [
          {
            inference: "The project appears to use simplified nominal-depth labels on framing plans.",
            evidence_refs: ["W8 beam notation represents W8X10 unless otherwise noted."],
            reasoning_summary: "Derived from the explicit W8 substitution note.",
            confidence: 0.8,
            impact: "Some W-shape annotations may intentionally omit the weight designation.",
            human_review_recommended: false,
          },
        ],
        abbreviation_rules: [],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    // The explicit fact and the derived inference must both be visible,
    // and only the inference carries the "Project inference" marker.
    expect(
      screen.getByText("W8 beam notation represents W8X10 unless otherwise noted."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("The project appears to use simplified nominal-depth labels on framing plans."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Project inference")).toHaveLength(1);
  });

  it("informational disclaimer is always present when the panel renders", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "SUCCESS",
        executive_summary: "Summary text.",
        source_facts: [],
        derived_insights: [],
        abbreviation_rules: [],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    expect(
      screen.getByText(/Informational only -- does not change any predicted section\./),
    ).toBeInTheDocument();
  });
});
