import { Box, Paper, Stack, Typography } from "@mui/material";

/**
 * Explicitly separates TEST METADATA (expected) from live backend output (actual).
 * Never substitutes expected values into the model result.
 */
export default function ExpectedVsActualPanel({ comparison }) {
  if (!comparison) return null;
  const { status, expected, actual, detail } = comparison;
  const tone =
    status === "PASS" ? "success" : status === "UNMATCHED" ? "info" : status === "n/a" ? "neutral" : "warning";

  return (
    <Paper
      variant="outlined"
      data-testid="expected-vs-actual"
      sx={{
        p: 1.25,
        borderColor: tone === "neutral" ? "divider" : `${tone}.main`,
      }}
    >
      <Stack spacing={0.75}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            {expected?.normalized || expected?.intended || "—"}
            <Box component="span" sx={{ color: "text.secondary", fontWeight: 500, mx: 0.75 }}>→</Box>
            {actual?.normalized || "—"}
          </Typography>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              color: tone === "neutral" ? "text.secondary" : `${tone}.main`,
            }}
            data-testid="expected-vs-actual-status"
          >
            {status}
          </Typography>
        </Stack>

        <Typography variant="caption" color="text.secondary">
          Expected is test metadata · actual is live model
          {expected?.operation ? ` · expected ${expected.operation}` : ""}
          {actual?.operation ? ` · got ${actual.operation}` : ""}
          {expected?.abstention ? " · abstain" : ""}
        </Typography>

        {detail && (
          <Typography variant="caption" color="text.secondary">
            {detail}
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}
