import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SheetIndex from "./SheetIndex";

const page = (overrides) => ({
  page: 1,
  sheet_id: "S-001",
  sheet_id_status: "read",
  sheet_title: "GENERAL NOTES",
  title_status: "read",
  sheet_role: "general_notes",
  sheet_role_label: "General notes",
  classification_status: "read",
  issue: "65% DESIGN DEVELOPMENT",
  issue_status: "read",
  issue_date: "28 JANUARY 2025",
  scale: "As indicated",
  scale_status: "read",
  revision: { status: "read", rows: [{ number: "", description: "FTG PERMIT", date: "12/11/2024" }] },
  source_bbox: [1, 2, 3, 4],
  ...overrides,
});

describe("SheetIndex", () => {
  it("keeps the printed sheet id, including a suffix, and does not treat a revision as the issue", () => {
    render(
      <SheetIndex
        index={{
          pages: [
            page({ page: 10, sheet_id: "S-122-O", sheet_title: "OSSE FACILITY SECOND FLOOR PLAN",
              sheet_role: "framing_plan", sheet_role_label: "Floor plan" }),
            page({}),
          ],
        }}
      />,
    );
    expect(screen.getByText("S-122-O")).toBeInTheDocument();
    expect(screen.getByText(/Issue: 65% DESIGN DEVELOPMENT/)).toBeInTheDocument();
    expect(screen.getAllByText(/FTG PERMIT/)).toHaveLength(2);
    expect(screen.queryByText(/Issue: FTG PERMIT/)).not.toBeInTheDocument();
  });

  it("puts a title that names two drawing types under Review", () => {
    render(
      <SheetIndex
        index={{
          pages: [
            page({
              page: 8,
              sheet_id: "S-104-O",
              sheet_title: "NORTH STAIR & ELEVATOR PLANS AND ELEVATIONS",
              sheet_role: null,
              sheet_role_label: "Review",
              classification_status: "review",
              classification_evidence: "title names more than one sheet type",
            }),
          ],
        }}
      />,
    );
    expect(screen.getByText("Review · 1")).toBeInTheDocument();
    expect(screen.getByText("NORTH STAIR & ELEVATOR PLANS AND ELEVATIONS")).toBeInTheDocument();
  });

  it("opens the title-block box for that page", () => {
    const onView = vi.fn();
    render(<SheetIndex index={{ pages: [page({ page: 4, sheet_id: "S-101A" })] }} onView={onView} />);
    screen.getByRole("button", { name: /View/ }).click();
    expect(onView).toHaveBeenCalledWith(expect.objectContaining({
      page: 4, bbox: [1, 2, 3, 4], sheet: "S-101A",
    }));
  });
});
