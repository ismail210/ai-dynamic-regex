import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { uploadPdf } from "../api/client";
import UploadExtractPage from "./UploadExtractPage";

const mockUseAnalysis = vi.fn();
vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => mockUseAnalysis(),
}));
vi.mock("../api/client", () => ({
  uploadPdf: vi.fn(),
  extractDocument: vi.fn(),
}));

function renderPage(analysis) {
  mockUseAnalysis.mockReturnValue({
    document: null,
    extraction: null,
    excelFile: null,
    setExcelFile: vi.fn(),
    setExtraction: vi.fn(),
    setData: vi.fn(),
    setDocument: vi.fn(),
    setRestoreNotice: vi.fn(),
    stage: "empty",
    ...analysis,
  });
  return render(
    <MemoryRouter>
      <UploadExtractPage />
    </MemoryRouter>,
  );
}

describe("UploadExtractPage", () => {
  it("shows the upload dropzone when there is no document", () => {
    renderPage({ document: null });
    expect(screen.getByText("Drop a PDF here")).toBeInTheDocument();
  });

  it("shows the extract action and Excel picker once a document is stored", () => {
    renderPage({
      document: { document_id: "doc-1", source_file: "a.pdf", page_count: 4 },
      stage: "uploaded",
    });
    expect(screen.getByText("Extract drawing")).toBeInTheDocument();
    expect(screen.getByText("Optional ground-truth Excel")).toBeInTheDocument();
  });

  it("offers a way back to the PDF chooser when a restored document is loaded", () => {
    const startNewAnalysis = vi.fn();
    renderPage({
      document: { document_id: "doc-1", source_file: "a.pdf", page_count: 4 },
      stage: "uploaded",
      startNewAnalysis,
    });
    fireEvent.click(screen.getByRole("button", { name: /upload a different pdf/i }));
    expect(startNewAnalysis).toHaveBeenCalledTimes(1);
  });

  it("uploads a chosen PDF, accepts one without a MIME type, and can take the same file twice", async () => {
    uploadPdf.mockResolvedValue({ document_id: "doc-2", source_file: "b.pdf", page_count: 2 });
    const { container } = renderPage({ document: null });
    const input = container.querySelector('input[type="file"]');
    const file = new File(["%PDF-1.4"], "b.pdf", { type: "" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(uploadPdf).toHaveBeenCalledTimes(1));
    expect(uploadPdf.mock.calls[0][0]).toBe(file);
    expect(input.value).toBe("");
  });

  it("shows the extraction summary and the forward CTA once extracted", () => {
    renderPage({
      document: { document_id: "doc-1", source_file: "a.pdf", page_count: 4 },
      extraction: { tokens: [], object_counts: { engineering_objects: 12 }, layout: {} },
      stage: "extracted",
    });
    expect(screen.getByText("Continue to Drawing Summary")).toBeInTheDocument();
    expect(screen.getByText("12 engineering objects")).toBeInTheDocument();
  });
});
