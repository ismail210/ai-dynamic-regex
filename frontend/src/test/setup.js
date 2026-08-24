import "@testing-library/jest-dom/vitest";

// jsdom does not implement scrollIntoView at all (not even a no-op) --
// anything that scrolls a selected row/element into view (e.g.
// SectionResultsList's deep-link auto-scroll) throws without this stub.
// Individual tests may still override it with a vi.fn() to assert calls.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
