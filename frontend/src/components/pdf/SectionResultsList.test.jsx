import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SectionResultsList from "./SectionResultsList";

function hssResult(objectId, overrides = {}) {
  return {
    object_id: objectId,
    raw_text: "HSS8X8",
    original_token: "HSS8X8",
    section: "HSS8X8X1/2",
    family: "HSS",
    page_number: 7,
    bounding_box: [10, 20, 30, 40],
    canonical: {
      source_text: { raw: "HSS8X8", page_number: 7, bounding_box: [10, 20, 30, 40], available: true },
      prediction: { final_label: "HSS8X8X1/2" },
      comparison: { match_status: "exact_match" },
      needs_review: false,
    },
    ...overrides,
  };
}

describe("SectionResultsList row selection, filtering, and scroll-into-view", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("calls onSelect with the row's own key/result/location, not a text match", () => {
    const onSelect = vi.fn();
    const results = [hssResult("obj_a"), hssResult("obj_b")];
    render(<SectionResultsList results={results} onSelect={onSelect} />);

    const rows = screen.getAllByText(/HSS8X8X1\/2/);
    fireEvent.click(rows[1]);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].key).toBe("obj_b");
    expect(onSelect.mock.calls[0][0].result.object_id).toBe("obj_b");
  });

  it("scrolls the selected row into view within the list, not the page", () => {
    const results = Array.from({ length: 30 }, (_, i) => hssResult(`obj_${i}`));
    const { rerender } = render(
      <SectionResultsList results={results} selectedKey={null} onSelect={() => {}} />,
    );
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();

    rerender(
      <SectionResultsList results={results} selectedKey="obj_17" onSelect={() => {}} />,
    );

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ block: "center" }),
    );
  });

  it("clears an active filter that would otherwise hide the deep-linked selection", () => {
    const results = [
      hssResult("obj_a"),
      hssResult("obj_b", { section: "W16X26", family: "W", raw_text: "W16x26" }),
    ];
    const { rerender } = render(
      <SectionResultsList results={results} selectedKey={null} onSelect={() => {}} />,
    );

    // A prior search now hides obj_a.
    fireEvent.change(screen.getByPlaceholderText("Filter sections…"), {
      target: { value: "W16X26" },
    });
    expect(screen.getByText("1 of 2 sections")).toBeInTheDocument();
    expect(screen.queryByText(/HSS8X8X1\/2/)).not.toBeInTheDocument();

    // Deep-linking to obj_a (the hidden row) must reveal it, not fail silently.
    rerender(
      <SectionResultsList results={results} selectedKey="obj_a" onSelect={() => {}} />,
    );
    expect(screen.getByPlaceholderText("Filter sections…").value).toBe("");
    expect(screen.getByText(/HSS8X8X1\/2/)).toBeInTheDocument();
    expect(screen.getByText("2 of 2 sections")).toBeInTheDocument();
  });

  it("never confuses two rows sharing the same display text -- selecting one never marks the other selected", () => {
    const results = [hssResult("obj_a"), hssResult("obj_b")];
    const { rerender } = render(
      <SectionResultsList results={results} selectedKey="obj_a" onSelect={() => {}} />,
    );
    const buttons = screen.getAllByRole("button");
    // Two rows in the list (search field/list share role=button ancestry via ListItemButton).
    const rowButtons = buttons.filter((b) => b.textContent.includes("HSS8X8X1/2"));
    expect(rowButtons).toHaveLength(2);
    expect(rowButtons[0].className).toMatch(/Mui-selected/);
    expect(rowButtons[1].className).not.toMatch(/Mui-selected/);

    rerender(
      <SectionResultsList results={results} selectedKey="obj_b" onSelect={() => {}} />,
    );
    const buttonsAfter = screen
      .getAllByRole("button")
      .filter((b) => b.textContent.includes("HSS8X8X1/2"));
    expect(buttonsAfter[0].className).not.toMatch(/Mui-selected/);
    expect(buttonsAfter[1].className).toMatch(/Mui-selected/);
  });
});
