import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PageHeader from "./PageHeader";

function invalidDomPropWarnings(spy) {
  return spy.mock.calls.filter(
    ([message]) =>
      typeof message === "string" && message.includes("does not recognize the"),
  );
}

describe("PageHeader", () => {
  let errorSpy;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  it("renders title, subtitle, and actions without forwarding invalid DOM props", () => {
    render(
      <PageHeader
        title="Explainable predictions"
        subtitle="Exact sections selected from text, OCR, geometry, graph, and engineering evidence."
        actions={<button type="button">Download</button>}
      />,
    );
    expect(invalidDomPropWarnings(errorSpy)).toHaveLength(0);
  });

  it("renders with no subtitle or actions without forwarding invalid DOM props", () => {
    render(<PageHeader title="Dashboard" />);
    expect(invalidDomPropWarnings(errorSpy)).toHaveLength(0);
  });
});
