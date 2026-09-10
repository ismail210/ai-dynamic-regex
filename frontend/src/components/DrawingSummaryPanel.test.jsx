import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DrawingSummaryPanel from "./DrawingSummaryPanel";

// The panel is pure -- it takes the extraction-stage `legend_profile` object
// directly and renders its `drawing_intelligence` sub-object.

function narrative(overrides = {}) {
  return {
    project_overview: "This 28-page structural set has 4 framing/plan page(s).",
    structural_content: "Page make-up: 20 notes/legend, 2 floor framing.",
    steel_system: "Wide-flange (W) framing dominates the explicit designations.",
    drawing_language: "No project-specific shorthand substitutions were found.",
    typical_conditions: "520 repeated-condition marker(s) (TYP, U.N.O.).",
    schedules: "No structural schedules identified.",
    scope_revision: "No explicit issue/revision/phase markings detected.",
    important_notes: [],
    uncertainties: ["No unresolved conflicts or ambiguous page roles detected."],
    ...overrides,
  };
}

function di(overrides = {}) {
  return {
    version: "drawing_intelligence_v1",
    method: "deterministic",
    page_count: 28,
    abbreviation_rules: [],
    page_groups: [],
    steel_system: { families: [], representative_sections: [] },
    representative_sections: [],
    typical_conditions: [],
    schedule_insights: [],
    scope_signals: [],
    structural_notes: [],
    uncertainties: [],
    conflicts: [],
    sources: [],
    ...overrides,
    narrative: narrative(overrides.narrative),
  };
}

function base(profile = {}) {
  return {
    status: "SUCCESS",
    executive_summary: "",
    abbreviation_rules: [],
    project_rules: [],
    derived_insights: [],
    drawing_intelligence: di(),
    ...profile,
  };
}

const TITLE = "What Estima3D read from this drawing set";

describe("DrawingSummaryPanel", () => {
  it("renders nothing when profile is absent", () => {
    render(<DrawingSummaryPanel profile={undefined} />);
    expect(screen.queryByText(TITLE)).not.toBeInTheDocument();
  });

  it("renders nothing when disabled with no content", () => {
    render(
      <DrawingSummaryPanel
        profile={{ status: "DISABLED", drawing_intelligence: {}, project_rules: [], abbreviation_rules: [] }}
      />,
    );
    expect(screen.queryByText(TITLE)).not.toBeInTheDocument();
  });

  it("shows an explicit message when the model errored and rules exist", () => {
    render(
      <DrawingSummaryPanel
        profile={{
          status: "MODEL_ERROR",
          drawing_intelligence: {},
          project_rules: [],
          abbreviation_rules: [{ lhs: "W8", rhs: "W8X10", source_page: 5 }],
        }}
      />,
    );
    expect(screen.getByText(/Project notes analysis failed/)).toBeInTheDocument();
  });

  it("renders the deterministic narrative sections", () => {
    render(<DrawingSummaryPanel profile={base()} />);
    expect(screen.getByText(TITLE)).toBeInTheDocument();
    expect(screen.getByText("Project overview")).toBeInTheDocument();
    expect(screen.getByText(/28-page structural set/)).toBeInTheDocument();
    expect(screen.getByText("Steel system")).toBeInTheDocument();
    expect(screen.getByText("Typical / repeated conditions")).toBeInTheDocument();
    expect(
      screen.getByText(/it does not change any predicted section or takeoff/),
    ).toBeInTheDocument();
  });

  it("only names steel families that are in the profile", () => {
    render(
      <DrawingSummaryPanel
        profile={base({
          drawing_intelligence: di({
            steel_system: {
              families: [
                { family: "W", label: "wide-flange (W)", explicit_occurrences: 737, distinct_designations: 46, representative: ["W16X26"] },
                { family: "HSS", label: "hollow structural (HSS)", explicit_occurrences: 60, distinct_designations: 14, representative: ["HSS6X6X3/8"] },
              ],
              representative_sections: ["W16X26"],
            },
          }),
        })}
      />,
    );
    expect(screen.getByText(/wide-flange \(W\) · 737×/)).toBeInTheDocument();
    expect(screen.getByText(/hollow structural \(HSS\) · 60×/)).toBeInTheDocument();
  });

  it("surfaces project shorthand rules with source page tooltips", () => {
    render(
      <DrawingSummaryPanel
        profile={base({
          abbreviation_rules: [
            { lhs: "W8", rhs: "W8X10", source_page: 5, source_quote: '"W8" = W8x10' },
          ],
          drawing_intelligence: di({
            abbreviation_rules: [{ lhs: "W8", rhs: "W8X10", source_page: 5 }],
            narrative: { drawing_language: "1 explicit project shorthand rule(s): W8 = W8X10" },
          }),
        })}
      />,
    );
    expect(screen.getByText("W8 = W8X10")).toBeInTheDocument();
    expect(screen.getByText(/1 explicit project shorthand rule/)).toBeInTheDocument();
  });

  it("shows typical-condition detail bullets when present", () => {
    render(
      <DrawingSummaryPanel
        profile={base({
          drawing_intelligence: di({
            typical_conditions: [
              {
                type: "typical_condition",
                value: "'TYP' appears 120 time(s) across 6 page(s) (on framing/detail pages)",
                detail: { present: true, keyword: "TYP" },
                source_text: "W16X26 TYP",
                source_pages: [12, 13],
              },
            ],
          }),
        })}
      />,
    );
    expect(screen.getByText(/'TYP' appears 120 time/)).toBeInTheDocument();
  });

  it("shows scope stamps as warning chips", () => {
    render(
      <DrawingSummaryPanel
        profile={base({
          drawing_intelligence: di({
            scope_signals: [
              {
                type: "scope_signal",
                value: "Early / partial steel release stamp on page(s) 2",
                detail: { present: true, label: "Early / partial steel release" },
                source_pages: [2],
              },
            ],
            narrative: {
              scope_revision:
                "Early / partial steel release; Bid set. Multiple phases present.",
            },
          }),
        })}
      />,
    );
    expect(screen.getByText(/Early \/ partial steel release \(p\. 2\)/)).toBeInTheDocument();
    expect(screen.getByText(/Multiple phases present/)).toBeInTheDocument();
  });

  it("renders uncertainties as warnings", () => {
    render(
      <DrawingSummaryPanel
        profile={base({
          drawing_intelligence: di({
            uncertainties: [
              {
                type: "uncertainty",
                value: "Structural table on page 16 has unresolved row/cell semantics",
                detail: { kind: "schedule_semantics" },
              },
            ],
          }),
        })}
      />,
    );
    expect(screen.getByText(/unresolved row\/cell semantics/)).toBeInTheDocument();
  });

  it("does not invent TYP language when the profile reports none", () => {
    render(
      <DrawingSummaryPanel
        profile={base({
          drawing_intelligence: di({
            narrative: {
              typical_conditions: "No TYP / U.N.O. / repeated-condition language detected.",
            },
          }),
        })}
      />,
    );
    expect(
      screen.getByText("No TYP / U.N.O. / repeated-condition language detected."),
    ).toBeInTheDocument();
  });

  it("badges an LLM-polished summary", () => {
    render(<DrawingSummaryPanel profile={base({ drawing_intelligence: di({ method: "llm_enhanced" }) })} />);
    expect(screen.getByText("summary polished by model")).toBeInTheDocument();
  });
});
