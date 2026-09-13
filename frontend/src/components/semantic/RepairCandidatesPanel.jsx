import { Box, Button, Chip, Paper, Stack, Tooltip, Typography } from "@mui/material";
import { CheckCircleOutlined, HelpOutlined } from "@mui/icons-material";
import { describeScore, getRepairCandidates } from "../../lib/semanticContract";

const SOURCE_LABELS = {
  label_reconstruction_ranker: "Ranked by the trained candidate model",
  label_reconstruction_deterministic: "Deterministic candidate generator (no ranker available)",
  label_reconstruction_fuzzy_fallback: "Broadened fuzzy fallback (low confidence)",
};

/**
 * Real ranked repair candidates from services.label_reconstruction (Section
 * 9/17) -- never fabricated. Shows top 5; the full set stays in the raw
 * document payload for diagnostics. Score captions are kind-aware (Section
 * 8): a raw model score is never presented as a percentage/probability.
 */
export default function RepairCandidatesPanel({ annotation, onAccept, busy = false }) {
  const candidates = getRepairCandidates(annotation).slice(0, 5);
  if (!candidates.length) return null;

  const currentEffective = annotation.effective_text;
  const isFallback = candidates[0]?.source === "label_reconstruction_fuzzy_fallback";

  return (
    <Box data-testid="repair-candidates-panel">
      <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
        Candidates
      </Typography>
      {isFallback && (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
          The query's numeric fields looked complete, so the main engine found no confident
          match — these are broadened, similarity-only suggestions for review.
        </Typography>
      )}
      <Stack spacing={0.75} sx={{ mt: 0.5 }}>
        {candidates.map((candidate) => {
          const score = candidate.scores?.[0];
          const described = describeScore(score);
          const isCurrent = candidate.candidate_text === currentEffective;
          return (
            <Paper
              key={candidate.candidate_text}
              variant="outlined"
              sx={{
                p: 1,
                display: "flex",
                alignItems: "center",
                gap: 1,
                borderColor: isCurrent ? "success.main" : "divider",
                bgcolor: isCurrent ? "success.50" : "background.paper",
              }}
            >
              <Chip size="small" label={`#${candidate.rank}`} sx={{ fontWeight: 700 }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                  {candidate.candidate_text}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                  {(candidate.evidence || []).map((e) => e.notes).filter(Boolean).join(" · ") ||
                    SOURCE_LABELS[candidate.source] ||
                    candidate.source}
                </Typography>
              </Box>
              {described && (
                <Tooltip
                  title={
                    described.calibrated
                      ? "Calibrated probability"
                      : "Not a calibrated probability — for ranking only"
                  }
                >
                  <Chip
                    size="small"
                    variant="outlined"
                    icon={!described.calibrated ? <HelpOutlined fontSize="small" /> : undefined}
                    label={`${described.label}: ${described.valueText}`}
                  />
                </Tooltip>
              )}
              {isCurrent ? (
                <Chip size="small" color="success" icon={<CheckCircleOutlined fontSize="small" />} label="Current" />
              ) : (
                <Button
                  size="small"
                  variant="outlined"
                  disabled={busy}
                  onClick={() => onAccept(candidate.candidate_text)}
                >
                  {candidate.rank === 1 ? "Accept" : "Choose"}
                </Button>
              )}
            </Paper>
          );
        })}
      </Stack>
    </Box>
  );
}
