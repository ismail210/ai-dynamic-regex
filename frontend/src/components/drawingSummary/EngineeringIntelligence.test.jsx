import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
    expect(screen.getByText("S101A · N/S401 · S401 is in the set. View N is not a printed title.")).toBeInTheDocument();
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
    expect(screen.getByText(/1 grid labels sit on a drawn grid line/)).toBeInTheDocument();
    expect(screen.getByText(/not a column, a beam, or a quantity/)).toBeInTheDocument();
    expect(screen.getByText(/C1 · nearest grid crossing 1\/A/)).toBeInTheDocument();
    expect(screen.getByText("closest crossing")).toBeInTheDocument();
    expect(screen.getByText("no crossing nearby")).toBeInTheDocument();
    expect(screen.queryByText("confirmed")).not.toBeInTheDocument();
    expect(screen.queryByText(/marks allocated/)).not.toBeInTheDocument();
  });

  it("opens the printed view and does not offer a target for a sheet-only reference", () => {
    const onView = vi.fn();
    render(
      <EngineeringIntelligence
        onView={onView}
        data={{
          views: [],
          references: [
            {
              reference_text: "N/S502", source_sheet: "S102A", source_page: 7, target_sheet: "S502",
              target_number: "N", target_page: 21, target_view_type: "section", status: "target_view_found",
              bbox: [1, 2, 3, 4], target_bbox: [5, 6, 7, 8],
            },
            {
              reference_text: "H/S302", source_sheet: "S102D", source_page: 10, target_sheet: "S302",
              target_number: "H", status: "target_sheet_only", bbox: [1, 2, 3, 4],
            },
            { reference_text: "4/S-401", source_page: 15, status: "target_missing", bbox: [1, 2, 3, 4] },
            {
              reference_text: "6/S-301", source_sheet: "S101", source_page: 4, target_sheet: "S-301",
              target_number: "6", status: "ambiguous", bbox: [1, 2, 3, 4],
            },
          ],
          levels: { building_levels: [] },
          warnings: [],
        }}
      />,
    );
    expect(screen.getByText("S102A · N/S502 · section N is printed on S502.")).toBeInTheDocument();
    expect(screen.getByText("S102D · H/S302 · S302 is in the set. View H is not a printed title.")).toBeInTheDocument();
    expect(screen.getByText("4/S-401 · no sheet with that id.")).toBeInTheDocument();
    expect(screen.getByText("S101 · 6/S-301 · more than one printed view uses 6.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /H\/S302/ })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /4\/S-401/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "View S502 · PDF p. 21 for N/S502" }));
    expect(onView).toHaveBeenCalledWith(expect.objectContaining({ page: 21, bbox: [5, 6, 7, 8] }));
  });
});
