import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DrawingSummaryPanel from "./DrawingSummaryPanel";

// Drawing Summary review on OSSE (October 2026): reading order, conflict
// comparison, evidence chain, level schematic, scope / association states,
// notation key, grid offsets, precast parking columns and labelled concrete
// cells. Fixtures are shaped like the backend payload for OSSE - ST.pdf.

vi.mock("./pdf/PdfDocumentViewer", () => ({
  default: ({ selection }) => (
    <div
      data-testid="pdf-viewer"
      data-page={String(selection?.pageNumber)}
      data-bbox={JSON.stringify(selection?.boundingBox ?? null)}
    />
  ),
}));

const narrative = {
  project_overview: "26-page structural set (permit set, numbered revision). Steel column schedule: OSSE BUILDING - GCS (S602).",
  structural_content: "", steel_system: "", drawing_language: "No project-specific shorthand substitutions were found.",
  typical_conditions: "", schedules: "No structural schedules identified.", scope_revision: "", important_notes: [], uncertainties: [],
};

const level = (name, printed, inches, extra = {}) => ({
  schedule_id: "S2", schedule: "OSSE BUILDING - GCS", name, printed, elevation: { inches }, status: "read",
  page: 26, sheet: "S602", bbox: [160, 1500, 240, 1540], plan_matches: [], also_titled: [], excluded_scope: [],
  conflict: false, association: "unresolved", surface: null, ...extra,
});
const value = (raw, inches, page, sheet, name) => ({
  surface: "top of slab", raw, display: raw, inches, status: "read", compared: true, name,
  source: { page, sheet, bbox: [2555, 371, 2876, 555], text: "DATUM ELEVATION 0'-0\" REFERENCES ..." },
});

