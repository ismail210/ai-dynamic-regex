import { Box, Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { PlaceOutlined, VerifiedOutlined } from "@mui/icons-material";

/**
 * The "hero" evidence card (Section 14/33): shows exactly which
 * source-verified drawing rule justified a completion, with a "View
 * source" jump to the real page/bbox it came from. Never implies
 * "Grasshopper verified" or any authority beyond what the rule object
 * actually carries (Section 34).
 */
export default function DrawingRuleCard({ rule, onViewSource }) {
  if (!rule) return null;
  const evidence = rule.source_evidence?.[0];
  const isSourceVerified = rule.rule_status === "source_verified";

  return (
    <Paper
      variant="outlined"
      sx={{ p: 1.5, borderColor: isSourceVerified ? "success.main" : "divider" }}
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
        <VerifiedOutlined fontSize="small" color={isSourceVerified ? "success" : "disabled"} />
        <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
          Drawing rule
        </Typography>
        <Chip
          size="small"
          label={isSourceVerified ? "Source verified" : "Proposed only"}
          color={isSourceVerified ? "success" : "default"}
          variant={isSourceVerified ? "filled" : "outlined"}
        />
      </Stack>
      <Typography
        sx={{ fontFamily: "monospace", fontSize: 15, fontWeight: 700, mb: 0.5 }}
      >
        {rule.trigger} → {rule.result}
      </Typography>
      {evidence && (
        <>
          <Typography variant="caption" color="text.secondary" display="block">
            Page {evidence.page}
            {rule.scope?.pages?.length ? "" : " · applies document-wide"}
          </Typography>
          {evidence.quote && (
            <Box
              sx={{
                mt: 0.75,
                mb: 1,
                px: 1,
                py: 0.5,
                bgcolor: "action.hover",
                borderRadius: 1,
                fontFamily: "monospace",
                fontSize: 12.5,
              }}
            >
              {evidence.quote}
            </Box>
          )}
        </>
      )}
      {evidence?.bbox && onViewSource && (
        <Button
          size="small"
          startIcon={<PlaceOutlined fontSize="small" />}
          onClick={() => onViewSource(evidence.page, evidence.bbox)}
        >
          View source
        </Button>
      )}
    </Paper>
  );
}
