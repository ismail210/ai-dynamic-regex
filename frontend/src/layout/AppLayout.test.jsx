import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppLayout from "./AppLayout";
import { ThemeModeProvider } from "../context/ThemeContext";
import { AnalysisProvider } from "../context/AnalysisContext";

vi.mock("../api/client", () => ({
  getDocument: vi.fn(),
  extractDocument: vi.fn(),
  analyzeDocument: vi.fn(),
}));

function invalidDomPropWarnings(spy) {
  return spy.mock.calls.filter(
    ([message]) =>
      typeof message === "string" && message.includes("does not recognize the"),
  );
}

describe("AppLayout", () => {
  let errorSpy;

  beforeEach(() => {
    sessionStorage.clear();
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  it("renders the sidebar and toolbar without forwarding invalid DOM props", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ThemeModeProvider>
          <AnalysisProvider>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={<div>page content</div>} />
              </Route>
            </Routes>
          </AnalysisProvider>
        </ThemeModeProvider>
      </MemoryRouter>,
    );
    expect(invalidDomPropWarnings(errorSpy)).toHaveLength(0);
  });
});
