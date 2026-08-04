import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Chip,
  Divider,
  Grid,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { ExpandMoreOutlined } from "@mui/icons-material";
import {
  getCanonicalPrediction,
  getConfidence,
  getDisplayConfidence,
  getExplanation,
  getFamily,
  getSection,
  isLegacyPrediction,
  LEGACY_PROVENANCE_MESSAGE,
} from "../lib/predictionContract";
import MatchStatusBadge from "./ui/MatchStatusBadge";

function percent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : "—";
}

/** Render known evidence detail keys as labeled fields instead of a raw JSON
 * dump; anything left over (backend evolves fast) still surfaces, collapsed,
 * so no information is silently hidden. */
const KNOWN_DETAIL_LABELS = {
  extraction_confidence: "Extraction confidence",
  original_token: "Original token",
  corrected_token: "Corrected token",
  matched_neighbors: "Matched neighbors",
  object: "Object",
  similarity: "Similarity",
  source: "Source",
  degree: "Graph degree",
  structural_links: "Structural links",
  min_distance: "Min distance",
  consistency: "Consistency",
  member_role: "Member role",
  material_grade: "Material grade",
  findings: "Rule findings",
};

function formatDetailValue(value) {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) {
    if (!value.length) return "—";
    if (typeof value[0] === "object") return null; // fall through to JSON
    return value.join(", ");
  }
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "—";
  if (typeof value === "object") return null;
  return String(value);
}

function DetailFields({ details }) {
  const entries = Object.entries(details || {});
  if (!entries.length) return null;
  const simple = [];
  const complex = [];
  for (const [key, value] of entries) {
    const formatted = formatDetailValue(value);
    if (formatted === null) complex.push([key, value]);
    else simple.push([key, formatted]);
  }
  return (
    <Stack spacing={0.5} mt={1}>
      {simple.map(([key, formatted]) => (
        <Stack key={key} direction="row" gap={1} sx={{ justifyContent: "space-between" }}>
          <Typography variant="caption" color="text.secondary">
            {KNOWN_DETAIL_LABELS[key] || key}
          </Typography>
          <Typography variant="caption" fontFamily="monospace">
            {formatted}
          </Typography>
        </Stack>
      ))}
      {complex.length > 0 && (
        <Accordion disableGutters variant="outlined" sx={{ "&:before": { display: "none" } }}>
          <AccordionSummary expandIcon={<ExpandMoreOutlined fontSize="small" />}>
            <Typography variant="caption" color="text.secondary">
              {complex.length} additional detail field{complex.length > 1 ? "s" : ""}
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            {complex.map(([key, value]) => (
              <Box key={key} mb={1}>
                <Typography variant="caption" fontWeight={700} color="text.secondary">
                  {KNOWN_DETAIL_LABELS[key] || key}
                </Typography>
                <Typography
                  component="pre"
                  variant="caption"
                  color="text.secondary"
                  sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", m: 0 }}
                >
                  {JSON.stringify(value, null, 2)}
                </Typography>
              </Box>
            ))}
          </AccordionDetails>
        </Accordion>
      )}
    </Stack>
  );
}

function Evidence({ label, evidence, fallbackScore }) {
  const score = evidence?.score ?? fallbackScore;
  const available = evidence?.available !== false;
  return (
    <Paper variant="outlined" sx={{ p: 1.5, height: "100%" }}>
      <Stack
        direction="row"
        mb={0.75}
        sx={{ justifyContent: "space-between", alignItems: "center" }}
      >
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
      <DetailFields details={evidence?.details} />
    </Paper>
  );
}

function SourceVsPrediction({ canonical, section, family, isLegacy }) {
  const { sourceText, comparison } = canonical;
  const raw = sourceText.raw;
  const hasRaw = sourceText.available && raw;
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      {isLegacy && (
        <Alert severity="info" variant="outlined" sx={{ mb: 1.5 }}>
          {LEGACY_PROVENANCE_MESSAGE}
        </Alert>
      )}
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ alignItems: { sm: "center" } }}
      >
        <Box flex={1}>
          <Typography variant="caption" color="text.secondary">ORIGINAL PDF TEXT</Typography>
          <Typography fontFamily="monospace" fontWeight={700}>
            {hasRaw ? raw : "Not available from source"}
          </Typography>
          {hasRaw && sourceText.page_number != null && (
            <Typography variant="caption" color="text.secondary">
              Page {sourceText.page_number}
              {sourceText.bounding_box ? " · location captured" : " · location unavailable"}
            </Typography>
          )}
        </Box>
        <Box flex={1}>
          <Typography variant="caption" color="text.secondary">FINAL INTERPRETED LABEL</Typography>
          <Typography fontFamily="monospace" fontWeight={800}>
            {[family, section].filter(Boolean).join(" · ") || "Unclassified"}
          </Typography>
        </Box>
        <Box>
          <MatchStatusBadge matchStatus={comparison.match_status} isLegacy={isLegacy} />
        </Box>
      </Stack>
      {!isLegacy && comparison.match_status !== "exact_match" && hasRaw && (
        <Typography variant="caption" color="text.secondary" display="block" mt={1}>
          Original PDF wording is always preserved above — the badge explains why it differs
          from the final label.
        </Typography>
      )}
    </Paper>
  );
}

