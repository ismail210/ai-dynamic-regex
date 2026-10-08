import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchPageCrop, locateOnPlan } from "../api/client";
import DrawingSummaryPanel from "./DrawingSummaryPanel";
import { LocationProvider, PlanPreview } from "./drawingSummary/locate";
import { SummaryReport } from "./drawingSummary/report";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal()),
  locateOnPlan: vi.fn(() => Promise.resolve({ status: "plan_not_found", views: [], other_scope_views: [] })),
  getColumnTrace: vi.fn(),
  fetchPageCrop: vi.fn(() => Promise.resolve(new Blob(["png"], { type: "image/png" }))),
}));

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
  it("reads in the estimator's order: scope, attention, columns, levels, notation, supporting", () => {
    renderOsse();
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    const order = ["Project and scope", "Items needing attention", "Columns, plates and plan locations",
      "Levels and supported vertical extents", "Drawing notation", "Supporting schedules and evidence"];
    expect(order.every((h) => headings.includes(h))).toBe(true);
    for (let i = 1; i < order.length; i += 1) expect(headings.indexOf(order[i])).toBeGreaterThan(headings.indexOf(order[i - 1]));
    // Building and parking column groups are both discoverable in the columns section.
    const columns = within(screen.getByText("Columns, plates and plan locations").closest("section"));
    expect(columns.getByText("OSSE BUILDING - GCS")).toBeInTheDocument();
    expect(columns.getByText("OSSE PARKING - GCS")).toBeInTheDocument();
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
    const c1 = within(screen.getByText("A-1").closest("tr"));
    expect(c1.getByText("Precast concrete · C1")).toBeInTheDocument();
    // A concrete column's size is its section, never a plate's W × L × T.
    expect(c1.getByText("24″ × 24″ column section")).toBeInTheDocument();
    const parking = screen.getByRole("table", { name: "OSSE PARKING - GCS columns" });
    expect(within(parking).queryByRole("columnheader", { name: /W × L × T/ })).not.toBeInTheDocument();
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
    expect(screen.getAllByText(/1 printed entry/).length).toBeGreaterThan(0);
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
      completeness: { printed_rows: 6, properties_read: 1, linked: 0, references: 0 },
      unread_rows: ["16RB32", "20LB44", "26LB32", "32RB24", "40IT52"].map((printed_mark) => ({
        printed_mark, cells: cells.map((c) => ({ ...c, text: "" })), bbox: [1, 2, 3, 4] })),
    }];
    render(<DrawingSummaryPanel profile={profile} />);
    fireEvent.click(screen.getByRole("button", { name: /^Concrete beams/ }));
    expect(screen.getByText(/6 printed rows · 1 row with properties read/)).toBeInTheDocument();
    expect(screen.getByText(/5 printed rows are not used as takeoff label/)).toBeInTheDocument();
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

// ---------------------------------------------------------------------------
// Locate on plan, table-only locations, the multi-source level review,
// honest coverage counts and the printable report.
// ---------------------------------------------------------------------------

const locateResult = {
  status: "column_symbol", location: "C.8-8.9", default: 0, other_scope_views: [],
  views: [
    { page: 9, sheet: "S121", view_title: null, scope: { status: "supported_by_datum", note: "Datum ties the view." },
      state: "column_symbol", target_bbox: [100, 200, 110, 210], nearby_text: [{ text: "P1", bbox: [1, 1, 2, 2] }] },
    { page: 10, sheet: "S122", view_title: null, scope: { status: "consistent_by_sheet_family", note: "Same family." },
      state: "intersection_only", target_bbox: [300, 400, 306, 406], nearby_text: [] },
  ],
};

