import { useEffect, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Alert,
  Box,
  Chip,
  Grid,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import {
  CloudUploadOutlined,
  RateReviewOutlined,
  ModelTrainingOutlined,
} from "@mui/icons-material";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getHistory, getStatistics } from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import KpiCard from "../components/ui/KpiCard";
import SectionCard from "../components/ui/SectionCard";
import EmptyState from "../components/ui/EmptyState";
import { TipButton } from "../components/ui/ActionButtons";

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getStatistics(), getHistory(80)])
      .then(([s, h]) => {
        if (!active) return;
        setStats(s);
        setHistory(h.events || []);
        setError("");
      })
      .catch(() => {
        if (!active) return;
        setError("Backend unavailable on port 8000.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const unk = stats?.unknown_tokens || {};
  const accuracy =
    stats?.current_accuracy != null
      ? `${(Number(stats.current_accuracy) * 100).toFixed(1)}%`
      : "—";
  const trained = stats?.training_date
    ? new Date(stats.training_date).toLocaleString()
    : "Baseline";
  const datasetSize =
    stats?.model_meta?.samples_total ??
    (stats?.aisc_samples ?? 0) + (stats?.approved_tokens ?? 0);

  const growth = useMemo(() => {
    let n = 0;
    return [...history]
      .reverse()
      .filter(
        (e) =>
          String(e.event).includes("upload") || String(e.event).includes("approve")
      )
      .map((e) => {
        n += 1;
        return {
          t: e.created_at ? new Date(e.created_at).toLocaleDateString() : "",
          events: n,
        };
      })
      .slice(-20);
  }, [history]);

  return (
    <Box sx={{ minWidth: 0 }}>
      <PageHeader
        title="Dashboard"
        subtitle="AI structural steel takeoff — classification, AISC verification, review, and training status"
        actions={
          <>
            <TipButton
              title="Upload a drawing"
              component={RouterLink}
              to="/upload"
              variant="contained"
              startIcon={<CloudUploadOutlined />}
            >
              Upload
            </TipButton>
            <TipButton
              title="Open validation"
              component={RouterLink}
              to="/validation"
              variant="outlined"
              startIcon={<RateReviewOutlined />}
            >
              Validation
            </TipButton>
            <TipButton
              title="Training workspace"
              component={RouterLink}
              to="/training"
              variant="outlined"
              startIcon={<ModelTrainingOutlined />}
            >
              Training
            </TipButton>
          </>
        }
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2.5 }}>
          {error}
        </Alert>
      )}

      {error && !stats ? null : (
      <>
      <Grid container spacing={2}>
        {loading
          ? Array.from({ length: 6 }, (_, index) => (
              <Grid size={{ xs: 6, md: 4, lg: 2 }} key={index}>
                <Skeleton variant="rounded" height={116} />
              </Grid>
            ))
          : [
              ["Total PDFs", stats?.total_pdfs ?? 0, "/upload"],
              ["Known tokens", stats?.aisc_samples ?? 0, "/dataset"],
              ["Unknown", unk.pending ?? 0, "/review", "warning.main"],
              ["Approved", stats?.approved_tokens ?? 0, "/review?status=approved", "success.main"],
              ["Rejected", unk.rejected ?? 0, "/review?status=rejected"],
              ["Pattern helpers", stats?.regex_class_count ?? 0, "/analytics"],
            ].map(([label, value, to, accent]) => (
              <Grid size={{ xs: 6, md: 4, lg: 2 }} key={label}>
                <KpiCard label={label} value={value} to={to} accent={accent} />
              </Grid>
            ))}
      </Grid>

      {!loading && (
      <Grid container spacing={2} mt={0.5}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <SectionCard title="Production snapshot">
            <Grid container spacing={2.5}>
              {[
                ["Current Model", stats?.current_model || "—"],
                ["Accuracy", accuracy],
                ["Dataset Size", datasetSize],
                ["Training Date", trained],
                [
                  "Latest Upload",
                  stats?.latest_upload?.filename || "—",
                ],
                [
                  "Latest Retrain",
                  stats?.latest_retrain?.created_at
                    ? new Date(stats.latest_retrain.created_at).toLocaleString()
                    : trained,
                ],
              ].map(([label, value]) => (
                <Grid size={{ xs: 6, sm: 4 }} key={label}>
                  <Typography variant="caption" color="text.secondary" fontWeight={700}>
                    {label}
                  </Typography>
                  <Typography
                    fontWeight={700}
                    fontSize={14}
                    noWrap
                    title={String(value)}
                    sx={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis" }}
                  >
                    {value}
                  </Typography>
                </Grid>
              ))}
            </Grid>
          </SectionCard>

          <Box mt={2}>
            <SectionCard title="Workspace activity">
              <Box sx={{ height: 220, pt: 1 }}>
                {growth.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={growth}>
                      <CartesianGrid vertical={false} strokeDasharray="3 4" opacity={0.18} />
                      <XAxis dataKey="t" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                      <Tooltip />
                      <Area
                        type="monotone"
                        dataKey="events"
                        stroke="#8ba8ec"
                        fill="#8ba8ec25"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    title="No activity yet"
                    subtitle="Activity will appear after uploads and reviews."
                    sx={{ py: 4 }}
                  />
                )}
              </Box>
            </SectionCard>
          </Box>
        </Grid>

        <Grid size={{ xs: 12, lg: 4 }}>
          <SectionCard
            title="Unknown queue"
            action={
              <TipButton title="Open queue" component={RouterLink} to="/review" size="small">
                Open
              </TipButton>
            }
          >
            <Stack spacing={1.25}>
              {(stats?.recent_unknowns || []).slice(0, 5).map((t) => (
                <Stack
                  key={t.id}
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                  spacing={1}
                >
                  <Typography
                    fontFamily="monospace"
                    fontSize={12.5}
                    fontWeight={700}
                    noWrap
                    title={t.token}
                    sx={{ minWidth: 0 }}
                  >
                    {t.token}
                  </Typography>
                  <Chip size="small" label={t.prediction || "—"} />
                </Stack>
              ))}
              {!stats?.recent_unknowns?.length && (
                <Typography variant="body2" color="text.secondary">
                  Queue is clear.
                </Typography>
              )}
            </Stack>
          </SectionCard>

          <Box mt={2}>
            <SectionCard title="Recent activity" contentSx={{ px: 0, pb: 0 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ pl: 2.25 }}>Event</TableCell>
                    <TableCell>When</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(stats?.recent_activity || history).slice(0, 7).map((e) => (
                    <TableRow key={e.id}>
                      <TableCell sx={{ pl: 2.25 }}>
                        <Chip size="small" label={e.event} />
                      </TableCell>
                      <TableCell sx={{ fontSize: 11, whiteSpace: "nowrap", pr: 2.25 }}>
                        {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                  {!(stats?.recent_activity || history)?.length && (
                    <TableRow>
                      <TableCell colSpan={2} sx={{ p: 0 }}>
                        <EmptyState
                          title="No recent activity"
                          subtitle="Uploads and reviews will appear here."
                          sx={{ py: 4 }}
                        />
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </SectionCard>
          </Box>
        </Grid>
      </Grid>
      )}
      </>
      )}
    </Box>
  );
}