function CandidateList({ candidates, section }) {
  if (!candidates.length) return null;
  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={750} mb={0.75}>
        Ranked candidates
      </Typography>
      <Stack spacing={0.75}>
        {candidates.slice(0, 8).map((candidate) => (
          <Paper
            key={candidate.label}
            variant="outlined"
            sx={{
              p: 1,
              borderColor:
                candidate.label === section ? "primary.main" : undefined,
            }}
          >
            <Stack
              direction="row"
              gap={0.5}
              sx={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}
            >
              <Typography fontFamily="monospace" fontWeight={700}>
                {candidate.label}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                {candidate.catalog_valid && (
                  <Chip size="small" label="In AISC catalog" color="success" variant="outlined" />
                )}
                {candidate.mask_match && (
                  <Chip size="small" label="Wildcard mask match" color="info" variant="outlined" />
                )}
                <Chip size="small" label={`score ${percent(candidate.combined_score)}`} />
              </Stack>
            </Stack>
            {candidate.match_reasons?.length > 0 && (
              <Typography variant="caption" color="text.secondary">
                {candidate.match_reasons.join(" · ")}
              </Typography>
            )}
          </Paper>
        ))}
      </Stack>
    </Box>
  );
}

export default function PredictionExplainability({ result, compact = false }) {
  if (!result) return null;
  const explanation = getExplanation(result);
  const legacyConfidence = getConfidence(result);
  const display = getDisplayConfidence(result);
  const canonical = getCanonicalPrediction(result);
  const section = getSection(result);
  const family = getFamily(result);
  const rejected = explanation.why_rejected || [];
  const legacy = isLegacyPrediction(result);

  return (
    <Stack spacing={compact ? 1.5 : 2}>
      <SourceVsPrediction canonical={canonical} section={section} family={family} isLegacy={legacy} />

      <Grid container spacing={1.25}>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="caption" color="text.secondary">PREDICTION</Typography>
          <Typography fontFamily="monospace" fontWeight={800}>
            {[family, section].filter(Boolean).join(" · ") || "Unclassified"}
          </Typography>
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="caption" color="text.secondary">
            {display.isCalibrated ? "CALIBRATED CONFIDENCE" : "RANKING SCORE (uncalibrated)"}
          </Typography>
          <Typography fontWeight={750}>
            {legacyConfidence.level} · {percent(display.value)}
          </Typography>
          {!display.isCalibrated && (
            <Typography variant="caption" color="text.secondary">
              Not a calibrated probability — see relative candidate ranking below.
            </Typography>
          )}
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Typography variant="caption" color="text.secondary">REVIEW</Typography>
          <Typography variant="body2">
            {legacy
              ? "Legacy record — re-analyze to determine review status."
              : canonical.needsReview
                ? canonical.reviewReason || "Flagged for review."
                : "No review required."}
          </Typography>
        </Grid>
      </Grid>

      <Divider />

      <CandidateList candidates={canonical.candidates} section={section} />

      {!canonical.candidates.length && (
        <Box>
          <Typography variant="subtitle2" fontWeight={750} mb={0.75}>
            Top candidate sections
          </Typography>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
            {(explanation.top_candidate_sections || []).length > 0 ? (
              explanation.top_candidate_sections.slice(0, 8).map((candidate, index) => (
                <Chip
                  key={`${candidate.shape || candidate.section}-${index}`}
                  size="small"
                  color={String(candidate.shape || candidate.section) === String(section) ? "primary" : "default"}
                  variant={String(candidate.shape || candidate.section) === String(section) ? "filled" : "outlined"}
                  label={`${candidate.shape || candidate.section} ${percent(candidate.score ?? candidate.confidence)}`}
                />
              ))
            ) : (
              <Typography variant="body2" color="text.secondary">No ranked alternatives recorded.</Typography>
            )}
          </Stack>
        </Box>
      )}

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
          <Evidence label="Text evidence" evidence={explanation.text_evidence} fallbackScore={explanation.text_similarity} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence label="OCR evidence" evidence={explanation.ocr_evidence} fallbackScore={explanation.ocr_score} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence label="Layout evidence" evidence={explanation.layout_evidence} fallbackScore={explanation.layout_score} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence label="Geometry evidence" evidence={explanation.geometry_evidence} fallbackScore={explanation.geometry_similarity} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence label="Graph evidence" evidence={explanation.graph_evidence} fallbackScore={explanation.graph_consistency} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Evidence label="Engineering evidence" evidence={explanation.engineering_evidence} fallbackScore={explanation.engineering_evidence?.score} />
        </Grid>
      </Grid>

      {(explanation.matched_neighbors || []).length > 0 && (
        <Box>
          <Typography variant="subtitle2" fontWeight={750} mb={0.75}>
            Matched neighbors
          </Typography>
          <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap" }}>
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

      {!legacy && !explanation.summary && !explanation.why_selected?.length && (
        <Alert severity="info" variant="outlined">
          This legacy prediction predates the explainability v2 contract.
        </Alert>
      )}
    </Stack>
  );
}
