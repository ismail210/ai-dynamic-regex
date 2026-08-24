import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { saveHumanSelection } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import {
  buildLocalSelectionOverlay,
  getResultKey,
  getSection,
  mergeResolvedPrediction,
} from "../lib/predictionContract";

const OTHER_VALUE = "__other__";

/**
 * Shared candidate/"Other" section-review control — the one place that
 * presents candidates, the currently-selected human value, manual
 * correction, save state, and validation errors. Used identically by
 * Results (PredictionDetailModal) and Drawing Review so a reviewer sees and
 * changes the exact same decision from either page, through the exact same
 * persistence path (api/client.saveHumanSelection -> human_review_selection
 * -> services.human_selections).
 *
 * Candidates always come from `result.candidate_sections` (whatever the
 * backend actually generated — HSS completion today, potentially other
 * families later) — this component never invents its own candidate list.
 */
export default function SectionReviewSelector({ result, documentId, onResolved, dense = false }) {
  const { setData } = useAnalysis();
  const candidates = result.candidate_sections || [];
  const resolvedValue = result.human_selected_section || null;
  const objectId = result.object_id || result.component_id;
  const docId = documentId || result.document_id;

  const initialChoice = () => {
    if (resolvedValue && candidates.some((c) => c.designation === resolvedValue)) {
      return { selected: resolvedValue, custom: "" };
    }
    if (resolvedValue) {
      // Persisted value isn't one of the generated candidates -- it was a
      // manual "Other" correction. Reopen with Other pre-selected and the
      // saved value already in the text field, not silently dropped.
      return { selected: OTHER_VALUE, custom: resolvedValue };
    }
    // Nothing resolved yet -- start the radio on the model's own top pick
    // when that pick is itself one of the real candidates, rather than an
    // arbitrary list position.
    const guess = getSection(result);
    if (guess && candidates.some((c) => c.designation === guess)) {
      return { selected: guess, custom: "" };
    }
    return { selected: candidates[0]?.designation || OTHER_VALUE, custom: "" };
  };

  const [choice, setChoice] = useState(initialChoice);
  const [editing, setEditing] = useState(!resolvedValue);
  const [status, setStatus] = useState("idle"); // idle | saving | error
  const [error, setError] = useState("");
  const lastSyncedResolvedValue = useRef(resolvedValue);

  // Resync when the persisted value changes for a reason OTHER than this
  // component's own save (e.g. the reviewer changed it from the other page
  // and shared analysis state was patched, or a fresh object was navigated
  // to) -- keyed on the primitive resolved value, not the result object
  // reference, so this never fights the component's own optimistic state.
  useEffect(() => {
    if (resolvedValue !== lastSyncedResolvedValue.current) {
      lastSyncedResolvedValue.current = resolvedValue;
      setChoice(initialChoice());
      setEditing(!resolvedValue);
      setStatus("idle");
      setError("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedValue, objectId]);

  if (!objectId) return null;

  const pendingSection =
    choice.selected === OTHER_VALUE ? choice.custom.trim().toUpperCase() : choice.selected;

  async function handleSave() {
    if (!pendingSection) {
      setError("Enter a section.");
      setStatus("error");
      return;
    }
    setStatus("saving");
    setError("");
    try {
      const response = await saveHumanSelection({
        documentId: docId,
        objectId,
        correctLabel: pendingSection,
        prediction: result,
        notes:
          choice.selected === OTHER_VALUE
            ? `Reviewer entered a corrected section for ${result.corrected_token || result.normalized_text || getSection(result)}`
            : `Reviewer selected ${pendingSection} for ${result.corrected_token || result.normalized_text || getSection(result)}`,
      });
      const resolved =
        response?.resolved_prediction || buildLocalSelectionOverlay(result, pendingSection);
      lastSyncedResolvedValue.current = resolved.human_selected_section || pendingSection;
      setData((current) => mergeResolvedPrediction(current, getResultKey(result), resolved));
      setStatus("idle");
      setEditing(false);
      onResolved?.(resolved);
    } catch (err) {
      setStatus("error");
      setError(
        err.friendlyMessage ||
          err?.response?.data?.detail ||
          err.message ||
          "Failed to save selection",
      );
    }
  }

  if (resolvedValue && !editing) {
    return (
      <Box>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          Selected section
        </Typography>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography fontFamily="monospace" fontSize={15} fontWeight={700}>
            {resolvedValue}
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
        {candidates.length ? "Possible catalog sections" : "Enter the correct section"}
      </Typography>
      {candidates.length > 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {result.review_reason ||
            "Every option below is a real catalog section — select the correct one, or enter a different one below."}
        </Typography>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {result.review_reason ||
            "No catalog candidates were generated automatically. Enter the correct catalog section."}
        </Typography>
      )}
      <FormControl fullWidth>
        <RadioGroup
          value={choice.selected}
          onChange={(e) => setChoice((c) => ({ ...c, selected: e.target.value }))}
        >
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
          <FormControlLabel
            value={OTHER_VALUE}
            control={<Radio size="small" />}
            label={<Typography fontSize={13}>Other / Enter corrected section</Typography>}
          />
        </RadioGroup>
      </FormControl>
      {choice.selected === OTHER_VALUE && (
        <TextField
          size="small"
          label="Correct section"
          placeholder="e.g. HSS10X10X5/8"
          value={choice.custom}
          onChange={(e) => setChoice((c) => ({ ...c, custom: e.target.value }))}
          inputProps={{ style: { fontFamily: "monospace" } }}
          sx={{ mt: 1, mb: 1, maxWidth: dense ? "100%" : 320 }}
          fullWidth={dense}
        />
      )}
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          variant="contained"
          disabled={status === "saving"}
          onClick={handleSave}
        >
          {resolvedValue ? "Save selection" : "Use this section"}
        </Button>
        {!dense && (
          <Typography variant="caption" color="text.secondary">
            The reviewer makes the final call — this does not overwrite the original OCR reading.
          </Typography>
        )}
      </Stack>
      {status === "error" && (
        <Alert severity="error" sx={{ mt: 1 }}>
          {error}
        </Alert>
      )}
    </Box>
  );
}
