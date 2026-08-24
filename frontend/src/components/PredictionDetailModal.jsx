import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  Grid,
  Radio,
  RadioGroup,
  Stack,
  Typography,
} from "@mui/material";
import { approveValidationCorrection } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import {
  getConfidence,
  getDisplaySection,
  getFamily,
  getCandidateSections,
  getEvidenceSummary,
  getSemanticCandidates,
  isHumanReviewed,
} from "../lib/predictionContract";
import PredictionExplainability from "./PredictionExplainability";


function Field({ label, children }) {
  return (
    <div>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography className="mono">{children || "—"}</Typography>
    </div>
  );
}

// Not part of {"approve", "edit", "correct"} in the backend's corrections
// endpoint (routers/engineering.py) -- a reviewer's completion choice is
// persisted (services.human_selections, served back by
// services.staged_pipeline._apply_human_selections) exactly like the
// existing Approve flow's training-data log, but deliberately does NOT
// advance the continuous-learning approval counter or trigger a retrain.
const HUMAN_SELECTION_DECISION = "human_review_selection";

/** Patches the one matching result in-place in the shared analysis data so
 * the table/section cell reflects a saved selection immediately, without a
 * refetch. Mirrors exactly what the backend overlay
 * (staged_pipeline._apply_human_selections) will also produce on the next
 * load, so an immediate refresh shows the same thing. */
function applyLocalSelection(data, objectId, section, semanticType = "") {
  if (!data?.results) return data;
  return {
    ...data,
    results: data.results.map((row) => {
      if ((row.object_id || row.component_id) !== objectId) return row;
      const canonical = row.canonical
        ? {
            ...row.canonical,
            prediction: {
              ...row.canonical.prediction,
              final_label: section,
              ...(semanticType ? { annotation_type: semanticType } : {}),
            },
            comparison: { ...row.canonical.comparison, match_status: "human_resolved" },
            needs_review: false,
            review_reason: null,
          }
        : row.canonical;
      return {
        ...row,
        section,
        human_selected_section: section,
        ...(semanticType ? { human_selected_semantic_type: semanticType } : {}),
        decision_source: "human_review",
        needs_review: false,
        review_reason: null,
        semantic_candidates: null,
        canonical,
        comparison: canonical?.comparison || row.comparison,
      };
    }),
  };
}

function CandidateSectionPicker({ result, alreadyResolved }) {
  const { data, setData } = useAnalysis();
  const candidates = getCandidateSections(result);
  const [selected, setSelected] = useState(
    result.human_selected_section || result.section || candidates[0]?.designation || ""
  );
  const [status, setStatus] = useState("idle"); // idle | saving | saved | error
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(!alreadyResolved);

  if (!candidates.length) return null;

  async function handleSave() {
    setStatus("saving");
    setError("");
    const objectId = result.object_id || result.component_id;
    try {
      await approveValidationCorrection({
        documentId: result.document_id,
        objectId,
        correctLabel: selected,
        prediction: result,
        userDecision: HUMAN_SELECTION_DECISION,
        notes: `Reviewer selected ${selected} for missing-thickness ${result.corrected_token || result.normalized_text}`,
      });
      setData((current) => applyLocalSelection(current, objectId, selected));
      setStatus("saved");
      setEditing(false);
    } catch (err) {
      setStatus("error");
      setError(err.friendlyMessage || err?.response?.data?.detail || err.message || "Failed to save selection");
    }
  }

  if (alreadyResolved && !editing) {
    return (
      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          Selected section
        </Typography>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Typography fontFamily="monospace" fontSize={15} fontWeight={700}>
            {result.human_selected_section || result.section}
          </Typography>
          <Chip size="small" color="success" variant="outlined" label="Human review" />
          <Button size="small" onClick={() => setEditing(true)}>
            Change selection
          </Button>
        </Stack>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={700} gutterBottom>
        Possible catalog sections
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Wall thickness is not present in the extracted designation
        {result.known_dimensions
          ? ` (dimensions ${result.known_dimensions.join(" x ")} confirmed)`
          : ""}
        . Every option below is a real catalog section for those dimensions —
        select the correct one.
      </Typography>
      <FormControl>
        <RadioGroup value={selected} onChange={(e) => setSelected(e.target.value)}>
          {candidates.map((candidate) => (
            <FormControlLabel
              key={candidate.designation}
              value={candidate.designation}
              control={<Radio size="small" />}
              label={
                <Typography fontFamily="monospace" fontSize={13}>
                  {candidate.designation}
                </Typography>
              }
            />
          ))}
        </RadioGroup>
      </FormControl>
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mt: 1.5 }}>
        <Button
          size="small"
          variant="contained"
          disabled={status === "saving"}
          onClick={handleSave}
        >
          Use this section
        </Button>
        <Typography variant="caption" color="text.secondary">
          The reviewer makes the final call — this does not overwrite the
          original OCR reading.
        </Typography>
      </Stack>
      {status === "error" && (
        <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>
      )}
    </Box>
  );
}