function osseProfile() {
  const levels = [
    level("T.O. ROOF", "69' - 4\"", 832, {
      association: "linked",
      plan_matches: [{ page: 11, sheet: "S123", plan: "OSSE FACILITY ROOF PLAN", association: "supported",
        scope: { status: "supported_by_datum" }, name_relation: "qualified", plan_qualifiers: ["OFFICE"],
        comparison: "agrees", values: [value("69' - 4\"", 832, 11, "S123", "OFFICE ROOF")] }],
      excluded_scope: [{ page: 6, sheet: "S102", sheet_title: "OSSE PARKING SECOND FLOOR PLAN" }],
    }),
    level("T.O. SLAB LEVEL 2", "55' - 10\"", 670, {
      association: "linked", conflict: true, surface: "top of slab",
      plan_matches: [{ page: 10, sheet: "S122", plan: "SECOND FLOOR PLAN", association: "supported",
        scope: { status: "consistent_by_sheet_family" }, plan_qualifiers: [], comparison: "differs",
        values: [value("55' - 2\"", 662, 10, "S122", "SECOND FLOOR")] }],
    }),
    level("T.O. SLAB LEVEL 1", "38' - 0\"", 456, {
      association: "linked", surface: "top of slab",
      plan_matches: [{ page: 9, sheet: "S121", plan: "FIRST FLOOR PLAN", association: "supported",
        scope: { status: "supported_by_datum" }, plan_qualifiers: [], comparison: "agrees",
        values: [value("38' - 0\"", 456, 9, "S121", "FIRST FLOOR")] }],
      excluded_scope: [{ page: 5, sheet: "S101", sheet_title: "OSSE PARKING FOUNDATION AND FIRST FLOOR PLAN" }],
    }),
    level("T.O. PARKING LOWER DECK", "33' - 0\"", 396, { surface: "top of deck" }),
    { ...level("T.O. PARKING DECK SLAB", "50' - 0\"", 600), schedule_id: "S1", schedule: "OSSE PARKING - GCS",
      association: "checked_no_value", also_titled: ["S102"] },
  ];
  const steel = {
    id: "S2-20", schedule_id: "S2", key_role: "location", page: 26, sheet: "S602", bbox: [1700, 1848, 1772, 1937],
    mark: null, location_text: "C.8-8.9",
    locations: [{ raw: "C.8-8.9", status: "parsed", grids: [{ label: "C.8", offset: null }, { label: "8.9", offset: null }] }],
    listed_location_count: 1, sections: [{ designation: "W10X33", printed: "W10x33" }],
    plate: {
      status: "resolved", type: "base plate", printed: "CBP-2",
      dimensions: [{ label: "width", raw: "12\"" }, { label: "length", raw: "18\"" }, { label: "thickness", raw: "3/4\"" }],
      via: [
        { kind: "location table", text: "C.8-8.9 | W10x33 | CBP-2", title: "BASE PLATE", page: 25, sheet: "S601", bbox: [1134, 1755, 1353, 1768] },
        { kind: "plate schedule", text: "CBP-2 | 12\" | 18\" | 3/4\"", title: "BASE PLATE TYPE SCHEDULE", page: 25, sheet: "S601", bbox: [1134, 1922, 1422, 1935] },
      ],
    },
    other_plates: [], notes: [], conflicts: [], hidden_text: [], material: { status: "catalog section", material: "steel" },
    extent: { top: { position: "at", line: { name: "T.O. ROOF", elevation_text: "69' - 4\"" } },
      bottom: { position: "at", line: { name: "T.O. SLAB LEVEL 1", elevation_text: "38' - 0\"" } } },
    level_difference: { status: "computed", inches: 376, display: "31'-4\"",
      upper: { name: "T.O. ROOF", elevation: "69' - 4\"" }, lower: { name: "T.O. SLAB LEVEL 1", elevation: "38' - 0\"" } },
  };
  const parking = (id, location, printed, material) => ({
    id, schedule_id: "S1", key_role: "location", page: 26, sheet: "S602", bbox: [220, 390, 296, 466], mark: null,
    location_text: location, locations: [{ raw: location, status: "parsed", grids: [] }], listed_location_count: 1,
    sections: [{ designation: null, printed }], plate: { status: "not_shown", printed: "", dimensions: [], via: [] },
    other_plates: [], notes: [], conflicts: [], hidden_text: [], ...(material ? { material } : {}),
  });
  return {
    status: "SUCCESS", abbreviation_rules: [], project_rules: [], derived_insights: [],
    drawing_intelligence: {
      version: "drawing_intelligence_v3", method: "deterministic", page_count: 26, narrative,
      steel_system: { families: [] }, typical_conditions: [], schedule_insights: [], scope_signals: [], uncertainties: [],
      definitions: [{
        id: "D1", mark: "W1", component: "schedule", component_label: "Other schedule marks", schedule: "Schedule",
        schedule_title: "CONCRETE WALL SCHEDULE", relation: "mark defines non-steel item", role: "other schedule",
        printed: "#4@12\" O.C. E.F. #4@12\" O.C. E.F.", status: "not steel", configuration: [], parts: [],
        source_text: "W1 | ...", page: 25, sheet: "S601", bbox: [232, 934, 247, 943],
        cells: [{ heading: "WIDTH", group: "WIDTH", text: "12\"" },
          { heading: "REINFORCEMENT VERTICAL", group: "REINFORCEMENT", text: "#4@12\" O.C. E.F." },
          { heading: "HORIZONTAL", group: "REINFORCEMENT", text: "#4@12\" O.C. E.F." }],
      }],
      interpretation_rules: [{
        id: "R3", relation: "notation key", kind: "framing_key", scope: "project legend", page: 2, pages: [2], sheet: "S001",
        bbox: [388, 1711, 724, 1843], source_text: "W18X40 [35] c=1 1/4\" <+12'-3\">", text: "...",
        parts: [
          { token: "[35]", status: "defined", meaning: "# OF SHEAR STUDS. SEE TYPICAL DETAIL", field: "shear_studs" },
          { token: "c=1 1/4\"", status: "defined", meaning: "CAMBER", field: "camber" },
          { token: "<+12'-3\">", status: "no_leader", meaning: null },
        ],
      }],
      unresolved: [],
      column_schedule: {
        schedules: [
          { id: "S1", name: "OSSE PARKING - GCS", layout: "graphical", key_role: "location", pages: [26], sheets: ["S602"],
            page: 26, sheet: "S602", bbox: [150, 100, 2455, 466], block_count: 3,
            notes: ["NOTE: ALL C_ COLUMNS ARE PRECAST COLUMNS AND TO BE DESIGNED AND DETAILED BY CONTRACTOR'S ENGINEER"],
            hidden_text: [], material_group: "concrete", entry_count: 2 },
          { id: "S2", name: "OSSE BUILDING - GCS", layout: "graphical", key_role: "location", pages: [26], sheets: ["S602"],
            page: 26, sheet: "S602", bbox: [150, 1400, 2455, 1940], block_count: 1, notes: [], hidden_text: [],
            material_group: "steel", entry_count: 1 },
        ],
        entries: [
          parking("S1-1", "A-1", "C1 - 24\"x24\"", { status: "read", material: "precast concrete", mark: "C1",
            size: { raw: "24\"x24\"", dimensions: [{ raw: "24\"", inches: 24 }, { raw: "24\"", inches: 24 }] },
            source: { text: "NOTE: ALL C_ COLUMNS ARE PRECAST", page: 26, sheet: "S602" } }),
          parking("S1-2", "RA.1-R13", "RC1 - 24\" x 24\"", null),
          steel,
        ],
        plate_tables: [],
      },
      levels: {
        schedule_levels: levels, level_bands: [], plan_elevations: [], datums: [], notations: [], noted_on_plans: [],
        location_offsets: [{ location: "C.1(-6\")-7.3", grid: "C.1", offset: { raw: "-6\"", inches: -6 }, text: "(-6\")",
          page: 25, sheet: "S601", bbox: [1100, 1700, 1180, 1712] }],
        legend_examples: [{ text: "W18X40 [35] c=1 1/4\" <+12'-3\">", value: "<+12'-3\">", page: 2, sheet: "S001" }],
      },
      facts: [
        { id: "C1", type: "column", refs: { column_entry: "S2-20" } },
        { id: "X1", type: "level_conflict", difference_inches: 8, refs: { schedule_id: "S2", level: "T.O. SLAB LEVEL 2", plan_page: 10 } },
      ],
      summary_llm: {
        overview: "x", overview_source: "deterministic",
        key_facts: [{ id: "C1", why: "Check base plate CBP-2 before setting anchor rods." }],
        cautions: [{ id: "X1", why: "Confirm which Level 2 elevation applies; the drawing does not say which governs." }],
      },
    },
  };
}

