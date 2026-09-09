import { Link as RouterLink } from "react-router-dom";
import { Box, Stack, Typography } from "@mui/material";
import { CheckRounded } from "@mui/icons-material";
import { useAnalysis } from "../../context/AnalysisContext";

// The one canonical demo workflow. `key` is matched against the `step` prop;
// `done` is decided from AnalysisContext.stage so completed steps get a check.
const STEPS = [
  { key: "upload", label: "Upload", to: "/upload-extract" },
  { key: "summary", label: "Summary", to: "/drawing-summary" },
  { key: "analyze", label: "Analyze", to: "/analysis" },
  { key: "review", label: "Review", to: "/review-drawing" },
  { key: "validate", label: "Validate", to: "/validation" },
  { key: "takeoff", label: "Takeoff", to: "/takeoff" },
];

// How far the workflow has genuinely progressed, by stage. Steps at or below
// this index (and not the current one) render as done.
const STAGE_REACHED = { empty: -1, uploaded: 0, extracted: 1, analyzed: 5 };

/**
 * Subtle, non-blocking progress strip shown at the top of every workflow page.
 * Informational only — it never gates navigation (the pages keep their own
 * "requires extraction/analysis" empty states).
 */
export default function WorkflowProgress({ step }) {
  const { stage } = useAnalysis();
  const reached = STAGE_REACHED[stage] ?? -1;
  const currentIndex = STEPS.findIndex((s) => s.key === step);

  return (
    <Stack
      direction="row"
      spacing={0.5}
      useFlexGap
      sx={{ flexWrap: "wrap", alignItems: "center", mb: 2.5, rowGap: 0.75 }}
    >
      {STEPS.map((s, index) => {
        const isCurrent = index === currentIndex;
        const isDone = !isCurrent && index <= reached;
        return (
          <Box key={s.key} sx={{ display: "flex", alignItems: "center" }}>
            <Stack
              component={RouterLink}
              to={s.to}
              direction="row"
              spacing={0.6}
              sx={{
                alignItems: "center",
                textDecoration: "none",
                px: 0.9,
                py: 0.35,
                borderRadius: 1,
                bgcolor: isCurrent ? "action.selected" : "transparent",
                color: isCurrent
                  ? "text.primary"
                  : isDone
                    ? "text.secondary"
                    : "text.disabled",
                "&:hover": { bgcolor: "action.hover" },
              }}
            >
              <Box
                sx={{
                  width: 16,
                  height: 16,
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  fontSize: 10,
                  fontWeight: 700,
                  border: 1,
                  borderColor: isCurrent
                    ? "primary.main"
                    : isDone
                      ? "success.main"
                      : "divider",
                  color: isCurrent ? "primary.main" : isDone ? "success.main" : "inherit",
                }}
              >
                {isDone ? <CheckRounded sx={{ fontSize: 11 }} /> : index + 1}
              </Box>
              <Typography
                variant="caption"
                sx={{ fontWeight: isCurrent ? 700 : 600, whiteSpace: "nowrap" }}
              >
                {s.label}
              </Typography>
            </Stack>
            {index < STEPS.length - 1 && (
              <Box
                sx={{
                  width: 14,
                  height: "1px",
                  mx: 0.25,
                  bgcolor: "divider",
                  flexShrink: 0,
                }}
              />
            )}
          </Box>
        );
      })}
    </Stack>
  );
}
