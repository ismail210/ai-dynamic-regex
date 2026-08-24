import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { PlaceOutlined } from "@mui/icons-material";
import {
  getConfidence,
  getDisplaySection,
  getFamily,
  getPredictionLocation,
  isHumanReviewed,
  isSectionReviewEligible,
  reviewOnDrawingPath,
} from "../lib/predictionContract";
import PredictionExplainability from "./PredictionExplainability";
import SectionReviewSelector from "./SectionReviewSelector";


function Field({ label, children }) {
  return (
    <div>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography className="mono">{children || "—"}</Typography>
    </div>
  );
}

export default function PredictionDetailModal({ result, onClose }) {
  const navigate = useNavigate();
  if (!result) return null;
  const display = getDisplaySection(result);
  const family = getFamily(result);
  const confidence = getConfidence(result);
  const humanReviewed = isHumanReviewed(result);
  const hasLocation = getPredictionLocation(result).hasLocation;
  const showSectionReview = isSectionReviewEligible(result);
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Prediction details</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          {hasLocation && (
            <Button
              size="small"
              variant="outlined"
              startIcon={<PlaceOutlined />}
              sx={{ alignSelf: "flex-start" }}
              onClick={() => {
                const path = reviewOnDrawingPath(result);
                onClose?.();
                navigate(path);
              }}
            >
              Review on drawing
            </Button>
          )}
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
          {showSectionReview && (
            <>
              <Divider />
              <SectionReviewSelector result={result} />
            </>
          )}
          <Divider />
          <PredictionExplainability result={result} />
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
