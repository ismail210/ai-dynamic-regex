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
