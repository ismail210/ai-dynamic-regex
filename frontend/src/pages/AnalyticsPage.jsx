import { useEffect, useMemo, useState } from "react";
import { Alert, Box, Card, CardContent, Grid, Skeleton, Typography } from "@mui/material";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getDynamicRegex, getHistory, getStatistics } from "../api/client";
import { useThemeMode } from "../context/ThemeContext";
import PageHeader from "../components/ui/PageHeader";

function ChartPanel({ title, description, children, height = 290 }) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
        <Typography variant="subtitle1">{title}</Typography>
        <Typography variant="body2" color="text.secondary" mt={0.25} mb={2.25}>
          {description}
        </Typography>
        <Box sx={{ height }}>{children}</Box>
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [regexClasses, setRegexClasses] = useState({});
  const [error, setError] = useState("");
  const { mode } = useThemeMode();

  useEffect(() => {
    Promise.all([getStatistics(), getHistory(250), getDynamicRegex()])
      .then(([statistics, events, regex]) => {
        setStats(statistics);
        setHistory(events.events || []);
        setRegexClasses(regex.classes || {});
      })
      .catch(() => setError("Analytics could not be loaded."));
  }, []);

  const tooltipStyle = {
    background: mode === "dark" ? "#141a24" : "#fff",
    border: `1px solid ${mode === "dark" ? "#293140" : "#dce1e8"}`,
    borderRadius: 10,
    boxShadow: "0 12px 32px rgba(0,0,0,.16)",
    fontSize: 12,
  };

  const learningTrend = useMemo(() => {
    let approved = 0;
    let rejected = 0;
    return [...history]
      .reverse()
      .filter((event) => {
        const name = String(event.event || "");
        if (name.includes("approve")) approved += 1;
        if (name.includes("reject")) rejected += 1;
        return name.includes("approve") || name.includes("reject") || name.includes("upload");
      })
      .map((event) => ({
        date: event.created_at ? new Date(event.created_at).toLocaleDateString() : "",
        approved,
        rejected,
      }))
      .slice(-45);
  }, [history]);

  const classCoverage = useMemo(
    () =>
      Object.entries(regexClasses)
        .map(([name, record]) => ({
          name,
          samples: record.example_count || record.examples?.length || 0,
          confidence: Math.round(Number(record.confidence || 0) * 100),
        }))
        .sort((a, b) => b.samples - a.samples)
        .slice(0, 16),
    [regexClasses]
  );

  const categoryCoverage = useMemo(() => {
    const totals = {};
    Object.values(regexClasses).forEach((record) => {
      const category = record.category_label || record.category || "Other";
      totals[category] = (totals[category] || 0) + 1;
    });
    return Object.entries(totals)
      .map(([name, classes]) => ({ name, classes }))
      .sort((a, b) => b.classes - a.classes);
  }, [regexClasses]);

  const performance = [
    ["Accuracy", stats?.model_meta?.accuracy ?? stats?.current_accuracy],
    ["Precision", stats?.model_meta?.precision],
    ["Recall", stats?.model_meta?.recall],
    ["F1", stats?.model_meta?.f1],
  ].map(([metric, value]) => ({
    metric,
    score: value == null ? 0 : Number(value) * (Number(value) <= 1 ? 100 : 1),
  }));

  const retrainTimeline = useMemo(
    () =>
      [...history]
        .reverse()
        .filter((event) => String(event.event || "").includes("retrain"))
        .map((event, index) => ({
          date: event.created_at
            ? new Date(event.created_at).toLocaleDateString()
            : `Run ${index + 1}`,
          runs: index + 1,
        }))
        .slice(-24),
    [history]
  );

  return (
    <Box>
      <PageHeader
        title="Analytics"
        subtitle="Learning trends, model quality, and regex coverage"
      />
      {error && (
        <Alert severity="error" sx={{ mb: 2.5 }}>
          {error}
        </Alert>
      )}

      {!stats && !error ? (
        <Grid container spacing={2.5}>
          {[1, 2, 3, 4].map((item) => (
            <Grid size={{ xs: 12, lg: 6 }} key={item}>
              <Skeleton variant="rounded" height={370} />
            </Grid>
          ))}
        </Grid>
      ) : (
        <Grid container spacing={2.5} alignItems="stretch">
          <Grid size={{ xs: 12, lg: 7 }}>
            <ChartPanel
              title="Learning trend"
              description="Cumulative human decisions recorded through the review workflow."
            >
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={learningTrend}>
                  <defs>
                    <linearGradient id="approvedFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#55c995" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#55c995" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} strokeDasharray="3 4" opacity={0.2} />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Area type="monotone" dataKey="approved" stroke="#55c995" fill="url(#approvedFill)" strokeWidth={2} />
                  <Line type="monotone" dataKey="rejected" stroke="#e26d72" strokeWidth={1.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </ChartPanel>
          </Grid>

          <Grid size={{ xs: 12, lg: 5 }}>
            <ChartPanel
              title="Production model quality"
              description="Weighted holdout metrics from the latest XGBoost retrain."
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={performance} layout="vertical" margin={{ left: 10, right: 24 }}>
                  <CartesianGrid horizontal={false} strokeDasharray="3 4" opacity={0.2} />
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis type="category" dataKey="metric" width={72} axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(value) => `${Number(value).toFixed(2)}%`} />
                  <Bar dataKey="score" fill="#7d9ee8" radius={[0, 6, 6, 0]} barSize={24} />
                </BarChart>
              </ResponsiveContainer>
            </ChartPanel>
          </Grid>

          <Grid size={{ xs: 12, lg: 7 }}>
            <ChartPanel
              title="Training samples by class"
              description="Largest supported structural classes in the regex knowledge base."
              height={340}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={classCoverage} layout="vertical" margin={{ left: 4, right: 20 }}>
                  <CartesianGrid horizontal={false} strokeDasharray="3 4" opacity={0.2} />
                  <XAxis type="number" axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={54} axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="samples" fill="#7d9ee8" radius={[0, 5, 5, 0]} barSize={11} />
                </BarChart>
              </ResponsiveContainer>
            </ChartPanel>
          </Grid>

          <Grid size={{ xs: 12, lg: 5 }}>
            <ChartPanel
              title="Internal pattern helpers by category"
              description="Coverage across structural sections, materials, bolts, and related entities."
              height={340}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryCoverage}>
                  <CartesianGrid vertical={false} strokeDasharray="3 4" opacity={0.2} />
                  <XAxis dataKey="name" tick={{ fontSize: 9 }} axisLine={false} tickLine={false} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="classes" fill="#55c995" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartPanel>
          </Grid>

          <Grid size={{ xs: 12 }}>
            <ChartPanel
              title="Retraining history"
              description="Successful production model refreshes over time."
              height={220}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={retrainTimeline}>
                  <CartesianGrid vertical={false} strokeDasharray="3 4" opacity={0.2} />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line type="stepAfter" dataKey="runs" stroke="#7d9ee8" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </ChartPanel>
          </Grid>
        </Grid>
      )}
    </Box>
  );
}
