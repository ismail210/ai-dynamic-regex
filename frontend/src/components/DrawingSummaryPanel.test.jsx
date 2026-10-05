import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DrawingSummaryPanel from "./DrawingSummaryPanel";

// The real viewer (react-pdf) is covered by PdfDocumentViewer.test.jsx; here
// only what the summary asks it to show matters.
vi.mock("./pdf/PdfDocumentViewer", () => ({
  default: ({ fileUrl, selection }) => (
    <div
      data-testid="pdf-viewer"
      data-file={fileUrl}
      data-page={String(selection?.pageNumber)}
      data-bbox={JSON.stringify(selection?.boundingBox ?? null)}
    />
  ),
}));

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

function definition(id, mark, designation, extra = {}) {
  return {
    id,
    mark,
    designation,
    designation_source: designation ? "AISC v16 catalog" : null,
    printed: "",
    role: "lintel",
    configuration: [],
    parts: [],
    status: null,
    component: "lintel",
    component_label: "Lintels",
    schedule: "Lintel schedule",
    relation: "mark defines section",
    sheet: "S002",
    page: 2,
    bbox: [2021.4, 1770.7, 2030.5, 1781.2],
    source_text: `${mark} | ${designation}`,
    ...extra,
  };
}

const bearing = (printed) => ({ role: "bearing plate", printed, designation: null });

function evidenceProfile(overrides = {}) {
  return base({
    drawing_intelligence: di({
      definitions: [
        definition("D1", "L1", "W8X21", {
          configuration: ["bottom plate"], parts: [bearing('6"x6"x1/2"')],
          source_text: 'L1 | W8x21 WITH BOTTOM PLATE | 6"x6"x1/2"',
        }),
        definition("D2", "L1A", "W8X21", { configuration: ["hung plate"], parts: [bearing('6"x6"x1/2"')] }),
        definition("D3", "C1", "HSS6X6X1/2", {
          component: "column", component_label: "Columns", schedule: "Column schedule", role: "column",
        }),
        definition("D4", "BP1", null, {
          component: "bearing_plate", component_label: "Bearing plates",
          schedule: "Bearing plate schedule", relation: "mark defines plate",
          role: "bearing plate", printed: '4"x6"x3/4"',
        }),
        definition("D5", "CL1", "L5X5X3/8", {
          component: "icf_lintel", component_label: "ICF lintels", schedule: "ICF lintel schedule",
          role: "ICF lintel", configuration: ["loose angle"],
        }),
      ],
      interpretation_rules: [
        {
          id: "R1", relation: "default unless otherwise noted",
          text: "BEARING PLATE SIZE APPLIES TO EACH END UNLESS NOTED OTHERWISE.",
          scope: "Lintel schedule", sheet: "S002", page: 2,
        },
      ],
      unresolved: [
        {
          id: "U1", kind: "undefined_bracket_tag",
          text: "Numbers in brackets after beam sizes appear 427 times; do not read them as member quantities.",
          pages: [7, 8, 9, 10], sheet: "S102A",
        },
      ],
      summary_llm: {
        overview: "x", overview_source: "llm",
        key_facts: [{ id: "D2", why: "An L1A callout means a hung plate, not a bottom plate." }],
        cautions: [],
      },
      uncertainties: [{ value: "1 page(s) could not be confidently categorised", source_pages: [19] }],
      ...overrides,
    }),
  });
}

// The table row (desktop) that holds a mark.
function rowOf(mark) {
  return screen.getByText(mark, { selector: "h6, span, p" }).closest("tr");
}

