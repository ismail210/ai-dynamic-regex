import {
  Alert,
  Box,
  Chip,
  Divider,
  Grid,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import {
  getConfidence,
  getExplanation,
  getFamily,
  getSection,
} from "../lib/predictionContract";

function percent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : "—";
}

function Evidence({ label, evidence, fallbackScore }) {
  const score = evidence?.score ?? fallbackScore;
  const available = evidence?.available !== false;
  const details = evidence?.details || {};
  return (
    <Paper variant="outlined" sx={{ p: 1.5, height: "100%" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.75}>
        <Typography variant="subtitle2" fontWeight={750}>{label}</Typography>
        <Chip
          size="small"
          label={available ? percent(score) : "Unavailable"}
          color={available ? "primary" : "default"}
          variant="outlined"
        />
      </Stack>
      {available && Number.isFinite(Number(score)) && (
        <LinearProgress
          variant="determinate"
          value={Math.max(0, Math.min(100, Number(score) * 100))}
          sx={{ mb: 1 }}
        />
      )}
      <Typography variant="body2" color="text.secondary">
        {evidence?.summary || (available ? "Evidence contributed to fusion." : "No evidence linked.")}
      </Typography>
      {Object.keys(details).length > 0 && (
        <Typography
          component="pre"
          variant="caption"
          color="text.secondary"
          sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0, mt: 1 }}
        >
          {JSON.stringify(details, null, 2)}
        </Typography>
      )}
    </Paper>
  );
}

export default function PredictionExplainability({ result, compact = false }) {
  if (!result) return null;
  const explanation = getExplanation(result);
  const confidence = getConfidence(result);
  const section = getSection(result);
  const family = getFamily(result);
  const candidates = explanation.top_candidate_sections || [];
  const rejected = explanation.why_rejected || [];

  return (
    <Stack spacing={compact ? 1.5 : 2}>
      <Grid container spacing={1.25}>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="caption" color="text.secondary">PREDICTION</Typography>
          <Typography fontFamily="monospace" fontWeight={800}>
            {[family, section].filter(Boolean).join(" · ") || "Unclassified"}
          </Typography>
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="caption" color="text.secondary">CONFIDENCE</Typography>
          <Typography fontWeight={750}>
            {confidence.level} · {percent(confidence.overall)}
          </Typography>
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="caption" color="text.secondary">EXPLANATION CONTRACT</Typography>
          <Typography variant="body2">v{explanation.schema_version || result.schema_version || "1.0"}</Typography>
        </Grid>
      </Grid>

      <Divider />

      <Box>
        <Typography variant="subtitle2" fontWeight={750} mb={0.75}>
          Top candidate sections
        </Typography>
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
          {candidates.length > 0 ? candidates.slice(0, 8).map((candidate, index) => (
            <Chip
              key={`${candidate.shape || candidate.section}-${index}`}
              size="small"
              color={String(candidate.shape || candidate.section) === String(section) ? "primary" : "default"}
              variant={String(candidate.shape || candidate.section) === String(section) ? "filled" : "outlined"}
              label={`${candidate.shape || candidate.section} ${percent(candidate.score ?? candidate.confidence)}`}
            />
          )) : (
            <Typography variant="body2" color="text.secondary">No ranked alternatives recorded.</Typography>
          )}
        </Stack>
      </Box>

      <Grid container spacing={1.5}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography variant="subtitle2" fontWeight={750} mb={0.75}>Why selected</Typography>
          <Stack spacing={0.5}>
            {(explanation.why_selected || []).map((reason, index) => (
              <Typography key={index} variant="body2">• {reason}</Typography>
            ))}
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography variant="subtitle2" fontWeight={750} mb={0.75}>Why rejected</Typography>
          <Stack spacing={0.75}>
            {rejected.length > 0 ? rejected.slice(0, 6).map((candidate) => (
              <Box key={candidate.section}>
                <Typography variant="body2" fontFamily="monospace" fontWeight={700}>
                  {candidate.section} · {percent(candidate.score)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {(candidate.reasons || []).join(" ")}
                </Typography>
              </Box>
            )) : (
              <Typography variant="body2" color="text.secondary">No rejected candidates recorded.</Typography>
            )}
          </Stack>
        </Grid>
      </Grid>

      <Grid container spacing={1.25}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence
            label="Text evidence"
            evidence={explanation.text_evidence}
            fallbackScore={explanation.text_similarity}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence
            label="OCR evidence"
            evidence={explanation.ocr_evidence}
            fallbackScore={explanation.ocr_score}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence
            label="Layout evidence"
            evidence={explanation.layout_evidence}
            fallbackScore={explanation.layout_score}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence
            label="Geometry evidence"
            evidence={explanation.geometry_evidence}
            fallbackScore={explanation.geometry_similarity}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence
            label="Graph evidence"
            evidence={explanation.graph_evidence}
            fallbackScore={explanation.graph_consistency}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence
            label="Engineering evidence"
            evidence={explanation.engineering_evidence}
            fallbackScore={explanation.engineering_evidence?.score}
          />
        </Grid>
      </Grid>

      {(explanation.matched_neighbors || []).length > 0 && (
        <Box>
          <Typography variant="subtitle2" fontWeight={750} mb={0.75}>
            Matched neighbors
          </Typography>
          <Stack direction="row" gap={0.75} flexWrap="wrap">
            {explanation.matched_neighbors.map((neighbor, index) => (
              <Chip key={`${neighbor}-${index}`} size="small" label={neighbor} />
            ))}
          </Stack>
        </Box>
      )}

      {(explanation.correction_history || []).length > 0 && (
        <Box>
          <Typography variant="subtitle2" fontWeight={750} mb={0.75}>
            Correction history
          </Typography>
          {(explanation.correction_history || []).map((item, index) => (
            <Typography key={index} variant="body2" color="text.secondary">
              {item.original || item.token || "Reviewed example"} →{" "}
              {item.corrected || item.label || item.reviewed_class || "—"}
            </Typography>
          ))}
        </Box>
      )}

      {!explanation.summary && !explanation.why_selected?.length && (
        <Alert severity="info" variant="outlined">
          This legacy prediction predates the explainability v2 contract.
        </Alert>
      )}
    </Stack>
  );
}