function withReview(profile) {
  const di = profile.drawing_intelligence;
  const level2 = di.levels.schedule_levels.find((l) => l.name === "T.O. SLAB LEVEL 2");
  level2.review = {
    level: level2.name, schedule_id: "S2", plan_page: 10,
    headline: "Level 2 elevation requires review: the general datum note states 55'-2\", while the column schedule, a local slab annotation and a section state 55'-10\". Their applicable areas have not been fully reconciled.",
    items: [
      { role: "schedule", label: "Column schedule · OSSE BUILDING - GCS", value: "55' - 10\"", scope: "the schedule's level line",
        source: { page: 26, sheet: "S602", bbox: [160, 1533, 245, 1571] } },
      { role: "general_note", label: "General datum note · S122", value: "55' - 2\"", scope: "the sheet's datum statement (no area named)",
        source: { page: 10, sheet: "S122", bbox: [2555, 371, 2876, 555] } },
      { role: "local_annotation", label: "Local plan annotation · S122", value: "55' - 10\"",
        scope: "printed in a box at one place on the plan, beside slab tag S5.25",
        tag: { mark: "S5.25", material: "composite: concrete on metal deck",
          definition: { table: "SLAB/DECK SCHEDULE", page: 25, sheet: "S601", bbox: [1, 2, 3, 4],
          cells: [{ heading: "TOTAL DEPTH", path: ["TOTAL DEPTH"], text: "5 1/4\"" }] } },
        source: { page: 10, sheet: "S122", bbox: [1757, 1172, 1797, 1185] } },
      { role: "section", label: "Section 1 · S421", value: "55' - 10\"", name: "T.O. SLAB LEVEL 2", scope: "names this level",
        source: { page: 17, sheet: "S421", bbox: [550, 287, 636, 307] } },
    ],
    checks: [
      { slab: "55'-2\"", offset_inches: 5.25, result: "54'-8 3/4\"", printed: [], rule_source: { page: 10, sheet: "S122", text: "TOP OF STEEL ..." } },
      { slab: "55'-10\"", offset_inches: 5.25, result: "55'-4 3/4\"",
        printed: [{ page: 12, sheet: "S221", bbox: [1, 1, 2, 2], name: "T.O. STEEL LEVEL 2" }] },
    ],
    explanations: [
      { id: "surfaces", label: "Different physical surfaces", status: "not_supported", basis: "All name the top of slab." },
      { id: "inconsistent", label: "An inconsistent annotation", status: "unresolved", basis: "Not confirmed." },
    ],
    related: [{ value: "55' - 2\"", inches: 662, source: { page: 7, sheet: "S103", bbox: [885, 1390, 914, 1399] },
      separate: true, printed_count: 7, tag: { mark: "G2.5", material: "steel grating",
        definition: { table: "SLAB/DECK SCHEDULE", page: 25, sheet: "S601", bbox: [5, 6, 7, 8] } },
      result: "54'-11 1/2\"",
      note: "Printed on S103 beside G2.5 (steel grating, total depth 2 1/2\"): 55'-2\" − 2 1/2\" = 54'-11 1/2\", the bracketed member elevation printed 7 times around it. A separate condition from the slab statements above; it does not resolve them." }],
  };
  di.level_reviews = [level2.review];
  return profile;
}

function withTableOnly(profile) {
  const column = profile.drawing_intelligence.column_schedule;
  column.schedules.push({ id: "L1", name: "BASE PLATE SCHEDULE — locations not in a column schedule", layout: "location_table",
    source: "location_table", key_role: "location", pages: [25], sheets: ["S601"], page: 25, sheet: "S601", bbox: [1, 2, 3, 4],
    block_count: 1, levels: [], notes: [], hidden_text: [], scope_schedule_id: "S2",
    scope_basis: "22 of its 29 rows are locations of that schedule", material_group: "steel", entry_count: 1,
    coverage: { entries: 1, plates_linked: 1 } });
  column.entries.push({ id: "L1-1", schedule_id: "L1", key_role: "location", assignment_only: true, page: 25, sheet: "S601",
    bbox: [1134, 1360, 1353, 1372], mark: null, location_text: "C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")",
    locations: [{ raw: "C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")", status: "parsed",
      grids: [{ label: "C.4", offset: { raw: "1' - 7 3/8\"" } }, { label: "7.5", offset: { raw: "-2' - 4 1/2\"" } }] }],
    listed_location_count: 1, sections: [{ designation: "HSS16X4X5/8", printed: "HSS16X4X5/8" }],
    plate: { status: "resolved", printed: "CBP-3", type: "base plate",
      dimensions: [{ label: "width", raw: "16\"" }, { label: "length", raw: "18\"" }, { label: "thickness", raw: "1 1/4\"" }], via: [] },
    other_plates: [], notes: [], conflicts: [], hidden_text: [], extent: null, level_difference: null,
    extent_note: "The table assigns a section and base plate only; it gives no levels, so the column's vertical extent is not established.",
    material: { status: "catalog section", material: "steel" } });
  column.location_tables = [{ title: "BASE PLATE SCHEDULE", page: 25, sheet: "S601", rows: 29, matched: { S2: 22 },
    assignment_only: 7, assignment_only_schedule_id: "L1" }];
  column.plate_tables = [{ kind: "base plate", title: "BASE PLATE TYPE SCHEDULE", page: 25, sheet: "S601", marks: ["CBP-2", "CBP-7"],
    unused_marks: ["CBP-7"], rows: [{ mark: "CBP-2", dimensions: [{ label: "width", raw: "12\"" }] }, { mark: "CBP-7", dimensions: [] }] }];
  return profile;
}

