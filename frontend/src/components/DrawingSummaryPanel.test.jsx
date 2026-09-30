import { fireEvent, render, screen, within } from "@testing-library/react";
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

function columnLocation(location, extra = {}) {
  return {
    location,
    level: "LEVEL 1",
    printed_size: "W10X33",
    catalog_designation: "W10X33",
    printed_base_plate: 'PL 14"x14"x3/4"',
    schedule: "COLUMN SCHEDULE",
    page: 28,
    source: "schedule_grid",
    is_definition_not_quantity: true,
    ...extra,
  };
}

describe("DrawingSummaryPanel — column schedule locations", () => {
  const locations = [
    columnLocation("A-1"),
    columnLocation("B-2", { level: "ROOF", printed_size: "L4X4", catalog_designation: null, printed_base_plate: null }),
  ];
  const withLocations = (list) => base({ drawing_intelligence: di({ column_locations: list }) });

  it("renders locations as reference information", () => {
    render(<DrawingSummaryPanel profile={withLocations(locations)} />);
    expect(screen.getByText("Column Schedule Locations")).toBeInTheDocument();
    expect(screen.getByText(/Reference information from column schedules — not a quantity/)).toBeInTheDocument();
    expect(screen.getByText("COLUMN SCHEDULE · PDF p. 28")).toBeInTheDocument();
    const table = within(screen.getByRole("table", { name: "Column schedule locations" }));
    expect(table.getByRole("columnheader", { name: "Level" })).toBeInTheDocument();
    expect(table.getByRole("columnheader", { name: "Base plate" })).toBeInTheDocument();
    const a1 = within(table.getByText("A-1").closest("tr"));
    expect(a1.getByText("LEVEL 1")).toBeInTheDocument();
    expect(a1.getByText("W10X33")).toBeInTheDocument();
    expect(a1.getByText('PL 14"x14"x3/4"')).toBeInTheDocument();
    const b2 = within(table.getByText("B-2").closest("tr"));
    expect(b2.getByText("L4X4")).toBeInTheDocument();
    expect(b2.getByText("printed size, no catalog designation")).toBeInTheDocument();
  });

  it("shows no quantity, count or total", () => {
    render(<DrawingSummaryPanel profile={withLocations(locations)} />);
    const section = screen.getByRole("table", { name: "Column schedule locations" }).closest(".MuiPaper-root");
    expect(within(section).queryByText(/qty|quantity|total|×|\d+ locations?/i)).not.toBeInTheDocument();
    expect(within(section).queryByRole("columnheader", { name: /qty|quantity|count/i })).not.toBeInTheDocument();
  });

  it("is hidden when there are no column schedule locations", () => {
    render(<DrawingSummaryPanel profile={withLocations([])} />);
    expect(screen.queryByText("Column Schedule Locations")).not.toBeInTheDocument();
  });

  it("collapses long lists without showing a count", () => {
    const many = Array.from({ length: 12 }, (_, i) => columnLocation(`A-${i + 1}`));
    render(<DrawingSummaryPanel profile={withLocations(many)} />);
    expect(screen.queryByText("A-12")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Show all rows"));
    expect(screen.getByText("A-12")).toBeInTheDocument();
  });
});
