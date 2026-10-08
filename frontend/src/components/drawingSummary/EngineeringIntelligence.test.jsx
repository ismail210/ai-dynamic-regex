import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EngineeringIntelligence from "./EngineeringIntelligence";

describe("EngineeringIntelligence", () => {
  it("shows a level conflict and an unresolved reference without inventing the view", () => {
    render(
      <EngineeringIntelligence
        data={{
          views: [{ view_id: "V1", status: "read", sheet_id: "S401", pdf_page: 19, view_title: "DETAIL D", view_number: "D", bbox: [1, 2, 3, 4] }],
          references: [{
            reference_text: "N/S401", source_sheet: "S101A", source_page: 3, target_sheet: "S401",
            target_number: "N", status: "target_sheet_only", bbox: [4, 5, 6, 7],
          }],
          levels: { building_levels: [{
            name: "LEVEL 2", status: "conflict",
            sources: [{ sheet_id: "S-122-O", value: "55'-2\"" }, { sheet_id: "S-602-O", value: "55'-10\"" }],
          }] },
          warnings: [],
          grids: [{ grid_id: "A", status: "candidate" }],
        }}
      />,
    );
    expect(screen.getByText(/LEVEL 2/)).toBeInTheDocument();
    expect(screen.getByText("conflict")).toBeInTheDocument();
    expect(screen.getByText("target sheet only")).toBeInTheDocument();
    expect(screen.getByText(/DETAIL D/)).toBeInTheDocument();
    expect(screen.getByText(/not a grid/)).toBeInTheDocument();
  });

  it("shows a grid allocation without treating it as a quantity", () => {
    render(
      <EngineeringIntelligence
        data={{
          views: [],
          references: [],
          levels: { building_levels: [] },
          warnings: [],
          grids: [{ grid_id: "A@p1", label: "A", status: "confirmed" }],
          grid_diagnostics: {
            confirmed_grid_labels: 1,
            grid_intersections: 1,
            objects_allocated: 1,
            objects_ambiguous: 1,
            objects_unresolved: 1,
          },
          grid_allocations: [
            { mark: "C1", sheet_id: "S-101", pdf_page: 4, grid_location: "1/A", allocation_status: "confirmed", bbox: [1, 2, 3, 4] },
            { mark: "C2", sheet_id: "S-101", pdf_page: 4, grid_location: null, allocation_status: "unresolved", bbox: [1, 2, 3, 4] },
          ],
        }}
      />,
    );
    expect(screen.getByText(/1 grid labels are aligned/)).toBeInTheDocument();
    expect(screen.getByText(/C1 → 1\/A/)).toBeInTheDocument();
    expect(screen.getByText(/C2 → unresolved/)).toBeInTheDocument();
  });
});
