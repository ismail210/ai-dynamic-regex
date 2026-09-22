import { Chip, Tooltip } from "@mui/material";
import { LEGACY_PROVENANCE_MESSAGE } from "../../lib/predictionContract";

/**
 * Renders the canonical `comparison.match_status` as a single, consistent
 * badge across Results, Validation, and Review Queue. See
 * backend/services/prediction/canonical_contract.py::MatchStatus for the
 * authoritative enum this mirrors.
 */
const STATUS_META = {
  exact_match: { label: "Exact PDF Match", color: "success" },
  normalized_match: { label: "Formatting-Normalized Match", color: "success" },
  corrected_prediction: { label: "Corrected Prediction", color: "warning" },
  incomplete_label: { label: "Incomplete Label Resolved", color: "warning" },
  missing_dimension_field: { label: "Missing Dimension — Select Section", color: "warning" },
  project_rule_resolved: { label: "Project Rule", color: "success" },
  human_resolved: { label: "Human Reviewed", color: "info" },
  geometry_only: { label: "Geometry/Context Prediction", color: "info" },
  source_text_not_found: { label: "Source Text Not Found", color: "default" },
  unresolved: { label: "Unresolved — Review Required", color: "error" },
  confirmed_annotation: { label: "Confirmed Annotation", color: "success" },
  needs_context: { label: "Needs Context", color: "warning" },
};

/**
 * Records that predate the canonical contract are a pipeline-compatibility
 * gap, not an unresolved/error outcome — they get their own neutral badge
 * instead of falling into `STATUS_META.unresolved`'s red "error" treatment.
 */
const LEGACY_META = { label: "Legacy — Re-analysis Required", color: "info" };

export default function MatchStatusBadge({
  matchStatus,
  isLegacy = false,
  size = "small",
  tooltip,
  llmAssisted = false,
}) {
  const meta = isLegacy ? LEGACY_META : STATUS_META[matchStatus] || STATUS_META.unresolved;
  // A project-rule resolution earns an "LLM-Assisted" prefix only when the
  // winning rule actually came from a validated LLM extraction
  // (services.engineering.project_rule_resolver's `extraction_method ==
  // "llm_assisted"`) -- never applied to the deterministic "X" = Y legend
  // read, so a plain project rule is never mislabeled as LLM-assisted
  // (task Section 7).
  const label =
    llmAssisted && matchStatus === "project_rule_resolved" && !isLegacy
      ? `LLM-Assisted · ${meta.label}`
      : meta.label;
  const chip = (
    <Chip
      size={size}
      color={meta.color}
      variant={isLegacy || meta.color === "default" ? "outlined" : "filled"}
      label={label}
      aria-label={`Match status: ${label}`}
    />
  );
  const resolvedTooltip = tooltip || (isLegacy ? LEGACY_PROVENANCE_MESSAGE : undefined);
  return resolvedTooltip ? <Tooltip title={resolvedTooltip}>{chip}</Tooltip> : chip;
}

export function matchStatusLabel(matchStatus, isLegacy = false, llmAssisted = false) {
  if (isLegacy) return LEGACY_META.label;
  const meta = STATUS_META[matchStatus] || STATUS_META.unresolved;
  if (llmAssisted && matchStatus === "project_rule_resolved") {
    return `LLM-Assisted · ${meta.label}`;
  }
  return meta.label;
}
