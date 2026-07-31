import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  Grid,
  Skeleton,
  Snackbar,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import {
  CheckCircleRounded,
  ModelTrainingOutlined,
  RefreshRounded,
  SpeedRounded,
} from "@mui/icons-material";
import {
  getRetrainStatus,
  getStatistics,
  startRetrain,
} from "../api/client";
import { useThemeMode } from "../context/ThemeContext";
import PageHeader from "../components/ui/PageHeader";
import RetrainProgressDialog from "../components/RetrainProgressDialog";

const percent = (value) =>
  value == null
    ? "—"
    : `${(Number(value) * (Number(value) <= 1 ? 100 : 1)).toFixed(2)}%`;

export default function SettingsPage() {
  const [stats, setStats] = useState(null);
  const [retrain, setRetrain] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [snack, setSnack] = useState(false);
  const timer = useRef(null);
  const { mode, toggleMode } = useThemeMode();

  const refresh = useCallback(async () => {
    try {
      setStats(await getStatistics());
      setError("");
    } catch {
      setError("System information could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  const stopPolling = () => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
  };

  const pollStatus = useCallback(async () => {
    try {
      const status = await getRetrainStatus();
      setRetrain(status);
      if (status.status === "succeeded" || status.status === "failed") {
        stopPolling();
        if (status.status === "succeeded") {
          setSnack(true);
          refresh();
        }
      }
    } catch {
      stopPolling();
      setRetrain((current) => ({
        ...current,
        status: "failed",
        error: "Lost connection while checking retrain progress.",
      }));
    }
  }, [refresh]);

  useEffect(() => {
    let active = true;
    refresh();
    getRetrainStatus()
      .then((status) => {
        if (active && status.status === "running") {
          setRetrain(status);
          setDialogOpen(true);
          timer.current = window.setInterval(pollStatus, 1000);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
      stopPolling();
    };
  }, [pollStatus, refresh]);

  const run = async () => {
    setError("");
    try {
      const status = await startRetrain();
      setRetrain(status);
      setDialogOpen(true);
      stopPolling();
      timer.current = window.setInterval(pollStatus, 1000);
    } catch (e) {
      setError(e?.response?.data?.detail || "Retrain could not be started.");
    }
  };

  const meta = stats?.model_meta || {};
  const running = retrain?.status === "running";

  return (
    <Box sx={{ minWidth: 0 }}>
      <PageHeader
        title="Settings"
        subtitle="Workspace preferences and production model controls"
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2.5 }} onClose={() => setError("")}>
          {error}
        </Alert>
      )}

      {loading && !stats ? (
        <Grid container spacing={2.5}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Skeleton variant="rounded" height={320} />
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Skeleton variant="rounded" height={320} />
          </Grid>
        </Grid>
      ) : (
      <Grid container spacing={2.5} alignItems="stretch">
        <Grid size={{ xs: 12, lg: 8 }}>
          <Card sx={{ height: "100%" }}>
            <CardContent sx={{ p: 3, "&:last-child": { pb: 3 } }}>
              <Stack
                direction={{ xs: "column", sm: "row" }}
                justifyContent="space-between"
                alignItems={{ sm: "flex-start" }}
                spacing={2}
              >
                <Stack direction="row" spacing={1.5}>
                  <Box className="icon-surface">
                    <ModelTrainingOutlined />
                  </Box>
                  <Box>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="h6">Production model</Typography>
                      <Chip
                        size="small"
                        color="success"
                        icon={<CheckCircleRounded />}
                        label="Active"
                      />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" mt={0.35}>
                      Fast retraining uses the established XGBoost classifier only.
                    </Typography>
                  </Box>
                </Stack>
                <Button
                  variant="contained"
                  startIcon={running ? <RefreshRounded /> : <SpeedRounded />}
                  onClick={running ? () => setDialogOpen(true) : run}
                >
                  {running ? "View progress" : "Retrain XGBoost"}
                </Button>
              </Stack>

              <Grid container spacing={1.5} mt={2.5}>
                {[
                  ["Model", stats?.current_model || "XGBoost"],
                  ["Accuracy", percent(meta.accuracy ?? stats?.current_accuracy)],
                  ["F1 score", percent(meta.f1)],
                  ["Classes", meta.n_classes ?? stats?.n_classes],
                  ["Training samples", meta.samples_total ?? meta.rows],
                  ["Approved samples", stats?.approved_tokens ?? 0],
                ].map(([label, value]) => (
                  <Grid size={{ xs: 6, md: 4 }} key={label}>
                    <Box className="metric-tile">
                      <Typography variant="caption" color="text.secondary">
                        {label}
                      </Typography>
                      {stats ? (
                        <Typography fontWeight={700} mt={0.5} sx={{ fontVariantNumeric: "tabular-nums" }}>
                          {value ?? "—"}
                        </Typography>
                      ) : (
                        <Skeleton width="60%" />
                      )}
                    </Box>
                  </Grid>
                ))}
              </Grid>

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
                <Typography variant="body2" fontWeight={650}>
                  What happens during retraining
                </Typography>
                <Typography variant="body2" color="text.secondary" mt={0.5}>
                  Approved samples are merged with the base dataset, engineered
                  features and preprocessing are regenerated, XGBoost is trained,
                  artifacts are saved atomically, and the production model reloads.
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, lg: 4 }}>
          <Card sx={{ height: "100%" }}>
            <CardContent sx={{ p: 3, "&:last-child": { pb: 3 } }}>
              <Typography variant="h6">Workspace</Typography>
              <Typography variant="body2" color="text.secondary" mt={0.5} mb={2.5}>
                Appearance and runtime information.
              </Typography>

              <FormControlLabel
                sx={{ m: 0, width: "100%", justifyContent: "space-between" }}
                labelPlacement="start"
                control={<Switch checked={mode === "dark"} onChange={toggleMode} />}
                label={
                  <Box>
                    <Typography fontWeight={650} fontSize={13.5}>
                      Dark theme
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Optimized for technical drawings
                    </Typography>
                  </Box>
                }
              />

              <Stack spacing={1.5} mt={3}>
                <InfoRow label="API version" value={stats?.api_version} />
                <InfoRow
                  label="Auto-accept threshold"
                  value={
                    stats?.auto_accept_threshold != null
                      ? percent(stats.auto_accept_threshold)
                      : "—"
                  }
                />
                <InfoRow
                  label="Last retraining"
                  value={
                    stats?.training_date
                      ? new Date(stats.training_date).toLocaleString()
                      : "Baseline"
                  }
                />
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      )}

      <RetrainProgressDialog
        open={dialogOpen}
        status={retrain}
        onClose={() => setDialogOpen(false)}
      />

      <Snackbar
        open={snack}
        autoHideDuration={4500}
        onClose={() => setSnack(false)}
        message="XGBoost retrained and loaded successfully"
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      />
    </Box>
  );
}

function InfoRow({ label, value }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={650} textAlign="right">
        {value ?? "—"}
      </Typography>
    </Stack>
  );
}
