import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import { PlayArrowRounded, RefreshRounded } from "@mui/icons-material";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";
import RetrainProgressDialog from "../components/RetrainProgressDialog";
import {
  buildPairedDataset,
  getContinuousLearningStatus,
  getDataQuality,
  getPairedDatasetSummary,
  getRetrainStatus,
  getStatistics,
  startRetrain,
} from "../api/client";

function Tile({ label, value }) {
  return (
    <Box className="metric-tile">
      <Typography variant="caption" color="text.secondary" fontWeight={700}>
        {label}
      </Typography>
      <Typography variant="h5" fontWeight={720} mt={0.75}>
        {value ?? "—"}
      </Typography>
    </Box>
  );
}

export default function TrainingPage() {
  const [stats, setStats] = useState(null);
  const [paired, setPaired] = useState(null);
  const [quality, setQuality] = useState(null);
  const [learning, setLearning] = useState(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [retrain, setRetrain] = useState(null);
  const timer = useRef(null);

  const stopPolling = () => {
    if (timer.current) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [s, p, q, c] = await Promise.all([
        getStatistics(),
        getPairedDatasetSummary(),
        getDataQuality(),
        getContinuousLearningStatus(),
      ]);
      setStats(s);
      setPaired(p);
      setQuality(q);
      setLearning(c);
    } catch {
      setError("Failed to load training workspace.");
    } finally {
      setLoading(false);
    }
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const status = await getRetrainStatus();
      setRetrain(status);
      if (status?.status === "succeeded" || status?.status === "failed") {
        stopPolling();
        if (status?.status === "succeeded") refresh();
      }
    } catch {
      /* ignore transient poll errors */
    }
  }, [refresh]);

  useEffect(() => {
    refresh();
    return () => stopPolling();
  }, [refresh]);

  async function onBuildPaired() {
    setBuilding(true);
    setMessage("");
    try {
      const result = await buildPairedDataset();
      setMessage(`Built paired dataset: ${result.row_count} rows from ${result.pair_count} pairs.`);
      await refresh();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "Dataset build failed");
    } finally {
      setBuilding(false);
    }
  }

  async function onStartRetrain() {
    setError("");
    try {
      const status = await startRetrain();
      setRetrain(status);
      setDialogOpen(true);
      stopPolling();
      timer.current = window.setInterval(pollStatus, 1000);
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not start retrain");
    }
  }

  const meta = stats?.model_meta || {};
  const metrics = meta.metrics || stats?.metrics || {};
  const aug = stats?.augmentation || {};
  const pairedMeta = paired?.meta || {};

  if (loading && !stats) {
    return (
      <Box>
        <PageHeader title="Training" subtitle="Paired datasets, features, and model retrain controls" />
        <Grid container spacing={1.5}>
          {[1, 2, 3, 4].map((i) => (
            <Grid size={{ xs: 6, md: 3 }} key={i}>
              <Skeleton variant="rounded" height={90} />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  return (
    <Box>
      <PageHeader
        title="Training"
        subtitle="Continuous learning across text, geometry, graph, and fusion datasets with versioned models and quality-gated promotion."
        actions={
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button variant="outlined" startIcon={<RefreshRounded />} onClick={refresh}>
              Refresh
            </Button>
            <Button variant="outlined" onClick={onBuildPaired} disabled={building}>
              Build paired dataset
            </Button>
            <Button variant="contained" startIcon={<PlayArrowRounded />} onClick={onStartRetrain}>
              Run continuous learning
            </Button>
          </Stack>
        }
      />

      {building && <LinearProgress sx={{ mb: 2 }} />}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError("")}>
          {error}
        </Alert>
      )}
      {message && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMessage("")}>
          {message}
        </Alert>
      )}

      <Grid container spacing={1.5} mb={2.5}>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile label="Pending approvals" value={learning?.pending_approved_count ?? 0} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile
            label="Trigger threshold"
            value={`${learning?.pending_approved_count ?? 0} / ${learning?.threshold ?? 25}`}
          />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile
            label="CL ready"
            value={learning?.ready_for_trigger ? "Yes" : "No"}
          />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile label="Data quality" value={(quality?.status || "—").toString().toUpperCase()} />
        </Grid>
      </Grid>

      {learning?.sources && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Sources ingested: approved {learning.sources.sources?.approved_review || 0},
          corrections {learning.sources.sources?.corrected_prediction || 0},
          historical {learning.sources.sources?.historical_aisc || 0},
          Excel/paired {learning.sources.sources?.excel_takeoff || 0},
          artifacts {learning.sources.sources?.engineering_artifacts || 0}.
          Modalities — text {learning.sources.modality_counts?.text || 0},
          geometry {learning.sources.modality_counts?.geometry || 0},
          graph {learning.sources.modality_counts?.graph || 0},
          fusion {learning.sources.modality_counts?.fusion || 0}.
        </Alert>
      )}

      <Grid container spacing={2} mb={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1.5}>
                Dataset versions
              </Typography>
              <Stack spacing={1}>
                {["text", "geometry", "graph", "fusion"].map((modality) => {
                  const entry = learning?.datasets?.[modality] || {};
                  return (
                    <Typography key={modality} variant="body2" color="text.secondary">
                      <strong>{modality}</strong>: {entry.active_version || "none"} ·{" "}
                      {entry.count || 0} version(s)
                    </Typography>
                  );
                })}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1.5}>
                Model versions
              </Typography>
              <Stack spacing={1}>
                {["family_classifier", "exact_section", "geometry", "graph", "fusion"].map(
                  (family) => {
                    const entry = learning?.models?.[family] || {};
                    const latest = (entry.versions || [])[0];
                    return (
                      <Typography key={family} variant="body2" color="text.secondary">
                        <strong>{family}</strong>: {entry.active_version || "none"}
                        {latest?.promotion_status
                          ? ` · last ${latest.promotion_status}`
                          : ""}
                      </Typography>
                    );
                  },
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={1.5} mb={2.5}>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile label="Training samples" value={aug.training_samples_total || meta.samples_total || "—"} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile label="Augmented samples" value={stats?.synthetic_samples || aug.augmented_samples || 0} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile label="Feature count" value={meta.feature_count || stats?.feature_count || "—"} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Tile
            label="Geometry/graph gates"
            value={`${learning?.modality_thresholds?.geometry_min_samples || 80}+`}
          />
        </Grid>
      </Grid>

      {quality && (
        <Alert
          severity={
            quality.status === "fail"
              ? "error"
              : quality.status === "warning"
                ? "warning"
                : "info"
          }
          sx={{ mb: 2 }}
        >
          Data quality: {quality.sample_count} samples, {quality.duplicate_count || 0} duplicates,
          imbalance {quality.imbalance_ratio || 0}. Database is verification-only during inference.
        </Alert>
      )}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1.5}>
                Model metrics
              </Typography>
              <Grid container spacing={1.25}>
                {[
                  ["Accuracy", metrics.accuracy ?? metrics.holdout_accuracy],
                  ["Precision", metrics.precision ?? metrics.weighted_precision],
                  ["Recall", metrics.recall ?? metrics.weighted_recall],
                  ["F1", metrics.f1 ?? metrics.weighted_f1],
                ].map(([label, value]) => (
                  <Grid size={{ xs: 6 }} key={label}>
                    <Box className="metric-tile">
                      <Typography variant="caption" color="text.secondary" fontWeight={700}>
                        {label}
                      </Typography>
                      <Typography variant="h6" fontWeight={700}>
                        {value == null ? "—" : Number(value).toFixed(3)}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
              <Button href="/model" sx={{ mt: 2 }}>
                Open confusion matrix
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} mb={1.5}>
                Paired PDF + Excel dataset
              </Typography>
              {(paired?.pairs || []).length === 0 ? (
                <EmptyState
                  title="No pairs configured"
                  subtitle="Add matching files under training/pdf and training/excel."
                />
              ) : (
                <Stack spacing={1}>
                  <Typography variant="body2" color="text.secondary">
                    Ready pairs: {(paired.pairs || []).filter((p) => p.ready).length} /{" "}
                    {(paired.pairs || []).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Paired rows:{" "}
                    {pairedMeta.row_count ?? (paired.paired_dataset_exists ? "built" : "not built")}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Unique labels: {pairedMeta.unique_labels ?? "—"}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" mt={1}>
                    Excel is ground truth for dataset creation only — never used as inference input.
                  </Typography>
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <RetrainProgressDialog
        open={dialogOpen}
        status={retrain}
        onClose={() => setDialogOpen(false)}
      />
    </Box>
  );
}
