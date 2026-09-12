import { Box, Paper, Typography } from "@mui/material";

const STAT_TOKENS = [
  { key: "annotation_count", label: "Annotations", colorKey: "neutral" },
  { key: "normalized_count", label: "Normalized", colorKey: "info" },
  { key: "repaired_count", label: "Repaired", colorKey: "warning" },
  { key: "completed_count", label: "Completed", colorKey: "success" },
  { key: "unchanged_count", label: "Unchanged", colorKey: "neutral" },
  { key: "needs_review_count", label: "Need Review", colorKey: "warning" },
  { key: "geometry_linked_count", label: "Geometry Linked", colorKey: "info" },
  { key: "drawing_rule_count", label: "Drawing Rules", colorKey: "success" },
];

/**
 * Only real, derivable numbers -- no precision/recall/quantity metrics
 * (Section 8/35: those belong to a separate validation surface, not this
 * semantic-understanding demo).
 */
export default function DocumentSummaryBar({ summary }) {
  if (!summary) return null;
  return (
    <Paper
      variant="outlined"
      sx={{
        px: 2,
        py: 1.25,
        display: "flex",
        flexWrap: "wrap",
        gap: { xs: 2, md: 3 },
        rowGap: 1,
      }}
    >
      {STAT_TOKENS.map(({ key, label, colorKey }) => (
        <Box key={key} sx={{ minWidth: 88 }}>
          <Typography
            variant="h6"
            sx={{
              fontWeight: 750,
              lineHeight: 1.1,
              color: colorKey === "neutral" ? "text.primary" : `${colorKey}.main`,
            }}
          >
            {summary[key] ?? 0}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {label}
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
