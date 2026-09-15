import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SemanticReviewPage from "./SemanticReviewPage";

const { analysisDocument } = vi.hoisted(() => ({
  analysisDocument: { document_id: "doc_test1234567890", source_file: "demo.pdf" },
}));

vi.mock("../context/AnalysisContext", () => ({
  useAnalysis: () => ({ document: analysisDocument }),
}));

const getSemanticDocument = vi.fn();
const processSemanticDocument = vi.fn();
const reviewSemanticAnnotation = vi.fn().mockResolvedValue({ annotation: {} });
const getBenchmarkContext = vi.fn().mockResolvedValue(null);
const getAnnotationOracle = vi.fn().mockResolvedValue({ oracle: null });
const downloadCorrectedSemanticPdf = vi.fn().mockResolvedValue({ filename: "x_corrected.pdf" });
const acceptAllSemanticCorrections = vi.fn().mockResolvedValue({
  accepted_count: 1,
  accepted_annotation_ids: ["ann_repair"],
  document: null,
  summary: {
    accepted_correction_count: 1,
    corrected_pdf: {
      available: true,
      revision: "abc123",
      correction_count: 1,
      url: "/api/documents/doc_test1234567890/semantic/corrected-pdf?v=abc123",
    },
  },
  corrected_pdf: {
    available: true,
    revision: "abc123",
    correction_count: 1,
    url: "/api/documents/doc_test1234567890/semantic/corrected-pdf?v=abc123",
  },
});
vi.mock("../api/client", () => ({
  documentPdfUrl: (id) => `/api/documents/${id}/pdf`,
  correctedSemanticPdfUrl: (id, rev) => `/api/documents/${id}/semantic/corrected-pdf?v=${rev}`,
  getSemanticDocument: (...args) => getSemanticDocument(...args),
  processSemanticDocument: (...args) => processSemanticDocument(...args),
  reviewSemanticAnnotation: (...args) => reviewSemanticAnnotation(...args),
  acceptAllSemanticCorrections: (...args) => acceptAllSemanticCorrections(...args),
  getBenchmarkContext: (...args) => getBenchmarkContext(...args),
  getAnnotationOracle: (...args) => getAnnotationOracle(...args),
  downloadCorrectedSemanticPdf: (...args) => downloadCorrectedSemanticPdf(...args),
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
    correction: { operation: "keep", original: "X", canonical: "X", reason_codes: [], evidence_ids: [], auto_accept: false, confidence: null },
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
        structural_parse: {
          is_structural: true,
          family: "W",
          grammar: "incomplete",
          fields: {},
          catalog_exact_match: false,
        },
        correction: { operation: "keep", original: "W12", canonical: "W12", reason_codes: [], evidence_ids: [], auto_accept: false, confidence: null },
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
      baseAnnotation({
        annotation_id: "ann_multi_geom",
        primary_label: "W16X26",
        geometry_associations: [
          {
            geometry_id: "geom_pdf_1", provider: "pdf_vector",
            score: { value: 0.7, kind: "association_distance", calibrated: false },
            reason_codes: ["NEAREST_STRUCTURAL_CURVE"], verified: false, review_status: "pending",
          },
          {
            geometry_id: "geom_ghx_1", provider: "grasshopper",
            score: null, reason_codes: ["GHX_EXISTING_PAIR"], verified: false, review_status: "pending",
          },
        ],
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
    geometry_evidence: [
      { geometry_id: "geom_pdf_1", provider: "pdf_vector", geometry_type: "beam_curve" },
      { geometry_id: "geom_ghx_1", provider: "grasshopper", geometry_type: "beam_curve", source_output: "RH_OUT:BeamCrv" },
    ],
    grasshopper_geometry: [
      { geometry_id: "geom_pdf_1", provider: "pdf_vector", geometry_type: "beam_curve" },
      { geometry_id: "geom_ghx_1", provider: "grasshopper", geometry_type: "beam_curve", source_output: "RH_OUT:BeamCrv" },
    ],
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

// Operation labels also appear elsewhere on the page, so assertions on the
// inspector's badge/content must be scoped to it rather than matching page-wide.
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
    getSemanticDocument.mockResolvedValue({ document, summary: { annotation_count: 6 } });
    renderPage();

    await waitFor(() => expect(screen.getByTestId("overlay-count")).toHaveTextContent("6"));
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

  it("does not flood the viewer with every page token — only actionable overlays", async () => {
    const document = buildDocument();
    document.annotations.push(
      baseAnnotation({
        annotation_id: "ann_note_noise",
        primary_label: "SEE DETAIL",
        structural_parse: { is_structural: false, family: null, grammar: null, fields: {}, catalog_exact_match: false },
        correction: { operation: "keep", original: "SEE DETAIL", canonical: "SEE DETAIL", reason_codes: [], evidence_ids: [], auto_accept: false, confidence: null },
        review_status: "pending",
      }),
    );
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    await waitFor(() => expect(screen.getByTestId("overlay-count")).toHaveTextContent("6"));
    expect(screen.queryByTestId("overlay-ann_note_noise")).not.toBeInTheDocument();
    expect(screen.queryByText(/12205|Need Review|Annotations/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /needs review/i })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /repair queue/i })).toBeInTheDocument();
  });

  it("an annotation with no geometry evidence renders without crashing", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    fireEvent.click(await screen.findByTestId("overlay-ann_norm"));
    expect(await screen.findByText(/no geometry evidence/i)).toBeInTheDocument();
  });

  it("multiple geometry candidates from different providers render side by side, neither implied as verified", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    renderPage();

    fireEvent.click(await screen.findByTestId("overlay-ann_multi_geom"));
    expect(await inspector().findByText("geom_pdf_1")).toBeInTheDocument();
    expect(inspector().getByText("geom_ghx_1")).toBeInTheDocument();
    expect(inspector().getByText("Grasshopper candidate")).toBeInTheDocument();
    expect(inspector().getByText("pdf_vector")).toBeInTheDocument();
  });

  it("shows a process button and an empty state when nothing has been processed yet", async () => {
    getSemanticDocument.mockResolvedValue({
      document: null,
      summary: null,
      status: "not_ready",
    });
    renderPage();

    expect(await screen.findByText(/process this drawing to unlock review/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /process drawing/i })).toBeInTheDocument();
  });

  it("Accept All calls the bulk endpoint and keeps Accept All visible", async () => {
    const document = buildDocument();
    getSemanticDocument.mockResolvedValue({ document, summary: {} });
    acceptAllSemanticCorrections.mockResolvedValue({
      accepted_count: 1,
      accepted_annotation_ids: ["ann_repair"],
      document,
      summary: {
        accepted_correction_count: 1,
        corrected_pdf: {
          available: true,
          revision: "rev9",
          correction_count: 1,
          url: "/api/documents/doc_test1234567890/semantic/corrected-pdf?v=rev9",
        },
      },
      corrected_pdf: {
        available: true,
        revision: "rev9",
        correction_count: 1,
        url: "/api/documents/doc_test1234567890/semantic/corrected-pdf?v=rev9",
      },
    });
    renderPage();
    await screen.findByTestId("overlay-count");
    fireEvent.click(screen.getByTestId("accept-all-corrections"));
    await waitFor(() => expect(acceptAllSemanticCorrections).toHaveBeenCalledWith("doc_test1234567890"));
    expect(await screen.findByText(/accepted 1 correction/i)).toBeInTheDocument();
  });

  it("loads the damage-corpus navigator for SEMANTIC_DAMAGE_TEST uploads and keeps expected separate", async () => {
    analysisDocument.source_file = "burrville_SEMANTIC_DAMAGE_TEST.pdf";
    const document = buildDocument();
    // Place a repair annotation on a known Burrville case page/text so matching works.
    document.annotations.push(
      baseAnnotation({
        annotation_id: "ann_damage_match",
        page: 10,
        semantic_bbox: [1704.99, 730.32, 1717.58, 770.16],
        primary_label: "W18X40",
        correction: {
          operation: "keep",
          original: "W18X40",
          canonical: "W18X40",
          reason_codes: [],
          evidence_ids: [],
          auto_accept: true,
          confidence: null,
        },
        review_status: "auto_accepted",
      }),
    );
    getSemanticDocument.mockResolvedValue({ document, summary: { annotation_count: 7 } });
    renderPage();

    expect(await screen.findByTestId("damage-corpus-banner")).toBeInTheDocument();
    expect(screen.getByTestId("damage-case-bar")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("damage-case-next"));
    expect(screen.getByTestId("damage-case-position").textContent).toMatch(/\d+\/\d+/);
    expect(screen.getByTestId("expected-vs-actual")).toBeInTheDocument();
    expect(within(screen.getByTestId("expected-vs-actual")).getByText(/test metadata/i)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /all cases \(27\)/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /all cases/i }));
    expect(screen.getByTestId("review-queue-table").querySelectorAll("tbody tr")).toHaveLength(27);
    analysisDocument.source_file = "demo.pdf";
  });
});
