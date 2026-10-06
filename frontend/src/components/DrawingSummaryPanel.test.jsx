import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    expect(screen.getByText("Project orientation")).toBeInTheDocument();
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
    expect(screen.getByText(/overview wording by model, checked against the drawing/)).toBeInTheDocument();
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
    expect(screen.getByText("Steel marks and definitions")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: /Other non-steel definitions/ }));
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
    expect(screen.getByText("Drawing notation")).toBeInTheDocument();
    expect(screen.getByText("Default, U.N.O.")).toBeInTheDocument();
    expect(screen.getByText("Items needing attention")).toBeInTheDocument();
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
    expect(screen.getByText("Original notation and extraction details")).toBeInTheDocument();
    const summary = screen.getByText("Original notation and extraction details").closest("[aria-expanded]");
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
    expect(screen.getByText("Steel column schedules and plates")).toBeInTheDocument();
    expect(screen.getByText(/S600, S601 · PDF pp. 42, 43 · graphical schedule · printed in 4 parts/)).toBeInTheDocument();
    const row = within(screen.getByText("A.4'-14 +3").closest("tr"));
    expect(row.getByText("4 locations")).toBeInTheDocument();
    expect(row.getByText("W12X40")).toBeInTheDocument();
    // Width × Length × Thickness, with proper symbols; the printed value on hover.
    expect(row.getByText("1′-8″ × 1′-8″ × 1½″")).toBeInTheDocument();
    expect(screen.getByText(/Width × Length × Thickness/)).toBeInTheDocument();
    expect(row.getByText("BP7")).toBeInTheDocument();

  });

  it("keeps the printed location text next to the parsed grids and offsets", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    expect(screen.getAllByText("A.4'-14, B-4.9, E-8(-4'-4\"), C'-15.6").length).toBeGreaterThan(0);
    expect(screen.getByText(/Offset -4'-4" from grid 8 — direction not stated/)).toBeInTheDocument();
    expect(screen.getByText("Grid A.4' and grid 14")).toBeInTheDocument();
  });

  it("opens both the leader mark and the plate schedule row it resolved through", async () => {
    render(<DrawingSummaryPanel profile={withColumns()} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    fireEvent.click(screen.getByRole("button", { name: "View S601 · PDF p. 43 for BP7 dimensions" }));
    const viewer = await screen.findByTestId("pdf-viewer");
    expect(viewer).toHaveAttribute("data-page", "43");
    expect(viewer).toHaveAttribute("data-bbox", "[730,1880,1600,1890]");
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[0]);
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-page", "42");
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-bbox", "[843,760,958,860]");
    fireEvent.click(tabs[1]);
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-page", "42");
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-bbox", "[880,620,900,650]");
  });

  it("preserves expanded entries while filtering by a printed grid identifier", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    const search = screen.getByRole("textbox", { name: "Find a location" });
    fireEvent.change(search, { target: { value: "C.8-1" } });
    expect(screen.queryByText("W12X40")).not.toBeInTheDocument();
    fireEvent.change(search, { target: { value: "C'-15.6" } });
    expect(screen.getByRole("button", { name: "Hide details for A.4'-14 +3" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Grid A.4' and grid 14/)).toBeInTheDocument();
  });

  it("keeps equal-sized plate marks distinct and lists every linked location", async () => {
    const data = columnScheduleData();
    data.entries[0].plate.printed = "CBP-3";
    data.entries.push({ ...data.entries[0], id: "S1-9", location_text: "D-9",
      locations: [parsed("D-9", grid("D"), grid("9"))], listed_location_count: 1,
      plate: { ...data.entries[0].plate, printed: "CBP-5" } });
    render(<DrawingSummaryPanel profile={evidenceProfile({ column_schedule: data })} />);
    fireEvent.click(screen.getByRole("button", { name: "Plate mark CBP-3: roles, source and locations" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/A.4'-14, B-4.9/)).toBeInTheDocument();
    expect(dialog.queryByText("D-9")).not.toBeInTheDocument();
    expect(dialog.getByText(/definitions, not a count of plates/)).toBeInTheDocument();
  });

  it("shows a detail reference without inventing dimensions, and opens the detail sheet", async () => {
    render(<DrawingSummaryPanel profile={withColumns()} documentId="doc_abc" />);
    const row = within(screen.getByText("A-2").closest("tr"));
    expect(row.getByText("See detail D on S-201")).toBeInTheDocument();
    expect(row.getByLabelText("Not established")).toHaveTextContent("—");
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
    expect(screen.getByText(/NOTE: SEE TYPICAL DETAILS FOR TRANSFER BASE PLATE DETAIL/)).toBeInTheDocument();
  });

  it("never presents a column mark as a grid intersection", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    const row = within(screen.getByText("C-2").closest("tr"));
    expect(within(screen.getByText("C-2").closest("table")).getByRole("columnheader", { name: "Mark" })).toBeInTheDocument();
    fireEvent.click(row.getByRole("button", { name: "Show details for C-2" }));
    expect(screen.getByText(/C-2 is a column mark, not a grid intersection/)).toBeInTheDocument();
    expect(screen.queryByText(/Grid C and grid 2/)).not.toBeInTheDocument();
  });

  it("shows no quantity column or total", () => {
    render(<DrawingSummaryPanel profile={withColumns()} />);
    for (const table of screen.getAllByRole("table", { name: /columns$/ })) {
      expect(within(table).queryByRole("columnheader", { name: /qty|quantity|count|total/i })).not.toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole("button", { name: "Show details for C-2" }));
    expect(screen.getByText(/A schedule entry is a definition, not a counted member/)).toBeInTheDocument();
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
    expect(screen.queryByText("Steel column schedules and plates")).not.toBeInTheDocument();
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.queryByText("Steel column schedules and plates")).not.toBeInTheDocument();
  });
});

// Shaped like the backend's levels view (OSSE S-602-O / S-122-O, Furley
// S102C, Washington Latin S-202 / S-102 / S-103).
function levelsData() {
  const src = (page, sheet, text, bbox = [10, 20, 30, 40]) => ({ page, sheet, text, bbox });
  return {
    schedule_levels: [
      {
        schedule_id: "S2", schedule: "OSSE BUILDING - GCS", name: "T.O. SLAB LEVEL 2", printed: "55' - 10\"",
        elevation: { raw: "55' - 10\"", display: "55'-10\"" }, status: "read", page: 26, sheet: "S602",
        bbox: [161, 1533, 240, 1572], blocks: 1, conflict: true, also_titled: [],
        plan_matches: [{
          page: 10, sheet: "S122", plan: "SECOND FLOOR PLAN", comparison: "differs",
          values: [{ surface: "top of slab", display: "55'-2\"", raw: "55' - 2\"", status: "read",
            source: src(10, "S122", "DATUM ELEVATION 0'-0\" REFERENCES TOP OF SECOND FLOOR SLAB ELEVATION 55' - 2\"", [2555, 371, 2876, 555]) }],
        }],
      },
      {
        schedule_id: "S3", schedule: "STEEL COLUMN SCHEDULE", name: "SECOND FLOOR", printed: "SEE PLAN", elevation: null,
        status: "see_plan", page: 15, sheet: "S202", bbox: [653, 568, 697, 595], blocks: 1, conflict: false,
        resolved: { surface: "top of slab", display: "330'-0\"", via: "S102" }, plan_matches: [], also_titled: [],
      },
      {
        schedule_id: "S3", schedule: "STEEL COLUMN SCHEDULE", name: "THIRD FLOOR", printed: "SEE PLAN", elevation: null,
        status: "see_plan", page: 15, sheet: "S202", bbox: [653, 438, 697, 464], blocks: 1, conflict: false,
        resolved: null, note: "The matching plan shows 2 different values; the level is not reduced to one.",
        plan_matches: [], also_titled: [],
      },
    ],
    plan_elevations: [
      {
        status: "derived", surface: "top of steel", plan: "SECOND FLOOR / MECHANICAL ROOM FLOOR FRAMING NOTES",
        area: "MEACHANICAL ROOM", page: 9, sheet: "S102C", value: { raw: null, display: "18'-8\"" },
        offset: { display: "-0'-8\"", raw: "8\"", direction: "below", relative_to: "top of slab" },
        rule: "TOP OF STEEL ELEVATION (BOTTOM OF DECK) SHALL BE 8\" BELOW TOP OF SLAB",
        inputs: [src(9, "S102C", "TOP OF SLAB ELEVATION SHALL BE 19'-4\"", [1908, 1383, 2454, 1652]),
          src(9, "S102C", "TOP OF STEEL ELEVATION (BOTTOM OF DECK) SHALL BE 8\" BELOW TOP OF SLAB", [1908, 1383, 2454, 1652])],
        unless_noted: true, exceptions: { notation: "(", count: 4, examples: ["W16x26 [14] (13.00')"] },
        source: src(9, "S102C", "TOP OF SLAB ELEVATION SHALL BE 19'-4\""),
      },
      {
        status: "unresolved", surface: "top of steel", plan: "FLOOR PLAN", area: null, page: 10, sheet: "S122", value: null,
        note: "The note gives <0' - 5 1/4\"> from the top of slab but not whether it is above or below.",
        rule: "TOP OF STEEL ELEVATION IS <0' - 5 1/4\"> FROM TOP OF SLAB", unless_noted: true,
        source: src(10, "S122", "TOP OF STEEL ELEVATION IS <0' - 5 1/4\"> FROM TOP OF SLAB"),
      },
    ],
    datums: [{ page: 7, sheet: "S102A", plan: "UPPER FLOOR FRAMING PLAN NOTES", status: "read",
      relation: "reference elevation 14'-6\" corresponds to true elevation 112'-0\"", source: src(7, "S102A", "REFERENCE ELEVATION") }],
    notations: [{ page: 2, sheet: "S001", sample: "(##' - ##\")", meaning: "bottom of base plate", relative_to: "datum",
      scope: "project legend", source: src(2, "S001", "(##' - ##\") BOTTOM OF BASE PLATE ELEVATION RELATIVE TO DATUM") }],
    noted_on_plans: [],
  };
}

describe("DrawingSummaryPanel — levels and elevations", () => {
  const withLevels = () => evidenceProfile({ levels: levelsData() });

  it("shows a schedule level next to a differing plan value without replacing it", () => {
    render(<DrawingSummaryPanel profile={withLevels()} />);
    expect(screen.getByText("Levels and supported vertical extents")).toBeInTheDocument();
    const row = within(screen.getByText("Level 2", { selector: "td p, td span" }).closest("tr"));
    expect(row.getByText("55′-10″")).toBeInTheDocument();
    expect(row.getByText("55′-2″")).toBeInTheDocument();
    expect(row.getByText("Sources disagree")).toBeInTheDocument();
  });

  it("resolves SEE PLAN only to a single plan value", () => {
    render(<DrawingSummaryPanel profile={withLevels()} />);
    expect(within(screen.getByText("Second Floor").closest("tr")).getByText((_, el) => el?.tagName === "P" && el.textContent === "Top of slab 330′-0″ on S102")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Why this source.*THIRD FLOOR/ }));
    expect(screen.getByText(/2 different values/)).toBeInTheDocument();
  });

  it("shows a derived top of steel with its slab value and the note's offset", async () => {
    render(<DrawingSummaryPanel profile={withLevels()} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: /Detailed level evidence/ }));
    const row = within(screen.getByText("18′-8″").closest("tr"));
    expect(row.getByText("Calculated from stated values")).toBeInTheDocument();
    expect(row.getByText(/TOP OF SLAB ELEVATION SHALL BE 19'-4" 0'-8" below top of slab/)).toBeInTheDocument();
    expect(row.getByText(/4 local values noted on this sheet/)).toBeInTheDocument();
    fireEvent.click(row.getByRole("button", { name: "View S102C · PDF p. 9 for the value it is derived from" }));
    expect(await screen.findByTestId("pdf-viewer")).toHaveAttribute("data-page", "9");
  });

  it("leaves an offset with no stated direction unresolved, with no value", () => {
    render(<DrawingSummaryPanel profile={withLevels()} />);
    fireEvent.click(screen.getByRole("button", { name: /Detailed level evidence/ }));
    const row = within(screen.getByText(/not whether it is above or below/).closest("tr"));
    expect(row.getByText("Not established")).toBeInTheDocument();
    expect(row.getByText("—")).toBeInTheDocument();
  });

  it("lists datum relations and project notations", () => {
    render(<DrawingSummaryPanel profile={withLevels()} />);
    fireEvent.click(screen.getByRole("button", { name: /Detailed level evidence/ }));
    expect(screen.getByText(/reference elevation 14'-6" corresponds to true elevation 112'-0"/)).toBeInTheDocument();
    expect(screen.getByText(/on a plan means bottom of base plate, measured from the datum/)).toBeInTheDocument();
  });

  it("is hidden without level evidence", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile()} />);
    expect(screen.queryByText("Levels and supported vertical extents")).not.toBeInTheDocument();
  });
});

