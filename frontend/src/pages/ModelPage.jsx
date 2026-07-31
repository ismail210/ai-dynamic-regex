import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tab,
  Typography,
} from "@mui/material";
import {
  AccountTreeOutlined,
  CheckCircleRounded,
  DataObjectOutlined,
  ModelTrainingOutlined,
  TableRowsOutlined,
} from "@mui/icons-material";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getStatistics } from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import KpiCard from "../components/ui/KpiCard";
import EmptyState from "../components/ui/EmptyState";
import EntityTypeChip from "../components/ui/EntityTypeChip";

const pct = (value) =>
  value == null
    ? "—"
    : `${(Number(value) * (Number(value) <= 1 ? 100 : 1)).toFixed(2)}%`;

export default function ModelPage() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [entityTab, setEntityTab] = useState("all");

  useEffect(() => {
    let active = true;
    setLoading(true);
    getStatistics()
      .then((data) => {
        if (!active) return;
        setStats(data);
        setError("");
      })
      .catch(() => {
        if (!active) return;
        setStats(null);
        setError("Model information could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const meta = stats?.model_meta || {};
  const confusion = meta.confusion_matrix || {};
  const labels = confusion.labels || [];
  const matrix = confusion.matrix || [];
  const entitySummary = stats?.entity_summary || {};
  const entityPerformance = stats?.entity_performance || [];
  const classEntityMap = stats?.class_entity_map || {};
  const topMisclassifications = stats?.top_misclassifications || [];
  const entityTabs = stats?.entity_tabs || [
    { id: "all", label: "All" },
    { id: "structural_section", label: "Steel Sections" },
    { id: "material", label: "Materials" },
    { id: "bolt", label: "Bolts" },
    { id: "plate", label: "Plates" },
    { id: "miscellaneous", label: "Other" },
  ];

  const metrics = useMemo(
    () =>
      [
        ["Accuracy", meta.accuracy ?? stats?.current_accuracy],
        ["Precision", meta.precision],
        ["Recall", meta.recall],
        ["F1", meta.f1],
      ].map(([name, value]) => ({
        name,
        score: value == null ? 0 : Number(value) * (Number(value) <= 1 ? 100 : 1),
      })),
    [meta, stats]
  );

  const filteredMatrix = useMemo(() => {
    if (!matrix.length || !labels.length) {
      return { labels: [], matrix: [] };
    }
    if (entityTab === "all") {
      return { labels, matrix };
    }
    const indices = labels
      .map((label, index) => ({ label, index }))
      .filter(({ label }) => classEntityMap[label]?.tab_id === entityTab)
      .map(({ index }) => index);
    return {
      labels: indices.map((index) => labels[index]),
      matrix: indices.map((rowIndex) =>
        indices.map((colIndex) => matrix[rowIndex]?.[colIndex] ?? 0)
      ),
    };
  }, [matrix, labels, entityTab, classEntityMap]);

  const populatedPerformance = useMemo(
    () => entityPerformance.filter((row) => (row.class_count || 0) > 0),
    [entityPerformance]
  );

  const summaryCards = [
    ["Total Entity Types", entitySummary.total_entity_types ?? "—"],
    ["Steel Section Classes", entitySummary.steel_section_classes ?? "—"],
    ["Material Classes", entitySummary.material_classes ?? "—"],
    ["Bolt Classes", entitySummary.bolt_classes ?? "—"],
  ];
  if ((entitySummary.plate_classes ?? 0) > 0 || entityTab === "plate") {
    summaryCards.push(["Plate Classes", entitySummary.plate_classes ?? 0]);
  }
  summaryCards.push([
    "Overall Accuracy",
    pct(entitySummary.overall_accuracy ?? meta.accuracy ?? stats?.current_accuracy),
  ]);

  if (loading) {
    return (
      <Box>
        <PageHeader
          title="Model"
          subtitle="Production XGBoost quality, architecture, and class-level diagnostics"
        />
        <Grid container spacing={2} mb={2.5}>
          {Array.from({ length: 4 }, (_, index) => (
            <Grid size={{ xs: 6, lg: 3 }} key={index}>
              <Skeleton variant="rounded" height={116} />
            </Grid>
          ))}
        </Grid>
        <Grid container spacing={2.5}>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Skeleton variant="rounded" height={340} />
          </Grid>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Skeleton variant="rounded" height={340} />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Skeleton variant="rounded" height={220} />
          </Grid>
        </Grid>
      </Box>
    );
  }

  if (error) {
    return (
      <Box>
        <PageHeader
          title="Model"
          subtitle="Production XGBoost quality, architecture, and class-level diagnostics"
        />
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ minWidth: 0 }}>
      <PageHeader
        title="Model"
        subtitle="Production XGBoost quality, architecture, and class-level diagnostics"
      />

      <Grid container spacing={2} mb={2.5}>
        {[
          ["Production model", stats?.current_model || meta.model || "XGBoost"],
          ["Accuracy", pct(meta.accuracy ?? stats?.current_accuracy)],
          ["Training samples", meta.samples_total ?? meta.rows ?? "—"],
          ["Classes", meta.n_classes ?? stats?.n_classes ?? "—"],
        ].map(([label, value]) => (
          <Grid size={{ xs: 6, lg: 3 }} key={label}>
            <KpiCard label={label} value={value} />
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={2.5} alignItems="stretch">
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card sx={{ height: "100%" }}>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Typography variant="subtitle1">Holdout performance</Typography>
              <Typography variant="body2" color="text.secondary" mt={0.25} mb={2}>
                Weighted evaluation metrics from the latest production retrain.
              </Typography>
              <Box sx={{ height: 280 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={metrics} layout="vertical" margin={{ left: 8, right: 30 }}>
                    <CartesianGrid horizontal={false} strokeDasharray="3 4" opacity={0.18} />
                    <XAxis type="number" domain={[0, 100]} hide />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={72}
                      axisLine={false}
                      tickLine={false}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
                    <Bar dataKey="score" fill="#8ba8ec" radius={[0, 6, 6, 0]} barSize={25} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, lg: 5 }}>
          <Card sx={{ height: "100%" }}>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Typography variant="subtitle1">Model pipeline</Typography>
                <Chip
                  size="small"
                  color="success"
                  icon={<CheckCircleRounded />}
                  label="Loaded"
                />
              </Stack>
              <Typography variant="body2" color="text.secondary" mt={0.25} mb={2.5}>
                The same saved preprocessing executes during training and prediction.
              </Typography>
              <Stack spacing={1.25}>
                <PipelineStep
                  icon={DataObjectOutlined}
                  title="Raw engineering token"
                  detail="Normalized inside the pipeline"
                />
                <PipelineStep
                  icon={AccountTreeOutlined}
                  title="Combined preprocessing"
                  detail="Character TF-IDF + engineered structural features"
                />
                <PipelineStep
                  icon={ModelTrainingOutlined}
                  title="XGBoost classifier"
                  detail={`${meta.n_classes ?? stats?.n_classes ?? "—"} encoded output classes`}
                />
              </Stack>
              <Box className="metric-tile" mt={2}>
                <Typography variant="caption" color="text.secondary">
                  Last trained
                </Typography>
                <Typography fontWeight={650} fontSize={13} mt={0.45}>
                  {meta.trained_at
                    ? new Date(meta.trained_at).toLocaleString()
                    : "Baseline"}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Typography variant="subtitle1">Entity Type Summary</Typography>
              <Typography variant="body2" color="text.secondary" mt={0.25} mb={2}>
                Holdout class composition grouped by engineering entity type.
              </Typography>
              <Grid container spacing={1.5}>
                {summaryCards.map(([label, value]) => (
                  <Grid
                    size={{
                      xs: 6,
                      sm: 4,
                      md: summaryCards.length > 5 ? 2 : 2.4,
                    }}
                    key={label}
                  >
                    <Box className="metric-tile" sx={{ minHeight: 88 }}>
                      <Typography variant="caption" color="text.secondary" fontWeight={650}>
                        {label}
                      </Typography>
                      <Typography fontWeight={720} fontSize={22} mt={0.75} noWrap title={String(value)}>
                        {value}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Typography variant="subtitle1">Entity Performance</Typography>
              <Typography variant="body2" color="text.secondary" mt={0.25} mb={2}>
                Support-weighted holdout metrics for each populated entity type.
              </Typography>
              {!populatedPerformance.length ? (
                <EmptyState
                  title="No entity diagnostics"
                  subtitle="Run a production retrain to generate entity-level metrics."
                  icon={TableRowsOutlined}
                />
              ) : (
                <Grid container spacing={1.5}>
                  {populatedPerformance.map((row) => (
                    <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }} key={row.entity_type}>
                      <Box
                        className="metric-tile"
                        sx={{ height: "100%", minHeight: 168 }}
                      >
                        <Stack
                          direction="row"
                          alignItems="center"
                          justifyContent="space-between"
                          spacing={1}
                          mb={1.25}
                        >
                          <Typography fontWeight={700} fontSize={13.5} noWrap>
                            {row.entity_type_label}
                          </Typography>
                          <EntityTypeChip
                            entityType={row.entity_type}
                            label={row.entity_type_label}
                          />
                        </Stack>
                        <Typography fontWeight={720} fontSize={22} mb={1}>
                          {pct(row.accuracy)}
                        </Typography>
                        <Stack spacing={0.45}>
                          <MetricLine label="Precision" value={pct(row.precision)} />
                          <MetricLine label="Recall" value={pct(row.recall)} />
                          <MetricLine label="F1" value={pct(row.f1)} />
                          <MetricLine label="Classes" value={row.class_count ?? 0} />
                          <MetricLine
                            label="Holdout samples"
                            value={row.sample_count ?? 0}
                          />
                        </Stack>
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Typography variant="subtitle1">Confusion matrix</Typography>
              <Typography variant="body2" color="text.secondary" mt={0.25} mb={1.5}>
                Predicted classes by actual class on the latest holdout set.
              </Typography>
              <Tabs
                value={entityTab}
                onChange={(_, value) => setEntityTab(value)}
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
                sx={{
                  mb: 2,
                  minHeight: 36,
                  borderBottom: (theme) => `1px solid ${theme.palette.divider}`,
                  "& .MuiTab-root": {
                    minHeight: 36,
                    textTransform: "none",
                    fontWeight: 650,
                    fontSize: "0.8rem",
                  },
                }}
              >
                {entityTabs.map((tab) => (
                  <Tab key={tab.id} value={tab.id} label={tab.label} />
                ))}
              </Tabs>
              {!filteredMatrix.matrix.length ? (
                <EmptyState
                  title="No matrix available"
                  subtitle={
                    entityTab === "all"
                      ? "Run a production retrain to generate class diagnostics."
                      : "No classes in this entity type for the current model."
                  }
                />
              ) : (
                <TableContainer sx={{ overflowX: "auto", maxHeight: 540 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>Actual</TableCell>
                        {filteredMatrix.labels.map((label) => (
                          <TableCell key={label} align="center">
                            {label}
                          </TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredMatrix.matrix.map((row, rowIndex) => (
                        <TableRow key={filteredMatrix.labels[rowIndex] || rowIndex}>
                          <TableCell
                            sx={{
                              fontWeight: 700,
                              position: "sticky",
                              left: 0,
                              bgcolor: "background.paper",
                              zIndex: 1,
                            }}
                          >
                            {filteredMatrix.labels[rowIndex]}
                          </TableCell>
                          {row.map((value, columnIndex) => (
                            <TableCell
                              key={columnIndex}
                              align="center"
                              sx={{
                                color:
                                  rowIndex === columnIndex && value > 0
                                    ? "success.main"
                                    : "text.secondary",
                                fontWeight: rowIndex === columnIndex ? 700 : 400,
                              }}
                            >
                              {value}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Typography variant="subtitle1">Top Misclassifications</Typography>
              <Typography variant="body2" color="text.secondary" mt={0.25} mb={2}>
                Most frequent off-diagonal mistakes on the holdout set.
              </Typography>
              {!topMisclassifications.length ? (
                <EmptyState
                  title="No misclassifications"
                  subtitle="The holdout matrix has no off-diagonal errors to report."
                />
              ) : (
                <TableContainer sx={{ overflowX: "auto" }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Actual Class</TableCell>
                        <TableCell>Predicted Class</TableCell>
                        <TableCell>Entity Type</TableCell>
                        <TableCell align="right">Misclassification Count</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {topMisclassifications.map((row) => (
                        <TableRow
                          key={`${row.actual_class}-${row.predicted_class}-${row.count}`}
                        >
                          <TableCell sx={{ fontWeight: 650 }}>{row.actual_class}</TableCell>
                          <TableCell>{row.predicted_class}</TableCell>
                          <TableCell>
                            <EntityTypeChip
                              entityType={row.entity_type}
                              label={row.entity_type_label}
                            />
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700 }}>
                            {row.count}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}

function MetricLine({ label, value }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={1}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="caption" fontWeight={650}>
        {value}
      </Typography>
    </Stack>
  );
}

function PipelineStep({ icon: Icon, title, detail }) {
  return (
    <Stack direction="row" spacing={1.25} alignItems="center">
      <Box className="icon-surface" sx={{ width: "36px !important", height: "36px !important" }}>
        <Icon sx={{ fontSize: 18 }} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography fontSize={13.5} fontWeight={650}>
          {title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {detail}
        </Typography>
      </Box>
    </Stack>
  );
}
