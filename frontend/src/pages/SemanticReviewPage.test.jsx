import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SemanticReviewPage from "./SemanticReviewPage";

vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => ({ document: { document_id: "doc_test1234567890" } }),
}));

const getSemanticDocument = vi.fn();
const processSemanticDocument = vi.fn();
const reviewSemanticAnnotation = vi.fn().mockResolvedValue({ annotation: {} });
vi.mock("../api/client", () => ({
  documentPdfUrl: (id) => `/api/documents/${id}/pdf`,
  getSemanticDocument: (...args) => getSemanticDocument(...args),
  processSemanticDocument: (...args) => processSemanticDocument(...args),
  reviewSemanticAnnotation: (...args) => reviewSemanticAnnotation(...args),
}));

// The real viewer needs a real PDF worker; here only the overlay/selection
// wiring matters (PdfDocumentViewer's own rendering is covered by its own
// test suite), so it's replaced with buttons exposing exactly those props.
vi.mock("../components/pdf/PdfDocumentViewer", () => ({
  default: ({ overlays, selection }) => (
    <div>
      <div data-testid="selection-page">{selection?.pageNumber ?? "none"}</div>
      <div data-testid="overlay-count">{overlays?.length ?? 0}</div>
      {overlays?.map((o) => (
        <button key={o.key} type="button" data-testid={`overlay-${o.key}`} onClick={o.onClick}>
          {o.badgeTitle}
        </button>
      ))}
    </div>
  ),
}));

function baseAnnotation(overrides) {
  return {
    annotation_id: "ann_default",
    page: 5,
    original_text: "X",
    source_fragment_ids: [],
    source_fragments: [],
    semantic_bbox: [0, 0, 10, 10],
    original_anchor: [5, 5],
    primary_label: "X",
    modifiers: [],
    grouping_reasons: [],
    structural_parse: { is_structural: true, family: "W", grammar: "depth_weight", fields: {}, catalog_exact_match: true },
    correction: { operation: "none", original: "X", canonical: "X", reason_codes: [], evidence_ids: [], auto_accept: false, confidence: null },
    geometry_associations: [],
    review_status: "pending",
    ...overrides,
  };
}

function buildDocument() {
  return {
    document_id: "doc_test1234567890",
    annotations: [
      baseAnnotation({
        annotation_id: "ann_norm",
        primary_label: "HSS8X8X3/8",
        correction: {
          operation: "normalization", original: "HSS 8X8X0.375", canonical: "HSS8X8X3/8",
          reason_codes: ["deterministic_grammar_equivalence"], evidence_ids: [], auto_accept: true, confidence: 1.0,
        },
        review_status: "auto_accepted",
      }),
      baseAnnotation({
        annotation_id: "ann_completion",
        primary_label: "W8",
        correction: {
          operation: "completion", original: "W8", canonical: "W8X10",
          reason_codes: ["source_verified_match"], evidence_ids: ["note_W8"], auto_accept: true, confidence: null,
        },
        review_status: "auto_accepted",
      }),
      baseAnnotation({
        annotation_id: "ann_bare_no_rule",
        primary_label: "W12",
        correction: { operation: "none", original: "W12", canonical: "W12", reason_codes: [], evidence_ids: [], auto_accept: false, confidence: null },
        review_status: "pending",
      }),
      baseAnnotation({
        annotation_id: "ann_repair",
        primary_label: "W8XI0",
        correction: {
          operation: "repair", original: "W8XI0", canonical: "W8X10",
          reason_codes: ["single_char_ocr_confusion_candidate"], evidence_ids: [], auto_accept: false, confidence: null,
        },
        review_status: "needs_review",
      }),
      baseAnnotation({
        annotation_id: "ann_grouped",
        primary_label: "W18X40",
        modifiers: [{ type: "bracket_tag", raw_text: "[11;3;11]", value: "11;3;11", primitive_ids: ["p2"], bbox: [20, 0, 30, 10] }],
        source_fragment_ids: ["p1", "p2"],
        source_fragments: [
          { primitive_id: "p1", text: "W18x40", bbox: [0, 0, 10, 10] },
          { primitive_id: "p2", text: "[11;3;11]", bbox: [20, 0, 30, 10] },
        ],
        grouping_reasons: ["bracket_modifier_attachment"],
      }),
    ],
    drawing_language_rules: [
      {
        rule_id: "note_W8", trigger: "W8", result: "W8X10", rule_status: "source_verified",
        scope: { pages: [] },
        source_evidence: [{ page: 5, bbox: [1, 1, 2, 2], quote: '"W8" = W8x10' }],
        confidence: 0.95,
      },
    ],
    grasshopper_geometry: [],
    coordinate_frames: [],
    diagnostics: {},
    metrics: {},
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SemanticReviewPage />
    </MemoryRouter>,
  );
}

