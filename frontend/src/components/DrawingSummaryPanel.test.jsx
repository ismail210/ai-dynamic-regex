import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DrawingSummaryPanel from "./DrawingSummaryPanel";

// Moved here from pages/ExtractPage.test.jsx when the panel was promoted to its
// own Drawing Summary page. The panel is pure — it takes `profile` directly.
function base(profile) {
  return {
    executive_summary: "",
    abbreviation_rules: [],
    drawing_language: [],
    project_rules: [],
    derived_insights: [],
    warnings_and_conflicts: [],
    estimator_attention_items: [],
    ...profile,
  };
}

function renderPanel(profile) {
  return render(<DrawingSummaryPanel profile={profile} />);
}

describe("DrawingSummaryPanel", () => {
  it("renders nothing when profile is absent", () => {
    renderPanel(undefined);
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("renders nothing when status is DISABLED and there is no content", () => {
    renderPanel(base({ status: "DISABLED" }));
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("renders nothing when status is NO_CONTEXT_PAGES and there is no content", () => {
    renderPanel(base({ status: "NO_CONTEXT_PAGES" }));
    expect(screen.queryByText("Important Project Notes")).not.toBeInTheDocument();
  });

  it("shows an explicit message when the model is unavailable, instead of a blank panel", () => {
    renderPanel(base({ status: "MODEL_UNAVAILABLE" }));
    expect(screen.getByText("Important Project Notes")).toBeInTheDocument();
    expect(screen.getByText(/Project notes analysis unavailable/)).toBeInTheDocument();
  });

  it("shows an explicit message when the model errored", () => {
    renderPanel(base({ status: "MODEL_ERROR" }));
    expect(screen.getByText(/Project notes analysis failed/)).toBeInTheDocument();
  });

  it("renders overview, conventions, typed rules, insights, notes, and uncertainties", () => {
    renderPanel(
      base({
        status: "SUCCESS",
        executive_summary:
          "This project uses abbreviated W/HSS notation and delegates connection design.",
        abbreviation_rules: [
          { lhs: "W8", rhs: "W8X10", source_page: 5, source_quote: '"W8" = W8x10', confidence: 0.95 },
        ],
        drawing_language: ["`c=<dimension>` denotes beam camber."],
        project_rules: [
          {
            type: "ATTRIBUTE_DEFAULT",
            statement: "Square and rectangular HSS conform to ASTM A500 Grade C.",
            source_page: 5,
            application_policy: "ATTRIBUTE_ONLY",
          },
          {
            type: "INHERITANCE_RULE",
            statement: "A CANT beam with no section shown takes the adjacent backspan size, UNO.",
            source_page: 5,
            application_policy: "CORROBORATION_REQUIRED",
          },
        ],
        derived_insights: [
          {
            statement:
              "The project likely uses nominal-depth shorthand systematically for wide-flange beams.",
            evidence_refs: ["RULE_001", "RULE_002"],
            confidence: 0.91,
            impact: "Incomplete W labels elsewhere may be intentional shorthand.",
          },
        ],
        warnings_and_conflicts: [
          { summary: "Conflicting camber note found.", source_page: 6 },
        ],
        estimator_attention_items: [
          "Verify exceptions marked U.N.O. before assuming shorthand applies.",
        ],
      }),
    );
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
    expect(screen.getByText(/nominal-depth shorthand systematically/)).toBeInTheDocument();
    expect(screen.getByText("Not stated directly")).toBeInTheDocument();
    expect(screen.getByText(/Verify exceptions marked U.N.O./)).toBeInTheDocument();
    expect(screen.getByText("Conflicting camber note found.")).toBeInTheDocument();
  });

  it("shows a low-confidence derived insight under Uncertainties exactly once", () => {
    renderPanel(
      base({
        status: "SUCCESS",
        derived_insights: [
          {
            statement: "The project appears to use simplified nominal-depth labels on framing plans.",
            evidence_refs: ["RULE_001"],
            confidence: 0.6,
          },
        ],
      }),
    );
    expect(
      screen.getByText("The project appears to use simplified nominal-depth labels on framing plans."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Project inference")).toHaveLength(1);
    expect(screen.getAllByText("Not stated directly")).toHaveLength(1);
  });

  it("keeps the informational disclaimer whenever the panel renders", () => {
    renderPanel(base({ status: "SUCCESS", executive_summary: "Summary text." }));
    expect(
      screen.getByText(/Informational only -- it does not change any predicted section/),
    ).toBeInTheDocument();
  });

  it("lists steel families derived from extracted tokens", () => {
    render(
      <DrawingSummaryPanel
        profile={base({ status: "SUCCESS", executive_summary: "x" })}
        extraction={{
          tokens: [
            { text: "W12X26", engineering_object_type: "structural_section" },
            { text: "HSS6X6X1/4", engineering_object_type: "structural_section" },
          ],
        }}
      />,
    );
    expect(screen.getByText(/W — wide flange/)).toBeInTheDocument();
    expect(screen.getByText(/HSS — hollow structural/)).toBeInTheDocument();
  });
});