describe("DrawingSummaryPanel — evidence view", () => {
  it("groups marks into schedule tables with the shared source in the heading", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} documentId="doc_abc" />);
    expect(screen.getByText("Marks and definitions")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Lintels definitions" })).toBeInTheDocument();
    expect(screen.getByText(/Lintel schedule · S002 · PDF p\. 2 · 2 marks/)).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader", { name: "Defined section / component" }).length).toBe(4);
  });

  it("keeps L1 and L1A distinct by configuration while sharing W8X21", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    const l1 = within(rowOf("L1"));
    const l1a = within(rowOf("L1A"));
    expect(l1.getByText("W8X21")).toBeInTheDocument();
    expect(l1a.getByText("W8X21")).toBeInTheDocument();
    expect(l1.getByText("bottom plate")).toBeInTheDocument();
    expect(l1a.getByText("hung plate")).toBeInTheDocument();
    expect(l1.queryByText("hung plate")).not.toBeInTheDocument();
    expect(l1.getByText('bearing plate 6"x6"x1/2"')).toBeInTheDocument();
  });

  it("shows a bearing-plate mark with its printed size and no invented designation", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    const bp1 = within(rowOf("BP1"));
    expect(bp1.getByText('4"x6"x3/4"')).toBeInTheDocument();
    expect(bp1.getByText("bearing plate · printed size, no catalog designation")).toBeInTheDocument();
    expect(bp1.queryByText(/bent/i)).not.toBeInTheDocument();
  });

  it("shows the catalog angle with its condition and no redundant angle badge", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    const cl1 = within(rowOf("CL1"));
    expect(cl1.getByText("L5X5X3/8")).toBeInTheDocument();
    expect(cl1.getByText("ICF lintel · AISC v16 catalog")).toBeInTheDocument();
    expect(cl1.getByText("loose angle")).toBeInTheDocument();
    expect(cl1.queryByText("angle")).not.toBeInTheDocument();
    expect(screen.queryByText("plate")).not.toBeInTheDocument();
  });

  it("badges only meaningful states", () => {
    const defs = [
      definition("D1", "L5", null, { relation: "mark defines non-steel item", printed: "12F16-IB PRECAST LINTEL", status: "precast" }),
      definition("D2", "CL5", null, { relation: "mark defines no steel item", printed: "N/A", status: "no steel" }),
      definition("D3", "BP4", null, { relation: "mark defines plate", printed: '6"x8"x3/4"', status: "verify", role: "bearing plate" }),
    ];
    render(<DrawingSummaryPanel profile={evidenceProfile({ definitions: defs })} />);
    expect(screen.getByText("precast · not steel")).toBeInTheDocument();
    expect(screen.getByText("no steel (N/A)")).toBeInTheDocument();
    expect(screen.getByText("verify on sheet")).toBeInTheDocument();
  });

  it("states that schedule rows are definitions, never quantities", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.getByText(/it is never a quantity/)).toBeInTheDocument();
  });

  it("reveals the original schedule wording and model note on click", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.queryByText('L1 | W8x21 WITH BOTTOM PLATE | 6"x6"x1/2"')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show source details for L1" }));
    expect(screen.getByText('L1 | W8x21 WITH BOTTOM PLATE | 6"x6"x1/2"')).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show source details for L1A" }));
    expect(screen.getByText(/Model note: An L1A callout means a hung plate/)).toBeInTheDocument();
  });

  it("shows typed rules and actionable items", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.getByText("Rules affecting interpretation")).toBeInTheDocument();
    expect(screen.getByText("Default, U.N.O.")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText(/S102A · PDF pp\. 7, 8, 9, 10/)).toBeInTheDocument();
  });

  it("collapses long definition groups until expanded", () => {
    const many = Array.from({ length: 7 }, (_, i) => definition(`D${i + 1}`, `L${i + 1}`, "W8X21"));
    render(<DrawingSummaryPanel profile={evidenceProfile({ definitions: many })} />);
    expect(screen.queryByText("L7")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Show all 7"));
    expect(screen.getByText("L7")).toBeInTheDocument();
  });

  it("moves low-value background into collapsed supporting details", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.getByText("Supporting details")).toBeInTheDocument();
    const summary = screen.getByText("Supporting details").closest("[aria-expanded]");
    expect(summary).toHaveAttribute("aria-expanded", "false");
  });
});

// Entries shaped like the backend's column_schedule view (values from
// Brandywine S-600/S-601, Washington Latin S-202, Fort Davis S301).
const grid = (label, offset = null) => ({ label, offset });
const parsed = (raw, ...grids) => ({ raw, status: "parsed", grids });