// Several operation labels ("Normalized", "Completed", ...) also appear as
// static DocumentSummaryBar stat labels, so assertions on the inspector's
// own badge/content must be scoped to it rather than matching page-wide.
function inspector() {
  return within(screen.getByTestId("annotation-inspector"));
}

describe("SemanticReviewPage", () => {
  beforeEach(() => {
    getSemanticDocument.mockReset();
    processSemanticDocument.mockReset();
    reviewSemanticAnnotation.mockClear();
  });

  it("loads the semantic fixture deterministically and renders overlays for the default page", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: { annotation_count: 5 } });
    renderPage();

    await waitFor(() => expect(screen.getByTestId("overlay-count")).toHaveTextContent("5"));
    expect(getSemanticDocument).toHaveBeenCalledWith("doc_test1234567890");
  });

  it("clicking a normalization overlay populates the inspector with original/canonical and the Normalized badge", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    const overlay = await screen.findByTestId("overlay-ann_norm");
    fireEvent.click(overlay);

    expect(await inspector().findByText("Normalized")).toBeInTheDocument();
    expect(inspector().getByText("HSS 8X8X0.375")).toBeInTheDocument();
    expect(inspector().getByText("HSS8X8X3/8")).toBeInTheDocument();
  });

  it("shows the repair state distinctly, with an uncalibrated-confidence note, not a fabricated percentage", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    fireEvent.click(await screen.findByTestId("overlay-ann_repair"));
    expect(await inspector().findByText("Repaired")).toBeInTheDocument();
    expect(inspector().getByText(/not a calibrated probability/i)).toBeInTheDocument();
  });

  it("shows the completion's source-verified drawing rule with a View source action", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    fireEvent.click(await screen.findByTestId("overlay-ann_completion"));
    expect(await inspector().findByText("Completed")).toBeInTheDocument();
    expect(inspector().getByText("Source verified")).toBeInTheDocument();
    expect(inspector().getByText('"W8" = W8x10')).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /view source/i }));
    await waitFor(() => expect(screen.getByTestId("selection-page")).toHaveTextContent("5"));
  });

  it("a bare shorthand with no source-verified rule stays unchanged, never silently completed", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    fireEvent.click(await screen.findByTestId("overlay-ann_bare_no_rule"));
    expect(await inspector().findByText("Unchanged")).toBeInTheDocument();
    // Only the original text renders -- no separate "canonical" ever appears
    // when nothing actually changed.
    expect(inspector().queryByText("CANONICAL")).not.toBeInTheDocument();
  });

  it("a grouped annotation exposes its source fragments when the toggle is enabled", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    await screen.findByTestId("overlay-count");
    const before = Number(screen.getByTestId("overlay-count").textContent);

    fireEvent.click(screen.getByRole("switch", { name: /source fragments/i }));

    await waitFor(() => {
      const after = Number(screen.getByTestId("overlay-count").textContent);
      expect(after).toBeGreaterThan(before);
    });
  });

  it("needs-review-only filtering shows just the flagged annotation", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    await screen.findByTestId("overlay-count");
    fireEvent.click(screen.getByRole("switch", { name: /needs review only/i }));

    await waitFor(() => expect(screen.getByTestId("overlay-count")).toHaveTextContent("1"));
  });

  it("an annotation with no geometry evidence renders without crashing", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    fireEvent.click(await screen.findByTestId("overlay-ann_norm"));
    expect(await screen.findByText(/no geometry evidence/i)).toBeInTheDocument();
  });

  it("shows a process button and an empty state when nothing has been processed yet", async () => {
    getSemanticDocument.mockRejectedValue({ response: { status: 404 } });
    renderPage();

    expect(await screen.findByText(/no semantic result yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /process drawing/i })).toBeInTheDocument();
  });
});
