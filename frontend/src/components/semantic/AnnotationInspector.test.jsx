import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import AnnotationInspector from "./AnnotationInspector";

const getAnnotationOracle = vi.fn();
vi.mock("../../api/client", () => ({
  getAnnotationOracle: (...args) => getAnnotationOracle(...args),
}));

function suspiciousAnnotation(overrides = {}) {
  return {
    annotation_id: "ann_1",
    page: 5,
    original_text: "WI8X40",
    primary_label: "WI8X40",
    effective_text: "WI8X40",
    extraction_source: "native_pdf",
    modifiers: [],
    structural_parse: {
      is_structural: false,
      family: null,
      grammar: null,
      catalog_exact_match: false,
      parser_reason: "no_known_grammar_matched",
    },
    correction: {
      operation: "keep",
      original: "WI8X40",
      canonical: "WI8X40",
      confidence: null,
      confidence_is_calibrated: false,
      auto_accept: false,
      reason_codes: [],
      evidence_ids: [],
    },
    operations: [
      {
        operation: "repair",
        input_text: "WI8X40",
        output_text: "W18X40",
        accepted: false,
        reason_codes: ["label_reconstruction_shadow_proposal"],
      },
    ],
    repair_candidates: [
      {
        candidate_text: "W18X40",
        rank: 1,
        source: "label_reconstruction_ranker",
        scores: [{ value: 6.6994, kind: "raw_model_score", calibrated: false }],
        evidence: [{ notes: "Single-character difference at position 1: 'I' -> '1'" }],
        reason_codes: ["ocr_flex_positional"],
      },
      {
        candidate_text: "W18X46",
        rank: 2,
        source: "label_reconstruction_ranker",
        scores: [{ value: 0.9724, kind: "raw_model_score", calibrated: false }],
        evidence: [{ notes: "Nearest catalog entry by character similarity" }],
        reason_codes: ["fuzzy_nearest_neighbor"],
      },
    ],
    geometry_associations: [],
    review_status: "needs_review",
    review: { status: "needs_review", reason: "repair_candidate_available", history: [] },
    ...overrides,
  };
}

function cleanAnnotation() {
  return {
    annotation_id: "ann_clean",
    page: 5,
    original_text: "W24X68",
    primary_label: "W24X68",
    effective_text: "W24X68",
    modifiers: [],
    structural_parse: { is_structural: true, family: "W", grammar: "depth_weight", catalog_exact_match: true },
    correction: { operation: "keep", original: "W24X68", canonical: "W24X68", auto_accept: false, reason_codes: [], evidence_ids: [] },
    operations: [{ operation: "keep", input_text: "W24X68", output_text: "W24X68", accepted: true }],
    repair_candidates: [],
    geometry_associations: [],
    review_status: "pending",
    review: { status: "pending", history: [] },
  };
}

const emptyDocument = { annotations: [], drawing_language_rules: [], grasshopper_geometry: [] };

beforeEach(() => {
  getAnnotationOracle.mockReset();
  getAnnotationOracle.mockResolvedValue({ oracle: null });
});

describe("AnnotationInspector -- repair trace", () => {
  it("shows a process timeline for a suspicious annotation", () => {
    render(<AnnotationInspector document={emptyDocument} annotation={suspiciousAnnotation()} onReview={vi.fn()} />);
    expect(screen.getByTestId("process-timeline")).toBeInTheDocument();
    expect(screen.getByText(/Human review required/i)).toBeInTheDocument();
  });

  it("renders the real candidate list with honestly-labeled scores", () => {
    render(<AnnotationInspector document={emptyDocument} annotation={suspiciousAnnotation()} onReview={vi.fn()} />);
    const panel = screen.getByTestId("repair-candidates-panel");
    expect(panel).toHaveTextContent("W18X40");
    expect(panel).toHaveTextContent("W18X46");
    // A raw model score must be labeled "Model score", never shown as a bare percentage.
    expect(panel).toHaveTextContent("Model score");
    expect(panel).not.toHaveTextContent("%");
  });

  it("does not render a candidates panel for a clean, unambiguous annotation", () => {
    render(<AnnotationInspector document={emptyDocument} annotation={cleanAnnotation()} onReview={vi.fn()} />);
    expect(screen.queryByTestId("repair-candidates-panel")).not.toBeInTheDocument();
  });

  it("Accept proposal calls onReview with the top candidate's text", () => {
    const onReview = vi.fn();
    render(<AnnotationInspector document={emptyDocument} annotation={suspiciousAnnotation()} onReview={onReview} />);
    fireEvent.click(screen.getByRole("button", { name: /Accept proposal/i }));
    expect(onReview).toHaveBeenCalledWith("accept", null, "W18X40");
  });

  it("Choose alternate calls onReview with the alternate candidate's text", () => {
    const onReview = vi.fn();
    render(<AnnotationInspector document={emptyDocument} annotation={suspiciousAnnotation()} onReview={onReview} />);
    fireEvent.click(screen.getByRole("button", { name: /^Choose$/i }));
    expect(onReview).toHaveBeenCalledWith("accept", null, "W18X46");
  });

  it("Reject calls onReview with the reject action (original is preserved server-side)", () => {
    const onReview = vi.fn();
    render(<AnnotationInspector document={emptyDocument} annotation={suspiciousAnnotation()} onReview={onReview} />);
    fireEvent.click(screen.getByRole("button", { name: /Reject/i }));
    expect(onReview).toHaveBeenCalledWith("reject");
  });

  it("hides the benchmark truth panel unless a benchmarkContext is supplied", () => {
    render(<AnnotationInspector document={emptyDocument} annotation={suspiciousAnnotation()} onReview={vi.fn()} documentId="doc_1" />);
    expect(screen.queryByTestId("reveal-benchmark-truth")).not.toBeInTheDocument();
  });

  it("shows a reveal button in benchmark mode, and fetches the oracle only on click", async () => {
    getAnnotationOracle.mockResolvedValue({
      oracle: { kind: "mutation", clean_text: "W18X40", corrupted_text: "WI8X40", corruption_types: ["digit_1_to_i"], human_decision_matches_truth: true },
    });
    render(
      <AnnotationInspector
        document={emptyDocument}
        annotation={suspiciousAnnotation()}
        onReview={vi.fn()}
        documentId="doc_1"
        benchmarkContext={{ source_pdf: "FnF_Structure.pdf", mutation_count: 35, clean_control_count: 27 }}
      />,
    );
    expect(getAnnotationOracle).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("reveal-benchmark-truth"));
    await waitFor(() => expect(screen.getByTestId("benchmark-truth-result")).toBeInTheDocument());
    expect(screen.getByTestId("benchmark-truth-result")).toHaveTextContent("Correct repair");
  });
});
