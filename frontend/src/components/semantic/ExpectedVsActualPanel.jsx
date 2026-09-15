import { Alert, Box, Paper, Stack, Typography } from "@mui/material";

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
      <Stack spacing={1}>
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          sx={{ justifyContent: "space-between" }}
        >
          <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
            Expected vs actual
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

        <Alert severity="info" sx={{ py: 0 }}>
          Expected values are test-corpus metadata. They are not model output and are not fed into the pipeline.
        </Alert>

        <Box>
          <Typography variant="caption" color="text.secondary">
            EXPECTED TEST RESULT
          </Typography>
          <Typography sx={{ fontFamily: "monospace", fontSize: 14 }}>
            {expected?.normalized || expected?.intended || "—"}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            operation={expected?.operation || "—"} · status={expected?.status || "—"}
            {expected?.abstention ? " · abstain" : ""}
          </Typography>
        </Box>

        <Box>
          <Typography variant="caption" color="text.secondary">
            ACTUAL MODEL RESULT
          </Typography>
          {actual ? (
            <>
              <Typography sx={{ fontFamily: "monospace", fontSize: 14 }}>
                raw={actual.raw || "—"} → {actual.normalized || "—"}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                operation={actual.operation || "—"} · review={actual.review_status || "—"}
                {actual.family ? ` · family=${actual.family}` : ""}
              </Typography>
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">
              —
            </Typography>
          )}
        </Box>

        {detail && (
          <Typography variant="caption" color="text.secondary">
            {detail}
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}
