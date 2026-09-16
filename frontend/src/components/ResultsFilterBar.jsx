import { useMemo } from "react";
import { Chip, Stack } from "@mui/material";
import { getStatusTags } from "../lib/predictionContract";

/**
 * Canonical result-category quick filters for Analysis/Results and Drawing
 * Review (task Sections 16-23). Counts are computed from the FULL result
 * set passed in, never the already-filtered/paginated subset, so a chip's
 * number never shifts just because another filter narrowed the visible
 * rows.
 *
 * "All" clears every selection. "Needs attention" is the only negative
 * filter (NOT perfect_match) — every other chip is a direct status_tags
 * membership check. Multiple selected chips combine with OR (task Section
 * 20): a row is shown if it matches ANY selected chip.
 */
export const FILTER_CHIPS = [
  { key: "perfect", label: "Perfect", match: (tags) => tags.has("perfect_match") },
  { key: "needs_attention", label: "Needs attention", match: (tags) => !tags.has("perfect_match") },
  { key: "formatting", label: "Formatting", match: (tags) => tags.has("formatting_only") },
  // One combined chip: a row tagged llm_assisted is always also tagged
  // project_rule (an LLM-sourced rule is a kind of project rule), so
  // splitting them into two chips only ever produced two overlapping
  // buckets with the same rows in practice.
  { key: "project_rule", label: "Project rule", match: (tags) => tags.has("project_rule") || tags.has("llm_assisted") },
  { key: "needs_review", label: "Needs review", match: (tags) => tags.has("needs_review") },
  { key: "low_confidence", label: "Low confidence", match: (tags) => tags.has("low_confidence") },
  { key: "human_reviewed", label: "Human reviewed", match: (tags) => tags.has("human_reviewed") },
  { key: "warning", label: "Warning", match: (tags) => tags.has("warning") },
  { key: "unresolved", label: "Unresolved", match: (tags) => tags.has("unresolved") },
];

/** Row predicate for the currently-selected filter keys — OR semantics,
 * pass-through (no filtering) when nothing is selected ("All"). */
export function matchesSelectedFilters(result, selectedKeys) {
  if (!selectedKeys || selectedKeys.size === 0) return true;
  const tags = getStatusTags(result);
  for (const chip of FILTER_CHIPS) {
    if (selectedKeys.has(chip.key) && chip.match(tags)) return true;
  }
  return false;
}

export default function ResultsFilterBar({ results = [], selected, onToggle, onClear }) {
  const counts = useMemo(() => {
    const tagged = results.map((r) => getStatusTags(r));
    const out = { all: results.length };
    for (const chip of FILTER_CHIPS) {
      out[chip.key] = tagged.reduce((n, tags) => n + (chip.match(tags) ? 1 : 0), 0);
    }
    return out;
  }, [results]);

  const allActive = selected.size === 0;

  return (
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
      <Chip
        size="small"
        label={`All (${counts.all})`}
        color={allActive ? "primary" : "default"}
        variant={allActive ? "filled" : "outlined"}
        onClick={onClear}
      />
      {FILTER_CHIPS.map((chip) => (
        <Chip
          key={chip.key}
          size="small"
          label={`${chip.label} (${counts[chip.key]})`}
          color={selected.has(chip.key) ? "primary" : "default"}
          variant={selected.has(chip.key) ? "filled" : "outlined"}
          onClick={() => onToggle(chip.key)}
        />
      ))}
      {!allActive && (
        <Chip size="small" label="Clear filters" variant="outlined" onClick={onClear} />
      )}
    </Stack>
  );
}
