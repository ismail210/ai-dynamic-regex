import { Box, Chip, Stack, Typography } from "@mui/material";
import { VerifiedOutlined } from "@mui/icons-material";
import DrawingRuleCard from "./DrawingRuleCard";

/**
 * Structured document intelligence, not an "AI summary" paragraph
 * (Section 23/24): only values actually present in the semantic document.
 */
export default function DocumentIntelligencePanel({ document, onViewSource }) {
  const rules = document?.drawing_language_rules || [];
  const sourceVerified = rules.filter((r) => r.rule_status === "source_verified");

  const families = new Set();
  for (const a of document?.annotations || []) {
    if (a.structural_parse?.family) families.add(a.structural_parse.family);
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
          Detected structural families
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
          {[...families].sort().map((family) => (
            <Chip key={family} size="small" label={family} variant="outlined" />
          ))}
          {!families.size && (
            <Typography variant="body2" color="text.secondary">None detected.</Typography>
          )}
        </Stack>
      </Box>

      <Box>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
          <VerifiedOutlined fontSize="small" color="success" />
          <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
            Source-verified drawing rules ({sourceVerified.length})
          </Typography>
        </Stack>
        <Stack spacing={1}>
          {sourceVerified.map((rule) => (
            <DrawingRuleCard key={rule.rule_id} rule={rule} onViewSource={onViewSource} />
          ))}
          {!sourceVerified.length && (
            <Typography variant="body2" color="text.secondary">
              No source-verified rules were found in this drawing's notes.
            </Typography>
          )}
        </Stack>
      </Box>
    </Stack>
  );
}