const renderOsse = (documentId = "doc_osse") => render(<DrawingSummaryPanel profile={osseProfile()} documentId={documentId} />);

describe("Drawing Summary — OSSE estimator view", () => {
  it("reads in the estimator's order: orientation, attention, steel, levels, notation, supporting", () => {
    renderOsse();
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    const order = ["Project orientation", "Items needing attention", "Steel column schedules and plates",
      "Levels and supported vertical extents", "Drawing notation", "Supporting schedules and evidence"];
    expect(order.every((h) => headings.includes(h))).toBe(true);
    for (let i = 1; i < order.length; i += 1) expect(headings.indexOf(order[i])).toBeGreaterThan(headings.indexOf(order[i - 1]));
    // Parking (concrete) and the concrete wall schedule are supporting information.
    expect(screen.getByRole("button", { name: /Parking and concrete column schedules/ })).toBeInTheDocument();
  });

  it("shows the Level 2 conflict with both values, the difference and both sources, resolving nothing", async () => {
    renderOsse();
    const attention = screen.getByText("Items needing attention").closest("section");
    expect(within(attention).getByText("55′-10″")).toBeInTheDocument();
    expect(within(attention).getByText("55′-2″")).toBeInTheDocument();
    expect(within(attention).getByText("8″")).toBeInTheDocument();
    expect(within(attention).getByText(/Both values are kept; the drawing does not say which governs/)).toBeInTheDocument();
    expect(within(attention).getByText(/Model note: Confirm which Level 2 elevation applies/)).toBeInTheDocument();
    fireEvent.click(within(attention).getByRole("button", { name: /S122 · PDF p. 10 for T.O. SLAB LEVEL 2 on S122/ }));
    expect(await screen.findByTestId("pdf-viewer")).toHaveAttribute("data-page", "10");
  });

  it("compares the two sources side by side, each on its own page", async () => {
    renderOsse();
    fireEvent.click(screen.getByRole("button", { name: "Compare side by side" }));
    const viewers = await screen.findAllByTestId("pdf-viewer");
    expect(viewers.map((v) => v.getAttribute("data-page"))).toEqual(["26", "10"]);
  });

  it("reads a typical steel column with plate roles, extent and an evidence chain to each source", async () => {
    renderOsse();
    fireEvent.click(screen.getByRole("button", { name: "Show details for C.8-8.9" }));
    expect(screen.getByText("C.8-8.9", { selector: "dd span" })).toBeInTheDocument();
    expect(screen.getByText("Base plate", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getAllByText("CBP-2")).toHaveLength(2);
    expect(screen.getAllByLabelText("width 12 inches, length 18 inches, thickness three quarters of an inch")).toHaveLength(2);
    expect(screen.getByText("Level 1 to Roof")).toBeInTheDocument();
    expect(screen.getByLabelText("31 feet 4 inches")).toHaveTextContent("31′-4″");
    expect(screen.getByText("Fabricated length")).toBeInTheDocument();
    expect(screen.getByText("Unconfirmed")).toBeInTheDocument();
    expect(screen.getByText(/Model note: Check base plate CBP-2/)).toBeInTheDocument();
    const chain = screen.getByRole("list", { name: /Evidence chain/ });
    expect(within(chain).getAllByRole("button").map((b) => b.textContent)).toEqual(
      ["View column schedule", "View plate assignment", "View plate dimensions"]);
    fireEvent.click(within(chain).getByRole("button", { name: /for CBP-2 dimensions/ }));
    const viewer = await screen.findByTestId("pdf-viewer");
    expect(viewer).toHaveAttribute("data-page", "25");
    expect(viewer).toHaveAttribute("data-bbox", "[1134,1922,1422,1935]");
  });

  it("draws the schedule's levels as a schematic with the column's supported ends", () => {
    renderOsse();
    fireEvent.click(screen.getByRole("button", { name: "Show details for C.8-8.9" }));
    expect(screen.getByText(/schematic, not to scale/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /top end is at T.O. ROOF and its bottom end is at T.O. SLAB LEVEL 1/ })).toBeInTheDocument();
  });

  it("says why a level has no plan value instead of implying it does not exist", () => {
    renderOsse();
    expect(screen.getByText("No linked plan evidence yet")).toBeInTheDocument();
    expect(screen.getByText("Elevation not found in the linked sources")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Parking \/ concrete schedule levels/ }));
    fireEvent.click(screen.getByRole("button", { name: /Why this source.*T.O. PARKING DECK SLAB/ }));
    expect(screen.getByText(/Also checked S102: no elevation stated there/)).toBeInTheDocument();
    expect(screen.queryByText(/No plan with a matching title states/)).not.toBeInTheDocument();
  });

  it("links the roof to the office-roof datum with its qualifier and keeps parking sheets out", () => {
    renderOsse();
    const roof = within(screen.getByText("Roof", { selector: "td p" }).closest("tr"));
    expect(roof.getByText(/Office roof/i)).toBeInTheDocument();
    expect(roof.getByText("Agrees")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Why this source.*T.O. SLAB LEVEL 1/ }));
    expect(screen.getByText(/Not this building \/ area: S101/)).toBeInTheDocument();
  });

  it("decodes the framing key part by part and never decodes a part without a leader", () => {
    renderOsse();
    expect(screen.getByText(/# of shear studs. see typical detail \(label at the end of its leader\)/i)).toBeInTheDocument();
    expect(screen.getByText("No leader to a visible label — not decoded")).toBeInTheDocument();
    expect(screen.getByText("The key's numbers are an example, not a count of anything.")).toBeInTheDocument();
  });

  it("lists grid-location offsets as locations, not elevations, with the location copyable as printed", () => {
    renderOsse();
    expect(screen.getByText(/Bracketed values inside grid locations are offsets of that grid, not elevations/)).toBeInTheDocument();
    expect(screen.getByText("C.1(-6\")-7.3")).toBeInTheDocument();
    expect(screen.getByLabelText("minus 6 inches")).toHaveTextContent("−6″");
    expect(screen.getByText(/Legend examples, not project values/)).toBeInTheDocument();
  });

  it("calls a parking C1 precast concrete with its printed size, and other concrete marks nothing", () => {
    renderOsse();
    fireEvent.click(screen.getByRole("button", { name: /Parking and concrete column schedules/ }));
    const c1 = within(screen.getByText("A-1").closest("tr"));
    expect(c1.getByText("Precast concrete · C1")).toBeInTheDocument();
    expect(c1.getByText("24″ × 24″")).toBeInTheDocument();
    const rc1 = within(screen.getByText("RA.1-R13").closest("tr"));
    expect(rc1.getByText("RC1 - 24\" x 24\"")).toBeInTheDocument();
    expect(rc1.queryByText(/Precast/)).not.toBeInTheDocument();
    expect(screen.queryByText(/printed size, not a catalog section/)).not.toBeInTheDocument();
  });

  it("keeps vertical and horizontal reinforcement as two values even when equal", () => {
    renderOsse();
    fireEvent.click(screen.getByRole("button", { name: /Other non-steel definitions/ }));
    const w1 = within(screen.getByText("W1").closest("tr"));
    expect(w1.getByText("Reinforcement · Vertical")).toBeInTheDocument();
    expect(w1.getByText("Reinforcement · Horizontal")).toBeInTheDocument();
    expect(w1.getAllByText("#4@12\" O.C. E.F.")).toHaveLength(2);
  });

  it("counts schedule entries, never installed columns, and shows no model identifiers", () => {
    renderOsse();
    expect(screen.getByText(/1 schedule entry/)).toBeInTheDocument();
    expect(screen.queryByText(/installed columns?:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\b(?:C1|X1|K1)\b:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/fact id/i)).not.toBeInTheDocument();
  });

  it("shows source-backed beam coverage and merged paths while keeping blank reinforcement blank", () => {
    const profile = osseProfile();
    const cells = [
      { heading: "WIDTH", path: ["SIZE", "WIDTH"], text: '16"' },
      { heading: "DEPTH", path: ["SIZE", "DEPTH"], text: '32"' },
      { heading: "L.E. BARS", path: ["REINFORCEMENT", "TOP BARS", "L.E. BARS"], text: "" },
      { heading: "F.L. BARS", path: ["REINFORCEMENT", "TOP BARS", "F.L. BARS"], text: "4-#6" },
      { heading: "R.E. BARS", path: ["REINFORCEMENT", "STIRRUPS", "R.E. BARS"], text: "" },
      { heading: "REMARKS", path: ["REMARKS"], text: "" },
    ];
    profile.drawing_intelligence.definitions = [{ ...profile.drawing_intelligence.definitions[0],
      mark: "CB16X32", schedule_title: "CONCRETE BEAM SCHEDULE", cells }];
    profile.drawing_intelligence.supporting_schedules = [{ title: "CONCRETE BEAM SCHEDULE", kind: "beam",
      page: 25, sheet: "S601", printed_rows: 6, extracted_rows: 1,
      unread_rows: ["16RB32", "20LB44", "26LB32", "32RB24", "40IT52"].map((printed_mark) => ({
        printed_mark, cells: cells.map((c) => ({ ...c, text: "" })), bbox: [1, 2, 3, 4] })),
    }];
    render(<DrawingSummaryPanel profile={profile} />);
    fireEvent.click(screen.getByRole("button", { name: /Concrete beams/ }));
    expect(screen.getByText(/6 printed rows identified · 1 with interpreted details/)).toBeInTheDocument();
    expect(screen.getByText(/5 additional printed rows are available for review/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Top Bars" })).toHaveAttribute("colspan", "2");
    expect(screen.getByRole("columnheader", { name: "Stirrups" })).toHaveAttribute("colspan", "1");
    const row = within(screen.getByText("CB16X32").closest("tr")).getAllByRole("cell");
    expect(row[3]).toBeEmptyDOMElement();
    expect(row[4]).toHaveTextContent("4-#6");
    expect(row[5]).toBeEmptyDOMElement();
  });

  it("keeps unresolved slab and deck offsets distinct in the attention section", () => {
    const profile = osseProfile();
    profile.drawing_intelligence.levels.plan_elevations = [
      { inches: 5.25, relative_to: "top of slab", sheet: "S122", page: 10, name: "T.O. SLAB LEVEL 2" },
      { inches: 3, relative_to: "top of deck", sheet: "S123", page: 11, name: "T.O. ROOF" },
    ].map((e) => ({ ...e, status: "unresolved", surface: "top of steel", offset: { inches: e.inches },
      levels: [{ name: e.name }], rule: `FROM ${e.relative_to}`,
      source: { page: e.page, sheet: e.sheet, text: `FROM ${e.relative_to}` } }));
    render(<DrawingSummaryPanel profile={profile} />);
    const attention = within(screen.getByText("Items needing attention").closest("section"));
    expect(attention.getByText("5¼″")).toBeInTheDocument();
    expect(attention.getByText("3″")).toBeInTheDocument();
    expect(attention.getByText("Whether it is above or below the top of slab")).toBeInTheDocument();
    expect(attention.getByText("Whether it is above or below the top of deck")).toBeInTheDocument();
    expect(attention.getByText("Level 2 · S122")).toBeInTheDocument();
    expect(attention.getByText("Roof · S123")).toBeInTheDocument();
  });
});