describe("DrawingSummaryPanel — column vertical extent", () => {
  function withExtent(extent, difference) {
    const data = columnScheduleData();
    data.entries[0] = { ...data.entries[0], extent, level_difference: difference };
    return evidenceProfile({ column_schedule: data });
  }
  const line = (name, elevation_text) => ({ name, elevation_text, y: 0 });

  it("shows a level-to-level difference as such, never as a column length", () => {
    render(<DrawingSummaryPanel profile={withExtent(
      { top: { position: "at", line: line("T.O. ROOF", "69' - 4\"") }, bottom: { position: "at", line: line("T.O. SLAB LEVEL 1", "38' - 0\"") } },
      { status: "computed", inches: 376, display: "31'-4\"", upper: { name: "T.O. ROOF", elevation: "69' - 4\"" },
        lower: { name: "T.O. SLAB LEVEL 1", elevation: "38' - 0\"" } },
    )} />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    expect(screen.getByText("31′-4″")).toBeInTheDocument();
    expect(screen.getByText("Calculated from the two printed level elevations")).toBeInTheDocument();
    expect(screen.getByText("Unconfirmed")).toBeInTheDocument();
    expect(screen.getByText("Fabricated length")).toBeInTheDocument();
  });

  it("shows no height when an end is between level lines", () => {
    render(<DrawingSummaryPanel profile={withExtent(
      { top: { position: "between", near: "upper", upper: line("LEVEL 2", "14'-0\""), lower: line("LEVEL 1", "0\"") },
        bottom: { position: "at", line: line("LEVEL 1", "0\"") } },
      { status: "unresolved", note: "One end is not drawn on a level line." },
    )} />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    expect(screen.getByText(/Top: between LEVEL 2 \(14'-0"\) and LEVEL 1 \(0"\) — drawn just below LEVEL 2/)).toBeInTheDocument();
    expect(screen.getByText(/No height shown: One end is not drawn on a level line/)).toBeInTheDocument();
    expect(screen.queryByText(/Level-to-level difference/)).not.toBeInTheDocument();
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

describe("DrawingSummaryPanel — level bands and flagged values", () => {
  const levels = () => ({
    schedule_levels: [], plan_elevations: [], datums: [], notations: [],
    level_bands: [{
      schedule_id: "S1", schedule: "COLUMN SCHEDULE", printed: "14' - 0\" FIRST FLOOR", pairing: "unpaired", level: null,
      upper: { name: "SECOND FLOOR", elevation: "14' - 0\"" }, lower: { name: "FIRST FLOOR", elevation: "0' - 0\"" },
      page: 26, sheet: "S501", blocks: 4, schedule_rows: 118,
    }],
    noted_on_plans: [{
      page: 8, sheet: "S2.04", plan: "FRAMING PLAN", meaning: ["top of steel (from top of datum slab on grade)"],
      count: 2, flagged: 1, rule_sheets: ["S2.01"],
      examples: [
        { text: "TOS (30'-8\")", value: "(30'-8\")", status: "read", page: 8, sheet: "S2.04", bbox: [1, 2, 3, 4] },
        { text: "TOS (+30'-8)", value: "(+30'-8)", status: "flagged", candidate: "30'-8\"",
          flag: "closing inch mark missing", page: 8, sheet: "S2.04", bbox: [5, 6, 7, 8] },
      ],
    }],
  });

  it("explains that a printed band joins two different levels", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile({ levels: levels() })} />);
    fireEvent.click(screen.getByRole("button", { name: /Detailed level evidence/ }));
    expect(screen.getByText(/two levels: 14' - 0" is SECOND FLOOR; FIRST FLOOR is at\s+0' - 0"/)).toBeInTheDocument();
    expect(screen.getByText(/the label of 118 schedule rows/)).toBeInTheDocument();
  });

  it("shows a flagged value with its printed text and candidate, apart from read values", async () => {
    render(<DrawingSummaryPanel profile={evidenceProfile({ levels: levels() })} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: /Detailed level evidence/ }));
    expect(screen.getByText(/notation defined on S2.01/)).toBeInTheDocument();
    expect(screen.getByText("flagged")).toBeInTheDocument();
    expect(screen.getByText(/closing inch mark missing; reads\s+as 30'-8" if completed/)).toBeInTheDocument();
    expect(screen.queryByText(/e\.g\. .*\(\+30'-8\)/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /for \(\+30'-8\) \(flagged 1\)/ }));
    expect(await screen.findByTestId("pdf-viewer")).toHaveAttribute("data-page", "8");
  });
});

describe("DrawingSummaryPanel — column tracing pilot", () => {
  const trace = {
    status: "traced", pilot: true, location_text: "A.4'-14", grids: [], sections: ["W10X33"], notes: [],
    schedule: { id: "S1", title: "COLUMN SCHEDULE", page: 42, sheet: "S600", bbox: [1, 2, 3, 4] },
    ends: {
      top: { state: "established", level: "T.O. ROOF", elevation: "69' - 4\"", by: "drawn on the schedule's level line",
        plan_annotations: [] },
      bottom: { state: "unresolved", position: "between",
        plan_annotations: [{ sheet: "S121", page: 9, text: "POST UP", bbox: [1, 2, 3, 4] }],
        note: "The schedule draws the bottom end between two level lines; it is not moved to the nearest line." },
    },
    levels: [{
      name: "T.O. ROOF", elevation: "69' - 4\"", other_titled_sheets: ["S3.05"],
      other_scope_views: [{ page: 5, sheet: "S101", view_title: null, sheet_title: "OSSE PARKING FOUNDATION AND FIRST FLOOR PLAN",
        note: "The view is titled for PARKING, another schedule's scope." }],
      plans: [{
        page: 11, sheet: "S123", plan: "OSSE FACILITY ROOF PLAN", observation: "column_symbol", ambiguous_match: false,
        matched_by: "the plan's note names OFFICE ROOF at the same elevation", grid_axes: [1, 1],
        candidates: [{ page: 11, point_bbox: [2171, 1487, 2177, 1493], symbol: { bbox: [2170, 1480, 2177, 1497] },
          scale: { status: "validated", printed: { raw: "1/8\" = 1'-0\"" }, note: "1/8\" = 1'-0\" agrees with 13 printed grid dimensions." },
          offset: { grid: "8", printed: "-4'-4\"", status: "placed", note: "The column is drawn -4'-4\" from grid 8, toward grid 7, at the view's validated scale.",
            sides: [{ toward: "7", point_bbox: [2012, 1001, 2018, 1007], symbol: { bbox: [2011, 999, 2018, 1009] } },
              { toward: "9", point_bbox: [2090, 1001, 2096, 1007], symbol: null }] },
          scope: { status: "supported_by_datum", view_title: null, sheet_title: "OSSE FACILITY ROOF PLAN",
            note: "The plan's note names OFFICE ROOF at 69'-4\", a level of this schedule only." },
          annotations: [], nearby_text: [{ text: "69' - 9\"", how: "nearby" }] }],
      }],
    }],
    directional_evidence: [{ level: "T.O. ROOF", sheet: "S123", page: 11, text: "COL UP", bbox: [1, 2, 3, 4],
      direction: "up", scope_counts: true }],
    summary: { levels_spanned: ["T.O. ROOF"], levels_with_symbol: ["T.O. ROOF"], logical_stack_only: true,
      note: "Observations describe one logical column stack at this location; they do not establish how many fabricated pieces it is made of." },
  };

  it("loads a trace on request and shows honest end states with plan sources", async () => {
    const client = await import("../api/client");
    const spy = vi.spyOn(client, "getColumnTrace").mockResolvedValue(trace);
    render(<DrawingSummaryPanel profile={evidenceProfile({ column_schedule: columnScheduleData() })} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    // The entry lists four locations; each is traced on its own.
    expect(screen.getByRole("button", { name: "C'-15.6" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "E-8(-4'-4\")" }));
    expect(await screen.findByText(/column symbol drawn at the grid intersection/)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith("doc_abc", "E-8(-4'-4\")", "S1");
    expect(screen.getByRole("button", { name: "Trace another location" })).toBeInTheDocument();
    expect(screen.getByText(/Bottom end: S121 prints “POST UP” with a leader to the column/)).toBeInTheDocument();
    expect(screen.getByText(/Nearby, not associated: 69' - 9"/)).toBeInTheDocument();
    expect(screen.getByText(/Scale: validated — 1\/8" = 1'-0"/)).toBeInTheDocument();
    expect(screen.getByText(/toward grid 7, at the view's validated scale/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /for T.O. ROOF offset toward grid 7/ })).toHaveTextContent("Toward grid 7 (column drawn)");
    expect(screen.getByText(/“COL UP” \(up\)/)).toBeInTheDocument();
    expect(screen.getByText(/Scope: same building \/ area \(datum note\) — OSSE FACILITY ROOF PLAN/)).toBeInTheDocument();
    expect(screen.getByText(/Not this building \/ area: S101 · OSSE PARKING FOUNDATION AND FIRST FLOOR PLAN/)).toBeInTheDocument();
    expect(screen.getByText(/do not establish how many fabricated pieces/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /View S123 · PDF p. 11 for T.O. ROOF grid intersection/ })[0]);
    expect(await screen.findByTestId("pdf-viewer")).toHaveAttribute("data-page", "11");
    spy.mockRestore();
  });

  it("offers no trace without a stored document", () => {
    render(<DrawingSummaryPanel profile={evidenceProfile({ column_schedule: columnScheduleData() })} />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    expect(screen.queryByRole("button", { name: "E-8(-4'-4\")" })).not.toBeInTheDocument();
  });

  it("ignores a late trace for a previous location and clears its plan sources", async () => {
    const client = await import("../api/client");
    let finishFirst;
    const spy = vi.spyOn(client, "getColumnTrace")
      .mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve; }))
      .mockResolvedValueOnce({ status: "unresolved", note: "Second location has no supported plan match." });
    render(<DrawingSummaryPanel profile={withColumns()} documentId="doc_abc" />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for A.4'-14 +3" }));
    fireEvent.click(screen.getByRole("button", { name: "A.4'-14" }));
    fireEvent.click(screen.getByRole("button", { name: "Trace another location" }));
    fireEvent.click(screen.getByRole("button", { name: "B-4.9" }));
    await screen.findByText("Second location has no supported plan match.");
    await act(async () => finishFirst(trace));
    expect(screen.getByText("Selected location: B-4.9")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /T.O. ROOF grid intersection/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/column symbol drawn at the grid intersection/)).not.toBeInTheDocument();
    spy.mockRestore();
  });
});
