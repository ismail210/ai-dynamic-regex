import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import {
  CheckCircleRounded,
  ErrorOutlineRounded,
  ModelTrainingOutlined,
} from "@mui/icons-material";

function formatDuration(seconds) {
  if (seconds == null) return "Calculating…";
  if (seconds <= 5) return "Less than 10 seconds";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `About ${minutes}m ${remainder}s` : `About ${remainder}s`;
}

export default function RetrainProgressDialog({ open, status, onClose }) {
  const running = status?.status === "running";
  const succeeded = status?.status === "succeeded";
  const failed = status?.status === "failed";
  const progress = Number(status?.progress || 0);

  return (
    <Dialog
      open={open}
      onClose={running ? undefined : onClose}
      disableEscapeKeyDown={running}
      fullWidth
      maxWidth="sm"
      PaperProps={{ sx: { overflow: "hidden" } }}
    >
      <Box
        sx={{
          height: 3,
          bgcolor: failed ? "error.main" : succeeded ? "success.main" : "primary.main",
        }}
      />
      <DialogTitle sx={{ px: 3, pt: 3, pb: 1 }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: 2,
              display: "grid",
              placeItems: "center",
              color: failed ? "error.main" : succeeded ? "success.main" : "primary.main",
              bgcolor: failed
                ? "error.main"
                : succeeded
                  ? "success.main"
                  : "primary.main",
              backgroundColor: "color-mix(in srgb, currentColor 12%, transparent)",
            }}
          >
            {failed ? (
              <ErrorOutlineRounded />
            ) : succeeded ? (
              <CheckCircleRounded />
            ) : (
              <ModelTrainingOutlined />
            )}
          </Box>
          <Box>
            <Typography variant="h6">
              {failed ? "Retrain failed" : succeeded ? "Model updated" : "Retraining XGBoost"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {failed
                ? "The production model was not changed."
                : succeeded
                  ? "The new model is loaded and ready."
                  : "The application remains available while this runs."}
            </Typography>
          </Box>
        </Stack>
      </DialogTitle>

      <DialogContent sx={{ px: 3, pt: 2.5, pb: 2 }}>
        {!failed && (
          <>
            <Stack direction="row" mb={1} sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
              <Typography fontWeight={650} fontSize={13}>
                {status?.step || "Preparing retrain"}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
                {progress}%
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={progress}
              color={succeeded ? "success" : "primary"}
              sx={{ height: 7, borderRadius: 99 }}
            />
          </>
        )}

        <Box
          sx={{
            mt: 2.5,
            p: 2,
            borderRadius: 2,
            bgcolor: "action.hover",
            border: 1,
            borderColor: "divider",
          }}
        >
          <Stack
            direction={{ xs: "column", sm: "row" }}
            divider={<Box sx={{ width: 1, bgcolor: "divider" }} />}
            spacing={2}
          >
            <Box flex={1}>
              <Typography variant="caption" color="text.secondary">
                Approved samples
              </Typography>
              <Typography fontWeight={700} sx={{ fontVariantNumeric: "tabular-nums" }}>
                {status?.approved_samples ?? 0}
              </Typography>
            </Box>
            <Box flex={1}>
              <Typography variant="caption" color="text.secondary">
                Merged samples
              </Typography>
              <Typography fontWeight={700} sx={{ fontVariantNumeric: "tabular-nums" }}>
                {status?.total_samples ?? "—"}
              </Typography>
            </Box>
            <Box flex={1}>
              <Typography variant="caption" color="text.secondary">
                Estimated remaining
              </Typography>
              <Typography fontWeight={700} fontSize={13}>
                {succeeded ? "Complete" : formatDuration(status?.estimated_remaining_seconds)}
              </Typography>
            </Box>
          </Stack>
        </Box>

        {running && (
          <Stack direction="row" spacing={1} mt={2.5} useFlexGap sx={{ flexWrap: "wrap" }}>
            {["Merge data", "Build features", "Train XGBoost", "Reload model"].map(
              (label, index) => {
                const thresholds = [5, 25, 40, 97];
                const complete = progress > thresholds[index];
                return (
                  <Chip
                    key={label}
                    size="small"
                    variant={complete ? "filled" : "outlined"}
                    color={complete ? "success" : "default"}
                    label={label}
                  />
                );
              }
            )}
          </Stack>
        )}

        {failed && (
          <Box
            sx={{
              mt: 1,
              p: 2,
              borderRadius: 2,
              bgcolor: "error.main",
              backgroundColor: "color-mix(in srgb, currentColor 9%, transparent)",
            }}
          >
            <Typography variant="body2">{status?.error || "Retrain failed."}</Typography>
          </Box>
        )}
      </DialogContent>

      {!running && (
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button variant="contained" color={failed ? "error" : "primary"} onClick={onClose}>
            {failed ? "Close" : "Done"}
          </Button>
        </DialogActions>
      )}
    </Dialog>
  );
}