function SemanticCandidatePicker({ result, alreadyResolved }) {
  const { data, setData } = useAnalysis();
  const candidates = getSemanticCandidates(result);
  const [selected, setSelected] = useState(
    result.human_selected_section || candidates[0]?.label || "",
  );
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(!alreadyResolved);

  if (!candidates.length) return null;

  const selectedCandidate = candidates.find((c) => c.label === selected) || candidates[0];

  async function handleSave() {
    setStatus("saving");
    setError("");
    const objectId = result.object_id || result.component_id;
    try {
      await approveValidationCorrection({
        documentId: result.document_id,
        objectId,
        correctLabel: selected,
        prediction: result,
        userDecision: HUMAN_SELECTION_DECISION,
        semanticType: selectedCandidate?.type || "",
        notes: `Reviewer selected ${selectedCandidate?.type || "semantic"} interpretation for ${result.raw_text || result.original_token}`,
      });
      setData((current) =>
        applyLocalSelection(current, objectId, selected, selectedCandidate?.type || ""),
      );
      setStatus("saved");
      setEditing(false);
    } catch (err) {
      setStatus("error");
      setError(err.friendlyMessage || err?.response?.data?.detail || err.message || "Failed to save selection");
    }
  }

  if (alreadyResolved && !editing) {
    return (
      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          Selected interpretation
        </Typography>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Typography fontFamily="monospace" fontSize={15} fontWeight={700}>
            {result.human_selected_section || result.section}
          </Typography>
          <Chip size="small" color="success" variant="outlined" label="Human review" />
          <Button size="small" onClick={() => setEditing(true)}>
            Change selection
          </Button>
        </Stack>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={700} gutterBottom>
        Possible semantic interpretations
      </Typography>
      {getEvidenceSummary(result) && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Context: {getEvidenceSummary(result)}
        </Typography>
      )}
      <FormControl>
        <RadioGroup value={selected} onChange={(e) => setSelected(e.target.value)}>
          {candidates.map((candidate) => (
            <FormControlLabel
              key={`${candidate.type}-${candidate.label}`}
              value={candidate.label}
              control={<Radio size="small" />}
              label={
                <Stack spacing={0.25}>
                  <Typography fontFamily="monospace" fontSize={13}>
                    {candidate.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {candidate.type} · score {(candidate.score * 100).toFixed(0)}%
                    {candidate.evidence?.length ? ` · ${candidate.evidence.join(", ")}` : ""}
                  </Typography>
                </Stack>
              }
            />
          ))}
        </RadioGroup>
      </FormControl>
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mt: 1.5 }}>
        <Button size="small" variant="contained" disabled={status === "saving"} onClick={handleSave}>
          Use this interpretation
        </Button>
      </Stack>
      {status === "error" && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
    </Box>
  );
}

export default function PredictionDetailModal({ result, onClose }) {
  if (!result) return null;
  const display = getDisplaySection(result);
  const family = getFamily(result);
  const confidence = getConfidence(result);
  const candidateSections = getCandidateSections(result);
  const semanticCandidates = getSemanticCandidates(result);
  const showThicknessPicker = candidateSections.length > 0;
  const showSemanticPicker = semanticCandidates.length > 0;
  const alreadyResolved = Boolean(result.human_selected_section);
  const humanReviewed = isHumanReviewed(result);
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Prediction details</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Field label="ORIGINAL OCR">
                {result.raw_text || result.original_token || result.token}
              </Field>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Field label="NORMALIZED / CORRECTED OCR">
                {result.corrected_text || result.corrected_token || result.original_token || result.token}
              </Field>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Field label="NORMALIZED TEXT">{result.normalized_text}</Field>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Field label="PAGE">{result.page_number}</Field>
            </Grid>
            <Grid size={{ xs: 12, sm: 9 }}>
              <Field label="BOUNDING BOX">
                {(result.bounding_box || []).join(", ")}
              </Field>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Field label="PREDICTION SOURCE">
                {result.prediction_source || (result.evidence_source || []).join(", ")}
              </Field>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}><Field label="FAMILY">{family}</Field></Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Field label="SECTION">
                {display.reviewRequired ? (
                  <Chip size="small" color="warning" variant="outlined" label="Review required" />
                ) : (
                  display.value
                )}
              </Field>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Field label="CONFIDENCE">
                {display.reviewRequired || humanReviewed
                  ? "—"
                  : confidence.overall == null
                    ? confidence.level
                    : `${Math.round(Number(confidence.overall) * 100)}%`}
              </Field>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Field label="VALIDATION">
                {humanReviewed ? (
                  <Chip size="small" label="Human Reviewed" color="info" />
                ) : (
                  result.validation?.status || result.review_status
                )}
              </Field>
            </Grid>
          </Grid>
          {humanReviewed && (
            <Typography variant="caption" color="text.secondary">
              This section was selected by a reviewer, so confidence/match no
              longer apply to the final answer. The model's original
              prediction and evidence are preserved below for audit.
            </Typography>
          )}
          {showSemanticPicker && (
            <>
              <Divider />
              <SemanticCandidatePicker result={result} alreadyResolved={alreadyResolved} />
            </>
          )}
          {showThicknessPicker && (
            <>
              <Divider />
              <CandidateSectionPicker result={result} alreadyResolved={alreadyResolved} />
            </>
          )}
          <Divider />
          <PredictionExplainability result={result} />
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
