import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import { getHistory, getStatistics } from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";

const COLOR = {
  upload: "primary",
  approve: "success",
  reject: "error",
  retrain: "secondary",
  model_retrained: "secondary",
  token_approved: "success",
  token_rejected: "error",
  unknown_queued: "warning",
};

function parseRetrainDetail(detail = "") {
  const d = String(detail);
  const num = (re) => {
    const m = d.match(re);
    return m ? m[1] : null;
  };
  return {
    accuracy: num(/accuracy[=:\s]+([0-9.]+)/i),
    samples: num(/samples?[=:\s]+(\d+)/i) || num(/rows?[=:\s]+(\d+)/i) || num(/dataset[=:\s]+(\d+)/i),
    newSamples: num(/new[=:\s]+(\d+)/i) || num(/approved[=:\s]+(\d+)/i),
    rejected: num(/rejected[=:\s]+(\d+)/i),
    regex: num(/regex[=:\s]+(\d+)/i) || num(/variants?[=:\s]+(\d+)/i),
    version: num(/version[=:\s]+([^\s,;]+)/i) || num(/model[=:\s]+([^\s,;]+)/i),
  };
}

function Meta({ label, value }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography fontWeight={600} fontSize={13}>
        {value}
      </Typography>
    </Box>
  );
}

export default function HistoryPage() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getHistory(200), getStatistics()])
      .then(([h, s]) => {
        if (!active) return;
        setEvents(h.events || []);
        setStats(s);
        setError("");
      })
      .catch(() => {
        if (!active) return;
        setError("Failed to load history.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const retrainEvents = useMemo(
    () =>
      events.filter((e) => {
        const ev = String(e.event || "").toLowerCase();
        return ev.includes("retrain");
      }),
    [events]
  );

  const otherEvents = useMemo(
    () =>
      events.filter((e) => {
        const ev = String(e.event || "").toLowerCase();
        return !ev.includes("retrain");
      }),
    [events]
  );

  if (loading) {
    return (
      <Box>
        <PageHeader
          title="History"
          subtitle="Retraining timeline, uploads, approvals, and rejects"
        />
        <Stack spacing={1.5}>
          <Skeleton variant="rounded" height={120} />
          <Skeleton variant="rounded" height={120} />
          <Skeleton variant="rounded" height={180} />
        </Stack>
      </Box>
    );
  }

  if (error) {
    return (
      <Box>
        <PageHeader
          title="History"
          subtitle="Retraining timeline, uploads, approvals, and rejects"
        />
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ minWidth: 0 }}>
      <PageHeader
        title="History"
        subtitle="Retraining timeline, uploads, approvals, and rejects"
      />

      <Typography variant="subtitle2" color="text.secondary" mb={1.5} fontWeight={700}>
        Retraining timeline
      </Typography>

      <Box sx={{ position: "relative", pl: { xs: 2, sm: 3 }, mb: 4 }}>
        <Box
          sx={{
            position: "absolute",
            left: { xs: 6, sm: 10 },
            top: 8,
            bottom: 8,
            width: 2,
            bgcolor: "divider",
          }}
        />
        <Stack spacing={1.5}>
          {retrainEvents.length === 0 && (
            <Card>
              <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
                <Typography fontWeight={700}>Baseline model</Typography>
                <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap mt={1.5}>
                  <Meta
                    label="Date"
                    value={
                      stats?.training_date
                        ? new Date(stats.training_date).toLocaleString()
                        : "Initial"
                    }
                  />
                  <Meta
                    label="Dataset Size"
                    value={(stats?.aisc_samples ?? 0) + (stats?.approved_tokens ?? 0)}
                  />
                  <Meta
                    label="Accuracy"
                    value={
                      stats?.current_accuracy != null
                        ? `${(Number(stats.current_accuracy) * 100).toFixed(1)}%`
                        : "—"
                    }
                  />
                  <Meta label="Model Version" value={stats?.current_model || "XGBoost"} />
                  <Meta label="Approved Samples" value={stats?.approved_tokens ?? 0} />
                  <Meta label="Rejected Samples" value={stats?.unknown_tokens?.rejected ?? 0} />
                </Stack>
              </CardContent>
            </Card>
          )}
          {retrainEvents.map((e) => {
            const p = parseRetrainDetail(e.detail);
            const acc =
              p.accuracy != null
                ? Number(p.accuracy) <= 1
                  ? `${(Number(p.accuracy) * 100).toFixed(1)}%`
                  : `${p.accuracy}%`
                : stats?.current_accuracy != null
                ? `${(Number(stats.current_accuracy) * 100).toFixed(1)}%`
                : "—";
            return (
              <Box key={e.id} sx={{ position: "relative" }}>
                <Box
                  sx={{
                    position: "absolute",
                    left: { xs: -14, sm: -18 },
                    top: 18,
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    bgcolor: "primary.main",
                    border: 2,
                    borderColor: "background.default",
                  }}
                />
                <Card>
                  <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
                    <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                      <Chip size="small" label={e.event} color={COLOR[e.event] || "secondary"} />
                      <Typography variant="caption" color="text.secondary">
                        {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                      </Typography>
                    </Stack>
                    <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
                      <Meta
                        label="Date"
                        value={e.created_at ? new Date(e.created_at).toLocaleDateString() : "—"}
                      />
                      <Meta label="Dataset Size" value={p.samples || "—"} />
                      <Meta label="Accuracy" value={acc} />
                      <Meta label="New Samples" value={p.newSamples || "—"} />
                      <Meta label="Rejected Samples" value={p.rejected || "—"} />
                      <Meta label="Regex Changes" value={p.regex || "—"} />
                      <Meta
                        label="Model Version"
                        value={p.version || stats?.current_model || "XGBoost"}
                      />
                    </Stack>
                    {e.detail && (
                      <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>
                        {e.detail}
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Box>
            );
          })}
        </Stack>
      </Box>

      <Typography variant="subtitle2" color="text.secondary" mb={1.5}>
        Activity log
      </Typography>
      <Stack spacing={1} sx={{ maxHeight: "50vh", overflow: "auto" }}>
        {otherEvents.slice(0, 100).map((e) => (
          <Card key={e.id}>
            <CardContent
              sx={{
                py: 1.25,
                "&:last-child": { pb: 1.25 },
                display: "flex",
                gap: 1.5,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <Typography variant="caption" color="text.secondary" sx={{ minWidth: 140 }}>
                {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
              </Typography>
              <Chip size="small" label={e.event} color={COLOR[e.event] || "default"} />
              <Typography
                fontFamily="monospace"
                fontSize={12}
                fontWeight={600}
                sx={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}
                title={e.token || ""}
              >
                {e.token || "—"}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  flex: 1,
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={e.detail || ""}
              >
                {e.detail || ""}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {e.actor}
              </Typography>
            </CardContent>
          </Card>
        ))}
        {otherEvents.length === 0 && retrainEvents.length === 0 && (
          <EmptyState
            title="No history yet"
            subtitle="Uploads, reviews, and retrains will appear here."
          />
        )}
      </Stack>
    </Box>
  );
}