describe("Drawing Summary — OSSE locations, coverage and review", () => {
  beforeEach(() => {
    locateOnPlan.mockReset();
    locateOnPlan.mockResolvedValue(locateResult);
  });

  it("locates a grid intersection on the default plan, switches plans and returns focus", async () => {
    renderOsse("doc_locate");
    const button = screen.getByRole("button", { name: "Locate C.8-8.9 on plan" });
    button.focus();
    fireEvent.click(button);
    expect(await screen.findByText("Column symbol identified")).toBeInTheDocument();
    expect(locateOnPlan).toHaveBeenCalledWith("doc_locate", "C.8-8.9", "S2");
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-page", "9");
    expect(screen.getByText(/Printed at the location: P1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "S122" }));
    expect(screen.getByText("Grid intersection identified; column not confirmed")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-viewer")).toHaveAttribute("data-page", "10");
    fireEvent.click(screen.getByRole("button", { name: "Close plan view" }));
    await waitFor(() => expect(button).toHaveFocus());
  });

  it("shows a plan preview and the plan views as sources in a column's details", async () => {
    renderOsse("doc_preview");
    fireEvent.click(screen.getByRole("button", { name: "Show details for C.8-8.9" }));
    URL.createObjectURL = vi.fn(() => "blob:plan-preview");
    URL.revokeObjectURL = vi.fn();
    const preview = await screen.findByRole("img", { name: "Plan S121 around C.8-8.9" });
    expect(preview.getAttribute("src")).toBe("blob:plan-preview");
    expect(fetchPageCrop).toHaveBeenCalledWith("doc_preview", 9, expect.any(Array), 360);
    const chain = screen.getByRole("list", { name: /Evidence chain/ });
    expect(within(chain).getByRole("button", { name: /for C.8-8.9 on S121/ })).toHaveTextContent("Plan S121");
  });

  it("lists table-only locations apart, with their source, offsets on both axes and no levels", () => {
    render(<DrawingSummaryPanel profile={withTableOnly(osseProfile())} documentId="doc_osse" />);
    const block = within(document.getElementById("summary-schedule-L1"));
    expect(block.getByText(/listed only in this table/)).toBeInTheDocument();
    expect(block.getByText("C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")")).toBeInTheDocument();
    expect(block.getByText("table only · no levels")).toBeInTheDocument();
    fireEvent.click(block.getByRole("button", { name: /Show details for C.4/ }));
    expect(block.getByText(/1' - 7 3\/8" from grid C.4, -2' - 4 1\/2" from grid 7.5/)).toBeInTheDocument();
    expect(block.getByText(/vertical extent is not established/)).toBeInTheDocument();
    expect(block.queryByText(/On the framing plans \(pilot\)/)).not.toBeInTheDocument();
    // The building schedule keeps its own rows; the table-only post is not one of them.
    expect(within(screen.getByRole("table", { name: "OSSE BUILDING - GCS columns" })).queryByText(/C\.4\(/)).not.toBeInTheDocument();
  });

  it("lists every schedule in a directory with printed counts, table matches and unused plate marks", () => {
    render(<DrawingSummaryPanel profile={withTableOnly(osseProfile())} documentId="doc_osse" />);
    const directory = within(screen.getByRole("table", { name: "Schedules read from this drawing set" }));
    expect(directory.getByText("OSSE PARKING - GCS")).toBeInTheDocument();
    expect(directory.getByText("29 rows")).toBeInTheDocument();
    expect(directory.getByText("22 in OSSE BUILDING - GCS · 7 in no column schedule")).toBeInTheDocument();
    expect(directory.getByText("CBP-7 not assigned to a listed location")).toBeInTheDocument();
  });

  it("shows a long schedule's preview honestly and searches the rows it hides", () => {
    const profile = osseProfile();
    const column = profile.drawing_intelligence.column_schedule;
    const template = column.entries[0];
    column.entries = [...Array.from({ length: 40 }, (_, i) => ({
      ...template, id: `S1-${i + 1}`, location_text: `E-${i + 1}`,
      locations: [{ raw: `E-${i + 1}`, status: "parsed", grids: [] }] })), column.entries[2]];
    render(<DrawingSummaryPanel profile={profile} documentId="doc_osse" />);
    expect(screen.getByText("Showing 8 of 40 printed entries — the search covers all of them")).toBeInTheDocument();
    expect(screen.queryByText("E-40")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Find a location, section or plate"), { target: { value: "e - 40" } });
    expect(screen.getByText("E-40")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 of 41 printed entries match (1 in OSSE PARKING - GCS)");
  });

  it("reviews Level 2 with every printed source, a check of printed numbers and unconfirmed explanations", async () => {
    render(<DrawingSummaryPanel profile={withReview(osseProfile())} documentId="doc_osse" />);
    const attention = within(screen.getByText("Items needing attention").closest("section"));
    expect(attention.getByText(/Level 2 elevation requires review/)).toBeInTheDocument();
    const evidence = within(attention.getByRole("table", { name: /Printed evidence for T.O. SLAB LEVEL 2/ }));
    expect(evidence.getByText("General datum note")).toBeInTheDocument();
    expect(evidence.getByText("Local plan annotation")).toBeInTheDocument();
    expect(evidence.getByText(/S5.25 \(composite: concrete on metal deck\) per slab\/deck schedule: total depth 5¼″/)).toBeInTheDocument();
    expect(attention.getByText(/beside G2.5 \(steel grating, total depth 2½″\): 55′-2″ − 2½″ = 54′-11½″/)).toBeInTheDocument();
    expect(attention.getByRole("button", { name: /S103 · PDF p. 7 for 55' - 2" beside G2.5/ })).toBeInTheDocument();
    expect(evidence.getByText("Section")).toBeInTheDocument();
    expect(attention.getByText(/not found among the extracted level markers/)).toBeInTheDocument();
    expect(attention.getByText(/printed as T.O. STEEL LEVEL 2 on S221/)).toBeInTheDocument();
    expect(attention.getByText("Not supported by printed evidence")).toBeInTheDocument();
    expect(attention.getByText("Unresolved")).toBeInTheDocument();
    fireEvent.click(evidence.getByRole("button", { name: /S421 · PDF p. 17 for Section 1/ }));
    expect(await screen.findByTestId("pdf-viewer")).toHaveAttribute("data-page", "17");
  });

  it("keeps a pier label and the pier schedule apart when their sizes differ", () => {
    const profile = osseProfile();
    const steel = profile.drawing_intelligence.column_schedule.entries[2];
    steel.supports = [{ printed: "P1 - 18 x 20", mark: "P1", page: 26, sheet: "S602", bbox: [1, 2, 3, 4],
      definition: { schedule_title: "PIER SCHEDULE", mark: "P1", page: 25, sheet: "S601", bbox: [5, 6, 7, 8], sizes: "differ",
        cells: [{ heading: "WIDTH", path: ["SIZE", "WIDTH"], text: "18\"" }, { heading: "LENGTH", path: ["SIZE", "LENGTH"], text: "24\"" }] } }];
    render(<DrawingSummaryPanel profile={profile} documentId="doc_osse" />);
    fireEvent.click(screen.getByRole("button", { name: "Show details for C.8-8.9" }));
    expect(screen.getByText("P1 - 18 x 20")).toBeInTheDocument();
    expect(screen.getByText(/P1 in the Pier Schedule: width 18" · length 24" — sizes differ from the label; both are kept/))
      .toBeInTheDocument();
  });

  it("prints every selected record: the full report lists all rows, the concise one says what it leaves out", () => {
    const profile = withTableOnly(withReview(osseProfile()));
    const di = profile.drawing_intelligence;
    const { unmount } = render(<SummaryReport di={di} document={{ source_file: "OSSE - ST.pdf" }} mode="concise" />);
    expect(screen.getByText(/2 entries of OSSE PARKING - GCS are summarised by label, not listed/)).toBeInTheDocument();
    expect(screen.getByText("C.8-8.9")).toBeInTheDocument();
    expect(screen.getByText("C.4(1' - 7 3/8\")-7.5(-2' - 4 1/2\")")).toBeInTheDocument();
    expect(screen.getByText(/Level 2 elevation requires review/)).toBeInTheDocument();
    expect(screen.queryByText("A-1")).not.toBeInTheDocument();
    unmount();
    render(<SummaryReport di={di} document={{ source_file: "OSSE - ST.pdf" }} mode="full" />);
    expect(screen.getByText("A-1")).toBeInTheDocument();
    expect(screen.getByText("RA.1-R13")).toBeInTheDocument();
    expect(screen.getByText(/Every record the summary holds is listed/)).toBeInTheDocument();
    expect(screen.getAllByText("12″ × 18″ × ¾″").length).toBeGreaterThan(0);
    // A concrete column's size is never under the plate's W × L × T.
    expect(screen.getByText(/precast concrete · C1 · 24″ × 24″ column section/)).toBeInTheDocument();
  });

  it("keeps plan locations on demand, tells not looked up from not found and names each value's source", async () => {
    locateOnPlan.mockReset();
    locateOnPlan.mockImplementation((_doc, location) => Promise.resolve(location === "C.8-8.9"
      ? { status: "column_symbol", views: [{ page: 9, sheet: "S121", state: "column_symbol" }] }
      : { status: "plan_not_found", note: "No plan in the set prints both grid labels.", views: [] }));
    const profile = withTableOnly(withReview(osseProfile()));
    const steel = profile.drawing_intelligence.column_schedule.entries[2];
    steel.plate = { ...steel.plate, via: [{ kind: "location table", page: 25, sheet: "S601", title: "BASE PLATE SCHEDULE" }] };
    render(<SummaryReport di={profile.drawing_intelligence} document={{ document_id: "doc_report", source_file: "OSSE - ST.pdf" }}
      mode="concise" />);
    const row = within(screen.getByText("C.8-8.9").closest("tr"));
    expect(row.getByText("Not yet looked up")).toBeInTheDocument();
    expect(row.getByText(/Plate: S601 p. 25/)).toBeInTheDocument();
    expect(screen.getByText(/Plan locations of \d+ listed locations? \(not yet looked up/)).toBeInTheDocument();
    expect(locateOnPlan).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Look up plan locations/ }));
    expect(await row.findByText("S121 — Column symbol identified")).toBeInTheDocument();
    expect(await screen.findAllByText(/^Not found: No plan in the set prints both grid labels/)).not.toHaveLength(0);
    expect(locateOnPlan).toHaveBeenCalledWith("doc_report", "C.8-8.9", "S2");
    // The levels table lists every printed source the review holds, not one value per sheet.
    expect(screen.getByText(/general note 55′-2″ · S122; local annotation 55′-10″ · S122; Section 1 55′-10″ · S421/))
      .toBeInTheDocument();
  });
});


it("refreshes Locate after re-extracting the same document", async () => {
  locateOnPlan.mockReset();
  locateOnPlan.mockResolvedValue({ status: "plan_not_found", views: [] });
  const first = {};
  const preview = (profile) => <LocationProvider profile={profile}>
    <PlanPreview documentId="same-document" location="A-2" scheduleId="S1" />
  </LocationProvider>;
  const { rerender } = render(preview(first));
  await screen.findByText("Relevant plan not found");
  expect(locateOnPlan).toHaveBeenCalledTimes(1);
  rerender(preview(first));
  expect(locateOnPlan).toHaveBeenCalledTimes(1);
  locateOnPlan.mockResolvedValue({ status: "not_a_grid_location", views: [] });
  rerender(preview({}));
  await screen.findByText("Not a grid location");
  expect(locateOnPlan).toHaveBeenCalledTimes(2);
});


it("searches column sections and plate marks across schedule groups", () => {
  render(<DrawingSummaryPanel profile={osseProfile()} documentId="search-types" />);
  const search = screen.getByRole("textbox", { name: "Find a location, section or plate" });
  fireEvent.change(search, { target: { value: "W10X33" } });
  expect(screen.getByRole("button", { name: "Show details for C.8-8.9" })).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "CBP-2" } });
  expect(screen.getByRole("button", { name: "Show details for C.8-8.9" })).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "C1" } });
  expect(screen.queryByRole("button", { name: "Show details for C.8-8.9" })).not.toBeInTheDocument();
  expect(screen.getByRole("status")).not.toHaveTextContent("0 of");
});