function columnScheduleData() {
  return {
    schedules: [
      {
        id: "S1", name: "COLUMN SCHEDULE", layout: "graphical", key_role: "location",
        pages: [42, 43], sheets: ["S600", "S601"], page: 42, sheet: "S600",
        bbox: [250, 230, 2500, 860], block_count: 4, notes: [], hidden_text: [],
      },
      {
        id: "S2", name: "STEEL COLUMN SCHEDULE", layout: "graphical", key_role: "location",
        pages: [15], sheets: ["S202"], page: 15, sheet: "S202", bbox: [651, 98, 2594, 1065],
        block_count: 2, notes: ["NOTE: SEE TYPICAL DETAILS FOR TRANSFER BASE PLATE DETAIL."],
        hidden_text: ["314' - 0\"", "A-1"],
      },
      {
        id: "S3", name: "COLUMN SCHEDULE", layout: "graphical", key_role: "mark",
        pages: [15], sheets: ["S301"], page: 15, sheet: "S301", bbox: [539, 159, 1204, 716],
        block_count: 1, notes: [], hidden_text: [],
      },
    ],
    entries: [
      {
        id: "S1-8", schedule_id: "S1", key_role: "location", page: 42, sheet: "S600",
        bbox: [843, 760, 958, 860], mark: null,
        location_text: "A.4'-14, B-4.9, E-8(-4'-4\"), C'-15.6",
        locations: [
          parsed("A.4'-14", grid("A.4'"), grid("14")),
          parsed("B-4.9", grid("B"), grid("4.9")),
          parsed("E-8(-4'-4\")", grid("E"), grid("8", { raw: "-4'-4\"", inches: -52, direction: null })),
          parsed("C'-15.6", grid("C'"), grid("15.6")),
        ],
        listed_location_count: 4, repeated_label: false, label_conflict: null,
        sections: [{ designation: "W12X40", printed: "W12X40", catalog_exact: true }],
        plate: {
          status: "resolved", type: "base plate", printed: "BP7",
          dimensions: [
            { label: "thickness", raw: '1 1/2"' },
            { label: "width", raw: "1'-8\"" },
            { label: "length", raw: "1'-8\"" },
          ],
          via: [
            { kind: "leader mark", text: "BP7", page: 42, sheet: "S600", bbox: [880, 620, 900, 650], title: "COLUMN SCHEDULE" },
            { kind: "plate schedule", text: 'BP7 | B | 1 1/2" | 1\'-8"', page: 43, sheet: "S601", bbox: [730, 1880, 1600, 1890], title: "BASE PLATE SCHEDULE" },
          ],
        },
        other_plates: [], notes: [], conflicts: [], hidden_text: [], is_definition_not_quantity: true,
      },
      {
        id: "S2-1", schedule_id: "S2", key_role: "location", page: 15, sheet: "S202",
        bbox: [721, 127, 793, 201], mark: null, location_text: "A-1",
        locations: [parsed("A-1", grid("A"), grid("1"))], listed_location_count: 1,
        repeated_label: true, label_conflict: null,
        sections: [
          { designation: "W10X33", printed: "W10X33", catalog_exact: true },
          { designation: "W10X39", printed: "W10X39", catalog_exact: true },
        ],
        plate: {
          status: "read", type: "base plate", printed: "1 1/4\"x14\"x1'-2\"", markers: [],
          dimensions: [{ label: null, raw: '1 1/4"' }, { label: null, raw: '14"' }, { label: null, raw: "1'-2\"" }],
          via: [{ kind: "schedule cell", text: "1 1/4\"x14\"x1'-2\"", page: 15, sheet: "S202", bbox: [721, 961, 793, 993], title: "BASE PLATE" }],
        },
        other_plates: [], notes: [], conflicts: [], hidden_text: ["A-1"], is_definition_not_quantity: true,
      },
      {
        id: "S2-2", schedule_id: "S2", key_role: "location", page: 15, sheet: "S202",
        bbox: [793, 127, 865, 201], mark: null, location_text: "A-2",
        locations: [parsed("A-2", grid("A"), grid("2"))], listed_location_count: 1,
        repeated_label: true, label_conflict: null,
        sections: [{ designation: "W10X45", printed: "W10X45", catalog_exact: true }],
        plate: {
          status: "reference", type: "base plate", printed: "D/S-201", dimensions: [],
          reference: { raw: "D/S-201", detail: "D", sheet: "S-201", page: 14 },
          via: [{ kind: "schedule cell", text: "D/S-201", page: 15, sheet: "S202", bbox: [793, 961, 865, 993], title: "BASE PLATE" }],
        },
        other_plates: [], notes: ["BRACE FRAME COLUMN"], conflicts: [], hidden_text: [], is_definition_not_quantity: true,
      },
      {
        id: "S2-3", schedule_id: "S2", key_role: "location", page: 15, sheet: "S202",
        bbox: [1600, 127, 1670, 201], mark: null, location_text: "C.8-1",
        locations: [parsed("C.8-1", grid("C.8"), grid("1"))], listed_location_count: 1,
        repeated_label: true, label_conflict: null,
        sections: [{ designation: "W10X39", printed: "W10X39", catalog_exact: true }],
        plate: {
          status: "blank", type: "base plate", printed: "", dimensions: [], via: [],
          note: "Left blank in the schedule. Schedule note: NOTE: SEE TYPICAL DETAILS FOR TRANSFER BASE PLATE DETAIL.",
        },
        other_plates: [], notes: [], conflicts: [], hidden_text: [], is_definition_not_quantity: true,
      },
      {
        id: "S3-6", schedule_id: "S3", key_role: "mark", page: 15, sheet: "S301",
        bbox: [1033, 214, 1110, 266], mark: "C-2", location_text: null, locations: [],
        listed_location_count: 0, repeated_label: false, label_conflict: null,
        location_note: "C-2 is a column mark, not a grid intersection. Its positions are drawn on the column location plan; they are not read yet.",
        sections: [{ designation: "HSS10X10X5/16", printed: "HSS10X10X5/16", catalog_exact: true }],
        plate: {
          status: "read", type: "base plate", printed: '18"x18"x1"', markers: [],
          dimensions: [{ label: null, raw: '18"' }, { label: null, raw: '18"' }, { label: null, raw: '1"' }],
          via: [{ kind: "schedule cell", text: '18"x18"x1"', page: 15, sheet: "S301", bbox: [1033, 560, 1110, 600], title: "BASE PLATE" }],
        },
        other_plates: [], notes: [], conflicts: [], hidden_text: [], is_definition_not_quantity: true,
      },
    ],
    plate_tables: [],
  };
}

