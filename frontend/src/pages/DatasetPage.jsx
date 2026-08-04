import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getContinuousLearningStatus, getStatistics } from "../api/client";
import { CHART_COLORS } from "../lib/utils";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";

export default function DatasetPage() {
  const [stats, setStats] = useState(null);
  const [learning, setLearning] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getStatistics(), getContinuousLearningStatus()])
      .then(([data, continuous]) => {
        if (!active) return;
        setStats(data);
        setLearning(continuous);
        setError("");
      })
      .catch(() => {
        if (!active) return;
        setError("Failed to load dataset statistics.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const unk = stats?.unknown_tokens || {};
  const aug = stats?.augmentation || {};
  const composition = [
    { name: "AISC original", value: stats?.aisc_samples || 0 },
    { name: "Approved", value: stats?.approved_tokens || 0 },
    { name: "Synthetic", value: stats?.synthetic_samples || aug.augmented_samples || 0 },
    { name: "Pending review", value: unk.pending || 0 },
    { name: "Rejected", value: unk.rejected || 0 },
  ].filter((d) => d.value > 0);

  const growthBars = [
    { name: "Original", count: (stats?.aisc_samples || 0) + (stats?.approved_tokens || 0) },
    { name: "Augmented", count: stats?.synthetic_samples || aug.augmented_samples || 0 },
    { name: "Train total", count: aug.training_samples_total || stats?.model_meta?.samples_total || 0 },
  ];

  if (loading) {
    return (
      <Box>
        <PageHeader
          title="Dataset"
          subtitle="AISC catalog + approved reviews + paired PDF/Excel ground truth + augmentation"
        />
        <Grid container spacing={1.5} mb={1.5}>
          {Array.from({ length: 6 }, (_, index) => (
            <Grid size={{ xs: 6, md: 4, lg: 2 }} key={index}>
              <Skeleton variant="rounded" height={88} />
            </Grid>
          ))}
        </Grid>
        <Grid container spacing={1.5}>
          <Grid size={{ xs: 12, md: 5 }}>
            <Skeleton variant="rounded" height={340} />
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            <Skeleton variant="rounded" height={340} />
          </Grid>
        </Grid>
      </Box>
    );
  }

  if (error) {
    return (
      <Box>
        <PageHeader
          title="Dataset"
          subtitle="AISC catalog + approved reviews + paired PDF/Excel ground truth + augmentation"
        />
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ minWidth: 0 }}>
      <PageHeader
        title="Dataset"
        subtitle="Versioned text, geometry, graph, and fusion datasets from reviews, corrections, PDF extraction, and Excel takeoff."
      />

      <Grid container spacing={1.5} mb={1.5}>
        {[
          ["Original (AISC)", stats?.aisc_samples],
          ["Approved samples", stats?.approved_tokens ?? 0],
          ["Synthetic samples", stats?.synthetic_samples ?? 0],
          ["Training total", aug.training_samples_total || "—"],
          ["Classes", stats?.n_classes],
          ["Augmentation", aug.enabled ? "Enabled" : "Off"],
        ].map(([label, value]) => (
          <Grid size={{ xs: 6, md: 4, lg: 2 }} key={label}>
            <Card>
              <CardContent sx={{ py: 1.75, "&:last-child": { pb: 1.75 } }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  {label}
                </Typography>
                <Typography variant="h6" fontWeight={700} noWrap title={String(value ?? "—")}>
                  {value ?? "—"}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {learning?.sources && (
        <Card sx={{ mb: 1.5 }}>
          <CardContent>
            <Typography variant="subtitle2" fontWeight={700} mb={1}>
              Continuous-learning ingestion
            </Typography>
            <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
              {Object.entries(learning.sources.sources || {}).map(([name, count]) => (
                <Chip key={name} size="small" label={`${name}: ${count}`} />
              ))}
            </Stack>
            <Stack direction="row" useFlexGap spacing={1} mt={1.25} sx={{ flexWrap: "wrap" }}>
              {Object.entries(learning.sources.modality_counts || {}).map(([name, count]) => (
                <Chip
                  key={name}
                  size="small"
                  color="primary"
                  variant="outlined"
                  label={`${name} lane: ${count}`}
                />
              ))}
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" mt={1.25}>
              Active dataset versions —{" "}
              {["text", "geometry", "graph", "fusion"]
                .map((modality) => `${modality}: ${learning.datasets?.[modality]?.active_version || "none"}`)
                .join(" · ")}
            </Typography>
          </CardContent>
        </Card>
      )}

      <Grid container spacing={1.5}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card sx={{ height: 340 }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={700} mb={1}>
                Dataset composition
              </Typography>
              {composition.length ? (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={composition} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85}>
                      {composition.map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState
                  title="No composition data"
                  subtitle="Dataset counts will appear after training data is available."
                  sx={{ py: 4 }}
                />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card sx={{ height: 340 }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={700} mb={1}>
                Augmentation size
              </Typography>
              {growthBars.some((row) => row.count > 0) ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={growthBars}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6b9bff" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState
                  title="No augmentation data"
                  subtitle="Run training or retraining to materialize synthetic variants."
                  sx={{ py: 4 }}
                />
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card sx={{ mt: 1.5 }}>
        <CardContent>
          <Typography variant="subtitle2" fontWeight={700} mb={1}>
            Known classes
          </Typography>
          {(stats?.known_classes || []).length ? (
            <Stack direction="row" useFlexGap gap={0.75} sx={{ flexWrap: "wrap" }}>
              {(stats?.known_classes || []).map((c) => (
                <Chip key={c} size="small" label={c} />
              ))}
            </Stack>
          ) : (
            <EmptyState
              title="No known classes"
              subtitle="Class labels appear after a model is trained."
              sx={{ py: 3 }}
            />
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
