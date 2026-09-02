import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MatchStatusBadge from "./MatchStatusBadge";

describe("MatchStatusBadge", () => {
  it("renders the exact-match label", () => {
    render(<MatchStatusBadge matchStatus="exact_match" />);
    expect(screen.getByText("Exact PDF Match")).toBeInTheDocument();
  });

  it("renders the corrected-prediction label", () => {
    render(<MatchStatusBadge matchStatus="corrected_prediction" />);
    expect(screen.getByText("Corrected Prediction")).toBeInTheDocument();
  });

  it("renders the incomplete-label (wildcard) label", () => {
    render(<MatchStatusBadge matchStatus="incomplete_label" />);
    expect(screen.getByText("Incomplete Label Resolved")).toBeInTheDocument();
  });

  it("renders a distinct Human Reviewed label for human_resolved, never the red Unresolved badge", () => {
    // Regression: STATUS_META previously had no entry for "human_resolved"
    // (added alongside services.human_selections), so a reviewer-resolved
    // missing-thickness HSS candidate fell through to the generic red
    // "Unresolved — Review Required" badge everywhere MatchStatusBadge is
    // used without extra isHumanReviewed gating (Drawing Review's
    // SectionResultsList, PredictionExplainability) -- falsely telling the
    // reviewer a resolved result still needed review.
    render(<MatchStatusBadge matchStatus="human_resolved" />);
    expect(screen.getByText("Human Reviewed")).toBeInTheDocument();
    expect(screen.queryByText("Unresolved — Review Required")).not.toBeInTheDocument();
  });

  it("renders a distinct label for missing_dimension_field, not the generic unresolved fallback", () => {
    render(<MatchStatusBadge matchStatus="missing_dimension_field" />);
    expect(screen.getByText("Missing Dimension — Select Section")).toBeInTheDocument();
    expect(screen.queryByText("Unresolved — Review Required")).not.toBeInTheDocument();
  });

  it("renders a distinct 'Project Legend Match' label for project_rule_resolved, not exact_match or unresolved", () => {
    render(<MatchStatusBadge matchStatus="project_rule_resolved" />);
    expect(screen.getByText("Project Legend Match")).toBeInTheDocument();
    expect(screen.queryByText("Exact PDF Match")).not.toBeInTheDocument();
    expect(screen.queryByText("Unresolved — Review Required")).not.toBeInTheDocument();
  });

  it("falls back to unresolved for an unknown status", () => {
    render(<MatchStatusBadge matchStatus="something_new" />);
    expect(screen.getByText("Unresolved — Review Required")).toBeInTheDocument();
  });

  it("exposes an accessible label", () => {
    render(<MatchStatusBadge matchStatus="geometry_only" />);
    expect(
      screen.getByLabelText("Match status: Geometry/Context Prediction"),
    ).toBeInTheDocument();
  });

  it("still renders the normal red unresolved badge for a genuine new unresolved prediction", () => {
    render(<MatchStatusBadge matchStatus="unresolved" isLegacy={false} />);
    expect(screen.getByText("Unresolved — Review Required")).toBeInTheDocument();
  });

  it("renders a distinct legacy badge instead of the status label when isLegacy is set", () => {
    render(<MatchStatusBadge matchStatus="unresolved" isLegacy />);
    expect(screen.getByText("Legacy — Re-analysis Required")).toBeInTheDocument();
    expect(screen.queryByText("Unresolved — Review Required")).not.toBeInTheDocument();
  });

  it("never renders the red unresolved error label for a legacy-only record", () => {
    // Legacy records commonly have no match_status at all; isLegacy alone
    // must be enough to suppress the red "error" treatment.
    render(<MatchStatusBadge matchStatus={undefined} isLegacy />);
    expect(screen.queryByText("Unresolved — Review Required")).not.toBeInTheDocument();
  });
});
