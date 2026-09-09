import { useMemo, useState } from "react";
import {
  Box,
  Chip,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import { isSteelTakeoffToken } from "../lib/predictionContract";

const DISCARD_LABELS = {
  layout_dims: "layout dimensions",
  title_block: "title block",
  weak_anonymous: "weak anonymous dims",
  standalone_refs: "standalone grades/refs",
  duplicates: "duplicates",
};

/**
 * Post-extraction summary: object counts, ignored-text breakdown, and the
 * detected structural labels. Read-only. Lifted verbatim from the old Extract
 * page so the merged Upload & Extract page can show it inline.
 */
export default function ExtractionSummary({ extraction }) {
  const [steelOnly, setSteelOnly] = useState(true);

  const visibleTokens = useMemo(() => {
    const tokens = extraction?.tokens || [];
    if (!steelOnly) return tokens;
    return tokens.filter(isSteelTakeoffToken);
  }, [extraction, steelOnly]);

  if (!extraction) return null;

  const counts = extraction.object_counts || {};
  const discardBreakdown = counts.discard_breakdown || {};

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" gap={1} mb={2} sx={{ flexWrap: "wrap" }}>
        <Chip label={`${counts.engineering_objects || 0} engineering objects`} />
        <Chip label={`${counts.discarded_text_candidates || 0} text candidates ignored`} />
        <Chip label={`${extraction.layout?.tables?.length || 0} tables`} />
        <Chip label={`${extraction.layout?.dimensions?.length || 0} dimensions`} />
        <Chip label={`${extraction.layout?.callouts?.length || 0} callouts`} />
        {extraction.cached && <Chip color="info" label="Cached extraction" />}
      </Stack>
      {Object.keys(discardBreakdown).length > 0 && (
        <Stack direction="row" gap={0.75} mb={2} sx={{ flexWrap: "wrap" }}>
          {Object.entries(discardBreakdown).map(([key, value]) => (
            <Chip
              key={key}
              size="small"
              variant="outlined"
              color="default"
              label={`${value} ${DISCARD_LABELS[key] || key}`}
            />
          ))}
        </Stack>
      )}
      <Stack
        direction="row"
        mb={1}
        sx={{ justifyContent: "space-between", alignItems: "center" }}
      >
        <Typography variant="subtitle2">
          Detected structural labels
          {steelOnly ? ` (${visibleTokens.length} steel-focused)` : ""}
        </Typography>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={steelOnly}
              onChange={(event) => setSteelOnly(event.target.checked)}
            />
          }
          label="Steel objects only"
        />
      </Stack>
      <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap" }}>
        {visibleTokens.slice(0, 80).map((token) => (
          <Chip
            key={token.token_id}
            variant="outlined"
            size="small"
            label={`${token.text} · ${token.engineering_object_type}`}
          />
        ))}
      </Stack>
    </Paper>
  );
}
