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

  it("renders the drawing-language profile: overview, sections, drawing language, typed rules, insights, warnings", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "SUCCESS",
        executive_summary: "This project uses abbreviated W/HSS notation and delegates connection design.",
        abbreviation_rules: [
          { lhs: "W8", rhs: "W8X10", source_page: 5, source_quote: '"W8" = W8x10', confidence: 0.95 },
        ],
        drawing_language: ["`c=<dimension>` denotes beam camber."],
        project_rules: [
          {
            type: "ATTRIBUTE_DEFAULT",
            statement: "Square and rectangular HSS conform to ASTM A500 Grade C.",
            source_page: 5,
            source_quote: "SQUARE AND RECTANGULAR HSS SHALL CONFORM TO ASTM A500 GRADE C.",
            application_policy: "ATTRIBUTE_ONLY",
          },
          {
            type: "INHERITANCE_RULE",
            statement: "A CANT beam with no section shown takes the adjacent backspan size, UNO.",
            source_page: 5,
            source_quote: '"CANT" INDICATES CANTILEVERED BEAM.',
            application_policy: "CORROBORATION_REQUIRED",
          },
        ],
        derived_insights: [
          {
            statement: "The project likely uses nominal-depth shorthand systematically for wide-flange beams.",
            evidence_refs: ["RULE_001", "RULE_002"],
            reasoning_summary: "Multiple explicit abbreviation mappings follow the same pattern.",
            confidence: 0.91,
            impact: "Incomplete W labels elsewhere may be intentional shorthand.",
          },
        ],
        warnings_and_conflicts: [
          { summary: "Conflicting camber note found.", source_page: 6, source_quote: "..." },
        ],
        estimator_attention_items: ["Verify exceptions marked U.N.O. before assuming shorthand applies."],
      }),
    );
    renderPage();
    expect(screen.getByText("Important Project Notes")).toBeInTheDocument();
    expect(screen.getByText(/abbreviated W\/HSS notation/)).toBeInTheDocument();
    expect(screen.getByText("W8 → W8X10")).toBeInTheDocument();
    expect(screen.getByText(/denotes beam camber/)).toBeInTheDocument();
    expect(
      screen.getByText("Square and rectangular HSS conform to ASTM A500 Grade C."),
    ).toBeInTheDocument();
    expect(screen.getByText("attribute only")).toBeInTheDocument();
    expect(screen.getByText("needs geometry check")).toBeInTheDocument();
    expect(screen.getByText("Project inference")).toBeInTheDocument();
    expect(
      screen.getByText(/nominal-depth shorthand systematically/),
    ).toBeInTheDocument();
    expect(screen.getByText("Not stated directly")).toBeInTheDocument();
    expect(
      screen.getByText(/Verify exceptions marked U.N.O./),
    ).toBeInTheDocument();
    expect(screen.getByText("Conflicting camber note found.")).toBeInTheDocument();
  });

  it("marks a LABEL_SUBSTITUTION rule as auto-applying and an insight as not stated directly", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "SUCCESS",
        executive_summary: "",
        abbreviation_rules: [],
        drawing_language: [],
        project_rules: [
          {
            type: "SCOPE_RULE",
            statement: "Supplemental steel for precast attachment is fabricator scope.",
            source_page: 4,
            source_quote: "ANGLES, PLATES AND SUPPLEMENTAL FRAMING FOR PRECAST ARE BY THE STEEL FABRICATOR.",
            application_policy: "INFORMATION_ONLY",
          },
        ],
        derived_insights: [
          {
            statement: "The project appears to use simplified nominal-depth labels on framing plans.",
            evidence_refs: ["RULE_001"],
            reasoning_summary: "Derived from the explicit substitution rules.",
            confidence: 0.8,
          },
        ],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    expect(
      screen.getByText("Supplemental steel for precast attachment is fabricator scope."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("The project appears to use simplified nominal-depth labels on framing plans."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Project inference")).toHaveLength(1);
    expect(screen.getAllByText("Not stated directly")).toHaveLength(1);
  });

  it("informational disclaimer is always present when the panel renders", () => {
    mockUseAnalysis.mockReturnValue(
      withProfile({
        status: "SUCCESS",
        executive_summary: "Summary text.",
        abbreviation_rules: [],
        drawing_language: [],
        project_rules: [],
        derived_insights: [],
        warnings_and_conflicts: [],
        estimator_attention_items: [],
      }),
    );
    renderPage();
    expect(
      screen.getByText(/Informational only -- it does not change any predicted section/),
    ).toBeInTheDocument();
  });
});
