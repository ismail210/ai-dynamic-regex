import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnalysisProvider, useAnalysis } from "./AnalysisContext";

vi.mock("../api/client", () => ({
  getDocument: vi.fn(),
  extractDocument: vi.fn(),
  analyzeDocument: vi.fn(),
}));

import { analyzeDocument, extractDocument, getDocument } from "../api/client";

function Probe() {
  const { document, extraction, data, rehydrating, stage, startNewAnalysis, restoreNotice } =
    useAnalysis();
  return (
    <div>
      <span data-testid="stage">{stage}</span>
      <span data-testid="rehydrating">{String(rehydrating)}</span>
      <span data-testid="document-id">{document?.document_id || ""}</span>
      <span data-testid="extraction">{extraction ? "yes" : "no"}</span>
      <span data-testid="data">{data ? "yes" : "no"}</span>
      <span data-testid="restore-notice-kind">{restoreNotice?.kind || ""}</span>
      <span data-testid="restore-notice-message">{restoreNotice?.message || ""}</span>
      <button onClick={startNewAnalysis}>reset</button>
    </div>
  );
}

function notFoundError(detail) {
  const error = new Error(detail || "Not Found");
  error.response = { status: 404, data: { detail } };
  return error;
}

describe("AnalysisContext workflow persistence", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  it("starts empty with nothing persisted", async () => {
    render(
      <AnalysisProvider>
        <Probe />
      </AnalysisProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("rehydrating").textContent).toBe("false"));
    expect(screen.getByTestId("stage").textContent).toBe("empty");
    expect(getDocument).not.toHaveBeenCalled();
  });

  it("rehydrates an analyzed document from a persisted document id", async () => {
    sessionStorage.setItem(
      "steelTakeoff.workflow.v1",
      JSON.stringify({ documentId: "doc_abc123", stage: "analyzed" }),
    );
    getDocument.mockResolvedValue({ document_id: "doc_abc123", stage: "analyzed" });
    extractDocument.mockResolvedValue({ tokens: [] });
    analyzeDocument.mockResolvedValue({ results: [], summary: {} });

    render(
      <AnalysisProvider>
        <Probe />
      </AnalysisProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("rehydrating").textContent).toBe("false"));
    expect(getDocument).toHaveBeenCalledWith("doc_abc123");
    expect(extractDocument).toHaveBeenCalledWith("doc_abc123", false);
    expect(analyzeDocument).toHaveBeenCalledWith("doc_abc123", null, undefined, false);
    expect(screen.getByTestId("document-id").textContent).toBe("doc_abc123");
    expect(screen.getByTestId("extraction").textContent).toBe("yes");
    expect(screen.getByTestId("data").textContent).toBe("yes");
    expect(screen.getByTestId("stage").textContent).toBe("analyzed");
  });

  it("clears persisted state when the document no longer exists", async () => {
    sessionStorage.setItem(
      "steelTakeoff.workflow.v1",
      JSON.stringify({ documentId: "doc_gone", stage: "analyzed" }),
    );
    getDocument.mockRejectedValue(new Error("404"));

    render(
      <AnalysisProvider>
        <Probe />
      </AnalysisProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("rehydrating").textContent).toBe("false"));
    expect(screen.getByTestId("stage").textContent).toBe("empty");
    expect(sessionStorage.getItem("steelTakeoff.workflow.v1")).toBeNull();
  });

  it("surfaces a missing-original-file notice instead of silently swallowing a 404 on restore", async () => {
    sessionStorage.setItem(
      "steelTakeoff.workflow.v1",
      JSON.stringify({ documentId: "doc_legacy1", stage: "analyzed" }),
    );
    getDocument.mockResolvedValue({ document_id: "doc_legacy1", stage: "analyzed" });
    extractDocument.mockRejectedValue(
      notFoundError("Registered document path is outside the upload store"),
    );
    analyzeDocument.mockRejectedValue(
      notFoundError("Registered document path is outside the upload store"),
    );

    render(
      <AnalysisProvider>
        <Probe />
      </AnalysisProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("rehydrating").textContent).toBe("false"));

    // The workflow is not silently erased: the document id is preserved...
    expect(screen.getByTestId("document-id").textContent).toBe("doc_legacy1");
    expect(screen.getByTestId("stage").textContent).toBe("uploaded");
    // ...and a readable, specific notice replaces the blank "no data" state.
    expect(screen.getByTestId("restore-notice-kind").textContent).toBe("missing-source");
    expect(screen.getByTestId("restore-notice-message").textContent).toBe(
      "The original uploaded file is no longer available. Upload the PDF again " +
        "and run the analysis to restore provenance.",
    );
  });

  it("distinguishes a generic restore failure from a missing-source-file 404", async () => {
    sessionStorage.setItem(
      "steelTakeoff.workflow.v1",
      JSON.stringify({ documentId: "doc_flaky", stage: "analyzed" }),
    );
    getDocument.mockResolvedValue({ document_id: "doc_flaky", stage: "analyzed" });
    extractDocument.mockRejectedValue(new Error("Network Error"));
    analyzeDocument.mockRejectedValue(new Error("Network Error"));

    render(
      <AnalysisProvider>
        <Probe />
      </AnalysisProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("rehydrating").textContent).toBe("false"));
    expect(screen.getByTestId("restore-notice-kind").textContent).toBe("restore-failed");
    expect(screen.getByTestId("restore-notice-message").textContent).not.toContain(
      "no longer available",
    );
  });

  it("never persists the analysis payload itself, only the document id/stage", async () => {
    sessionStorage.setItem(
      "steelTakeoff.workflow.v1",
      JSON.stringify({ documentId: "doc_abc123", stage: "analyzed" }),
    );
    getDocument.mockResolvedValue({ document_id: "doc_abc123", stage: "analyzed" });
    extractDocument.mockResolvedValue({ tokens: [] });
    analyzeDocument.mockResolvedValue({ results: new Array(500).fill({ big: "payload" }) });

    render(
      <AnalysisProvider>
        <Probe />
      </AnalysisProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("rehydrating").textContent).toBe("false"));

    const stored = JSON.parse(sessionStorage.getItem("steelTakeoff.workflow.v1"));
    expect(Object.keys(stored).sort()).toEqual(["documentId", "stage"]);
  });
});
