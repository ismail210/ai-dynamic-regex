import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
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
