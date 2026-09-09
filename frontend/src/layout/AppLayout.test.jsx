import { render, screen, within } from "@testing-library/react";
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

  function renderLayout() {
    return render(
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
  }

  it("renders the sidebar and toolbar without forwarding invalid DOM props", () => {
    renderLayout();
    expect(invalidDomPropWarnings(errorSpy)).toHaveLength(0);
  });

  it("shows the consolidated workflow nav and drops the retired standalone pages", () => {
    renderLayout();
    const nav = screen.getByRole("navigation");
    for (const label of [
      "Dashboard",
      "Upload & Extract",
      "Drawing Summary",
      "Analysis & Results",
      "Drawing Review",
      "Validation",
      "Takeoff",
      "Settings",
    ]) {
      expect(within(nav).getByText(label)).toBeInTheDocument();
    }
    for (const label of [
      "Upload",
      "Extract",
      "Analyze",
      "Results",
      "Corrections",
      "Dataset",
      "Training",
      "Analytics",
    ]) {
      expect(within(nav).queryByText(label)).not.toBeInTheDocument();
    }
  });
});
