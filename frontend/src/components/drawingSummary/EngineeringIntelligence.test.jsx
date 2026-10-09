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
    expect(screen.queryByRole("button", { name: /Show \d+ more/ })).not.toBeInTheDocument();
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
            {
              reference_text: "2/S-401", source_sheet: "S-101A", source_page: 4, target_sheet: "S-401",
              target_number: "2", target_view_type: "elevation", status: "target_view_found",
              bbox: [1, 2, 3, 4], target_bbox: [9, 10, 11, 12],
            },
          ],
          levels: { building_levels: [] },
          warnings: [],
        }}
      />,
    );
    expect(screen.getByText("S102A · N/S502 · section N is printed on S502.")).toBeInTheDocument();
    expect(screen.getByText("S-101A · 2/S-401 · elevation 2 is printed on S-401.")).toBeInTheDocument();
    expect(screen.getByText("S102D · H/S302 · S302 is in the set. View H is not a printed title.")).toBeInTheDocument();
    expect(screen.getByText("4/S-401 · no sheet with that id.")).toBeInTheDocument();
    expect(screen.getByText("S101 · 6/S-301 · more than one printed view uses 6.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /H\/S302/ })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /4\/S-401/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "View S502 · PDF p. 21 for N/S502" }));
    expect(onView).toHaveBeenCalledWith(expect.objectContaining({ page: 21, bbox: [5, 6, 7, 8] }));
  });

  it("reveals references twelve at a time and collapses them without moving the view list", () => {
    const onView = vi.fn();
    const references = Array.from({ length: 66 }, (_, index) => ({
      reference_text: `C${index + 1}/S-100`,
      source_sheet: "S101",
      source_page: 1,
      target_sheet: "S-100",
      target_number: "1",
      target_page: 2,
      status: index === 14 ? "target_view_found" : "target_sheet_only",
      bbox: [1, 2, 3, 4],
      target_bbox: index === 14 ? [9, 8, 7, 6] : undefined,
    }));
    const views = Array.from({ length: 15 }, (_, index) => ({
      view_id: `V${index + 1}`,
      status: "read",
      sheet_id: "S-100",
      pdf_page: 2,
      view_title: `DETAIL ${index + 1}`,
      view_number: String(index + 1),
      bbox: [1, 2, 3, 4],
    }));
    render(<EngineeringIntelligence onView={onView} data={{ views, references, levels: { building_levels: [] }, warnings: [] }} />);

    expect(screen.getByText("Showing 12 of 66 references")).toBeInTheDocument();
    expect(screen.getByText("Showing 12 of 15 views")).toBeInTheDocument();
    expect(screen.getByText(/C1\/S-100/)).toBeInTheDocument();
    expect(screen.getByText(/C12\/S-100/)).toBeInTheDocument();
    expect(screen.queryByText(/C13\/S-100/)).not.toBeInTheDocument();
    expect(screen.queryByText(/DETAIL 13/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show 12 more references" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show the first 12 references" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show 12 more references" }));
    expect(screen.getByText("Showing 24 of 66 references")).toBeInTheDocument();
    expect(screen.getByText(/C13\/S-100/)).toBeInTheDocument();
    expect(screen.getByText(/C24\/S-100/)).toBeInTheDocument();
    expect(screen.queryByText(/C25\/S-100/)).not.toBeInTheDocument();
    expect(screen.queryByText(/DETAIL 13/)).not.toBeInTheDocument();
    expect(screen.getByText("Unresolved targets stay unresolved.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View S-100 · PDF p. 2 for C15/S-100" }));
    expect(onView).toHaveBeenCalledWith(expect.objectContaining({ page: 2, bbox: [9, 8, 7, 6] }));
    expect(screen.getAllByRole("button", { name: /for C1\/S-100/ })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Show 12 more references" }));
    fireEvent.click(screen.getByRole("button", { name: "Show 12 more references" }));
    fireEvent.click(screen.getByRole("button", { name: "Show 12 more references" }));
    expect(screen.getByText("Showing 60 of 66 references")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show 6 more references" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show 6 more references" }));
    expect(screen.getByText("Showing all 66 references")).toBeInTheDocument();
    expect(screen.getByText(/C66\/S-100/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show \d+ more references/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show the first 12 references" }));
    expect(screen.getByText("Showing 12 of 66 references")).toBeInTheDocument();
    expect(screen.queryByText(/C13\/S-100/)).not.toBeInTheDocument();
    expect(screen.getByText("Showing 12 of 15 views")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show 3 more views" }));
    expect(screen.getByText("Showing all 15 views")).toBeInTheDocument();
    expect(screen.getByText(/DETAIL 13/)).toBeInTheDocument();
    expect(screen.getByText("Showing 12 of 66 references")).toBeInTheDocument();
    expect(screen.queryByText(/C13\/S-100/)).not.toBeInTheDocument();
  });

  it("does not offer expansion for a short list and still starts a long list at 12", () => {
    const { rerender } = render(
      <EngineeringIntelligence
        data={{
          views: [{ view_id: "V1", status: "read", sheet_id: "S1", pdf_page: 1, view_title: "PLAN", bbox: [1, 2, 3, 4] }],
          references: [{ reference_text: "1/S-1", source_page: 1, status: "target_sheet_only", bbox: [1, 2, 3, 4] }],
          levels: { building_levels: [] },
          warnings: [],
        }}
      />,
    );
    expect(screen.queryByRole("button", { name: /Show \d+ more/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Showing /)).not.toBeInTheDocument();

    rerender(
      <EngineeringIntelligence
        data={{
          views: [],
          references: Array.from({ length: 12 }, (_, index) => ({
            reference_text: `R${index + 1}`, source_page: 1, status: "target_sheet_only", bbox: [1, 2, 3, 4],
          })),
          levels: { building_levels: [] },
          warnings: [],
        }}
      />,
    );
    expect(screen.getByText(/R12/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show \d+ more/ })).not.toBeInTheDocument();

    rerender(
      <EngineeringIntelligence
        data={{
          views: [],
          references: Array.from({ length: 396 }, (_, index) => ({
            reference_text: `P${index + 1}/S-500`, source_page: 1, status: "target_sheet_only", bbox: [1, 2, 3, 4],
          })),
          levels: { building_levels: [] },
          warnings: [],
        }}
      />,
    );
    expect(screen.getByText("Showing 12 of 396 references")).toBeInTheDocument();
    expect(screen.queryByText(/P13\/S-500/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show 12 more references" })).toBeInTheDocument();
  });
});