const withColumns = (extra = {}) => evidenceProfile({ column_schedule: columnScheduleData(), ...extra });

describe("DrawingSummaryPanel — column schedule", () => {
  it("shows one row per schedule column with section, location and plate", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    expect(screen.getByText("Column schedule")).toBeInTheDocument();
    expect(screen.getByText(/S600, S601 · PDF pp. 42, 43 · graphical schedule · printed in 4 parts/)).toBeInTheDocument();
    const row = within(screen.getByText("A.4'-14 +3").closest("tr"));
    expect(row.getByText("4 locations listed")).toBeInTheDocument();
    expect(row.getByText("W12X40")).toBeInTheDocument();
    expect(row.getByText("1 1/2\" thick × 1'-8\" wide × 1'-8\" long")).toBeInTheDocument();
    expect(row.getByText("Base plate BP7")).toBeInTheDocument();
    expect(row.getByText("resolved via plate schedule")).toBeInTheDocument();
  });

  it("keeps the printed location text next to the parsed grids and offsets", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    expect(screen.getByText("A.4'-14, B-4.9, E-8(-4'-4\"), C'-15.6")).toBeInTheDocument();
    expect(screen.getByText(/Grid E and grid 8 — offset -4'-4" from grid 8 \(direction not stated\)/)).toBeInTheDocument();
    expect(screen.getByText("Grid A.4' and grid 14")).toBeInTheDocument();
  });

  it("opens both the leader mark and the plate schedule row it resolved through", async () => {
    render(<DrawingSummaryPanel profile={withColumns()} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    fireEvent.click(screen.getByRole("button", { name: /View S601 · PDF p. 43 for BP7/ }));
    const viewer = await screen.findByTestId("pdf-viewer");
    expect(viewer).toHaveAttribute("data-page", "43");
    expect(viewer).toHaveAttribute("data-bbox", "[730,1880,1600,1890]");
  });

  it("shows a detail reference without inventing dimensions, and opens the detail sheet", async () => {
    render(<DrawingSummaryPanel profile={withColumns()} documentId="doc_abc" />);
    const row = within(screen.getByText("A-2").closest("tr"));
    expect(row.getByText("See detail D on S-201")).toBeInTheDocument();
    expect(row.getByText("Dimensions are on that detail — not read")).toBeInTheDocument();
    expect(row.getByText("BRACE FRAME COLUMN")).toBeInTheDocument();
    fireEvent.click(row.getByRole("button", { name: "Show details for A-2" }));
    fireEvent.click(screen.getByRole("button", { name: "View S-201 · PDF p. 14 for detail D" }));
    expect(await screen.findByTestId("pdf-viewer")).toHaveAttribute("data-page", "14");
  });

  it("says a repeated top/bottom label is one entry, and that masked text was ignored", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    expect(screen.getByText(/2 text items hidden under white masks in this schedule were ignored/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show details for A-1" }));
    expect(screen.getByText(/printed at the top and bottom of this column — one entry, not two/)).toBeInTheDocument();
    expect(screen.getByText(/Text hidden under a white mask in this column was ignored \(A-1\)/)).toBeInTheDocument();
  });

  it("shows a blank plate as blank, with the schedule's own note", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    const row = within(screen.getByText("C.8-1").closest("tr"));
    expect(row.getByText("Blank")).toBeInTheDocument();
    expect(row.getByText(/SEE TYPICAL DETAILS FOR TRANSFER BASE PLATE DETAIL/)).toBeInTheDocument();
  });

  it("never presents a column mark as a grid intersection", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    const row = within(screen.getByText("C-2").closest("tr"));
    expect(row.getByText("column mark")).toBeInTheDocument();
    fireEvent.click(row.getByRole("button", { name: "Show details for C-2" }));
    expect(screen.getByText(/C-2 is a column mark, not a grid intersection/)).toBeInTheDocument();
    expect(screen.queryByText(/Grid C and grid 2/)).not.toBeInTheDocument();
  });

  it("shows no quantity column or total", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    for (const table of screen.getAllByRole("table", { name: /columns$/ })) {
      expect(within(table).queryByRole("columnheader", { name: /qty|quantity|count|total/i })).not.toBeInTheDocument();
    }
    expect(screen.getByText(/Schedule entries are definitions — not takeoff\s+quantities/)).toBeInTheDocument();
  });

  it("does not list a scheduled column mark twice", () => {
    const data = columnScheduleData();
    data.entries.push({ ...data.entries[4], id: "S4-1", schedule_id: "S3", mark: "C1", page: 2 });
    render(<DrawingSummaryPanel profile={evidenceProfile({ column_schedule: data })} />);
    expect(screen.queryByRole("table", { name: "Columns definitions" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Lintels definitions" })).toBeInTheDocument();
  });

  it("is hidden when no column schedule was read", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile({ column_schedule: { schedules: [], entries: [] } })} />);
    expect(screen.queryByText("Column schedule")).not.toBeInTheDocument();
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.queryByText("Column schedule")).not.toBeInTheDocument();
  });
});

