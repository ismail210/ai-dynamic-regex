import { Dialog, DialogContent, DialogTitle, Divider, Grid, Stack, Typography } from "@mui/material";
import { getConfidence, getFamily, getSection } from "../lib/predictionContract";
import PredictionExplainability from "./PredictionExplainability";


function Field({ label, children }) {
  return (
    <div>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography className="mono">{children || "—"}</Typography>
    </div>
  );
}


export default function PredictionDetailModal({ result, onClose }) {
  if (!result) return null;
  const section = getSection(result);
  const family = getFamily(result);
  const confidence = getConfidence(result);
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
              <Field label="CORRECTED OCR">
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
            <Grid size={{ xs: 6, sm: 3 }}><Field label="SECTION">{section}</Field></Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Field label="CONFIDENCE">
                {confidence.overall == null
                  ? confidence.level
                  : `${Math.round(Number(confidence.overall) * 100)}%`}
              </Field>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <Field label="VALIDATION">
                {result.validation?.status || result.review_status}
              </Field>
            </Grid>
          </Grid>
          <Divider />
          <PredictionExplainability result={result} />
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