describe("DrawingSummaryPanel — source page navigation", () => {
  it("hides View page when no document is loaded", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.queryByRole("button", { name: /^View / })).not.toBeInTheDocument();
  });

  it("opens the uploaded PDF on S002 (PDF page 2) with the mark highlighted", async () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: "View S002 · PDF p. 2 for L1" }));
    const viewer = await screen.findByTestId("pdf-viewer");
    expect(viewer).toHaveAttribute("data-file", "/api/documents/doc_abc/pdf");
    expect(viewer).toHaveAttribute("data-page", "2");
    expect(viewer).toHaveAttribute("data-bbox", "[2021.4,1770.7,2030.5,1781.2]");
    expect(screen.getByRole("dialog", { name: "L1 — S002 · PDF p. 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close source page" }));
    await waitFor(() => expect(screen.queryByTestId("pdf-viewer")).not.toBeInTheDocument());
  });

  it("navigates to another page after a group is expanded", async () => {
    const many = Array.from({ length: 7 }, (_, i) =>
      definition(`D${i + 1}`, `L${i + 1}`, "W8X21", i === 6 ? { sheet: "S503", page: 22, bbox: null } : {}),
    );
    render(<DrawingSummaryPanel profile={evidenceProfile({ definitions: many })} documentId="doc_abc" />);
    fireEvent.click(screen.getByText("Show all 7"));
    fireEvent.click(screen.getByRole("button", { name: "View S503 · PDF p. 22 for L7" }));
    const viewer = await screen.findByTestId("pdf-viewer");
    expect(viewer).toHaveAttribute("data-page", "22");
    expect(viewer).toHaveAttribute("data-bbox", "null");
  });

  it("opens an unresolved item's first page", async () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: "View S102A · PDF p. 7" }));
    expect(await screen.findByTestId("pdf-viewer")).toHaveAttribute("data-page", "7");
  });
});
