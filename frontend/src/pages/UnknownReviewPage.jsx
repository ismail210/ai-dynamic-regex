import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert,
  Box,
  Checkbox,
  Chip,
  Divider,
  Drawer,
  FormControl,
  InputLabel,
  InputAdornment,
  LinearProgress,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import {
  CheckCircleOutlined,
  CloseOutlined,
  DoneAllOutlined,
  EditOutlined,
  FileDownloadOutlined,
  RefreshOutlined,
  VisibilityOutlined,
  HighlightOffOutlined,
  InboxOutlined,
  SearchRounded,
} from "@mui/icons-material";
import {
  approveToken,
  getStatistics,
  getUnknownTokens,
  rejectToken,
  reviewBatch,
} from "../api/client";
import { downloadFile } from "../lib/utils";
import PageHeader from "../components/ui/PageHeader";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import { TipButton, TipIconButton } from "../components/ui/ActionButtons";
import PredictionExplainability from "../components/PredictionExplainability";

function confPct(row) {
  return Math.round(
    (Number(row.multimodal_confidence ?? row.overall_confidence) || 0) * 100,
  );
}

function confColor(pct) {
  if (pct >= 80) return "success";
  if (pct >= 50) return "warning";
  return "default";
}

function toCsv(rows) {
  const headers = [
    "token",
    "prediction",
    "confidence",
    "category",
    "regex_suggested",
    "source_file",
    "status",
  ];
  const esc = (v) => `"${String(v ?? "").replaceAll('"', '""')}"`;
  return [
    headers.join(","),
    ...rows.map((r) =>
      [
        r.token,
        r.prediction,
        confPct(r),
        r.category,
        r.regex_suggested,
        r.source_file,
        r.status,
      ]
        .map(esc)
        .join(",")
    ),
  ].join("\n");
}

const STATUS_OPTIONS = ["pending", "approved", "rejected", "all"];

export default function UnknownReviewPage() {
  const [searchParams] = useSearchParams();
  const initialStatus = STATUS_OPTIONS.includes(searchParams.get("status"))
    ? searchParams.get("status")
    : "pending";
  const [status, setStatus] = useState(initialStatus);
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState([]);
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [snack, setSnack] = useState({ open: false, message: "", severity: "success" });
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState("all");
  const [classFilter, setClassFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [detail, setDetail] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [sort, setSort] = useState({ key: "created_at", direction: "desc" });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const [data, stats] = await Promise.all([
        getUnknownTokens(status),
        getStatistics(),
      ]);
      setRows(data.tokens || []);
      setCounts(data.counts || {});
      setCategories(stats.categories || []);
      setSelected([]);
    } catch {
      setError("Failed to load review queue. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const classOptions = useMemo(() => {
    const set = new Set(rows.map((r) => r.prediction).filter(Boolean));
    return Array.from(set).sort();
  }, [rows]);

  const filtered = useMemo(() => {
    const now = Date.now();
    return rows.filter((r) => {
      if (categoryFilter !== "all" && r.category !== categoryFilter) return false;
      if (classFilter !== "all" && r.prediction !== classFilter) return false;
      const pct = confPct(r);
      if (confidenceFilter === "high" && pct < 80) return false;
      if (confidenceFilter === "medium" && (pct < 50 || pct >= 80)) return false;
      if (confidenceFilter === "low" && pct >= 50) return false;
      if (dateFilter !== "all" && r.created_at) {
        const age = now - new Date(r.created_at).getTime();
        const day = 86400000;
        if (dateFilter === "24h" && age > day) return false;
        if (dateFilter === "7d" && age > 7 * day) return false;
        if (dateFilter === "30d" && age > 30 * day) return false;
      }
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        String(r.token).toLowerCase().includes(q) ||
        String(r.prediction || "").toLowerCase().includes(q) ||
        String(r.category || "").toLowerCase().includes(q) ||
        String(r.source_file || "").toLowerCase().includes(q)
      );
    });
  }, [rows, search, categoryFilter, classFilter, confidenceFilter, dateFilter]);

  const sorted = useMemo(() => {
    const rowsToSort = [...filtered];
    const direction = sort.direction === "asc" ? 1 : -1;
    rowsToSort.sort((a, b) => {
      const left =
        sort.key === "confidence" ? confPct(a) : String(a[sort.key] ?? "").toLowerCase();
      const right =
        sort.key === "confidence" ? confPct(b) : String(b[sort.key] ?? "").toLowerCase();
      if (left < right) return -1 * direction;
      if (left > right) return 1 * direction;
      return 0;
    });
    return rowsToSort;
  }, [filtered, sort]);

  const pageRows = sorted.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  const allSelected =
    pageRows.length > 0 && pageRows.every((r) => selected.includes(r.id));

  const setEdit = (id, field, value) =>
    setEdits((m) => ({ ...m, [id]: { ...(m[id] || {}), [field]: value } }));

  const notify = (message, severity = "success") =>
    setSnack({ open: true, message, severity });

  const approveOne = async (row) => {
    setBusy(true);
    try {
      await approveToken(
        row.id,
        edits[row.id]?.class ||
          row.corrected_token ||
          row.suggested_shape ||
          row.prediction ||
          "",
        edits[row.id]?.notes || "",
        edits[row.id]?.category || row.category || ""
      );
      notify(`Approved ${row.token}`);
      setDetail(null);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Approve failed");
    } finally {
      setBusy(false);
    }
  };

  const rejectOne = async (row) => {
    setBusy(true);
    try {
      await rejectToken(row.id, edits[row.id]?.notes || "");
      notify(`Rejected ${row.token}`, "info");
      setDetail(null);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Reject failed");
    } finally {
      setBusy(false);
    }
  };

  const batch = async (action, ids = selected) => {
    if (!ids.length) return;
    setBusy(true);
    setProgress(0);
    try {
      await reviewBatch(ids, action);
      setProgress(100);
      notify(`${action === "approve" ? "Approved" : "Rejected"} ${ids.length} token(s)`);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Batch failed");
    } finally {
      setBusy(false);
      setProgress(0);
      setConfirm(null);
    }
  };

  const approveAllPending = async () => {
    const pendingIds = rows.filter((r) => r.status === "pending").map((r) => r.id);
    if (!pendingIds.length) {
      notify("No pending tokens to approve", "info");
      setConfirm(null);
      return;
    }
    setBusy(true);
    setProgress(10);
    try {
      // Prefer batch endpoint; chunk if very large
      const chunk = 200;
      for (let i = 0; i < pendingIds.length; i += chunk) {
        const slice = pendingIds.slice(i, i + chunk);
        await reviewBatch(slice, "approve");
        setProgress(Math.round(((i + slice.length) / pendingIds.length) * 100));
      }
      notify(`Approved all ${pendingIds.length} pending tokens`);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Approve all failed");
    } finally {
      setBusy(false);
      setProgress(0);
      setConfirm(null);
    }
  };

  const rejectAllPending = async () => {
    const pendingIds = rows.filter((r) => r.status === "pending").map((r) => r.id);
    if (!pendingIds.length) {
      notify("No pending tokens to reject", "info");
      setConfirm(null);
      return;
    }
    setBusy(true);
    setProgress(10);
    try {
      const chunk = 200;
      for (let i = 0; i < pendingIds.length; i += chunk) {
        const slice = pendingIds.slice(i, i + chunk);
        await reviewBatch(slice, "reject");
        setProgress(Math.round(((i + slice.length) / pendingIds.length) * 100));
      }
      notify(`Rejected all ${pendingIds.length} pending tokens`, "info");
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Reject all failed");
    } finally {
      setBusy(false);
      setProgress(0);
      setConfirm(null);
    }
  };

  const toggleSort = (key) => {
    setSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
    setPage(0);
  };

  const exportCsv = () => {
    downloadFile(toCsv(filtered), `review-queue-${status}.csv`, "text/csv");
    notify("Exported CSV");
  };

  return (
    <Box>
      <PageHeader
        title="Corrections"
        subtitle="Review low-confidence, conflicting, or validation-failed predictions before they enter the training dataset"
        actions={
          <>
            <TipButton
              title="Reload queue"
              variant="outlined"
              startIcon={<RefreshOutlined />}
              onClick={load}
              disabled={busy}
            >
              Refresh
            </TipButton>
            <TipButton
              title="Export filtered rows"
              variant="outlined"
              startIcon={<FileDownloadOutlined />}
              onClick={exportCsv}
            >
              Export CSV
            </TipButton>
          </>
        }
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError("")}>
          {error}
        </Alert>
      )}
      {busy && progress > 0 && (
        <Box mb={2}>
          <LinearProgress variant="determinate" value={progress} />
        </Box>
      )}

      {/* Sticky toolbar */}
      <Box
        sx={{
          position: "sticky",
          top: 56,
          zIndex: 8,
          bgcolor: "background.paper",
          p: { xs: 1.25, sm: 1.5 },
          border: 1,
          borderColor: "divider",
          mb: 2,
          borderRadius: 2,
          boxShadow: (theme) =>
            theme.palette.mode === "dark"
              ? "0 10px 28px rgba(2,7,14,.16)"
              : "0 10px 28px rgba(24,35,52,.06)",
        }}
      >
        <Stack spacing={1.25}>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
            <TextField
              placeholder="Search token, class, source…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchRounded sx={{ fontSize: 18, color: "text.secondary" }} />
                    </InputAdornment>
                  ),
                },
              }}
              sx={{ minWidth: { xs: "100%", sm: 220 }, flex: 1, maxWidth: { sm: 390 } }}
            />
            <FormControl sx={{ minWidth: { xs: "calc(50% - 4px)", sm: 130 }, flex: { xs: "1 1 140px", sm: "0 0 auto" } }}>
              <InputLabel>Status</InputLabel>
              <Select
                label="Status"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(0);
                }}
              >
                {["pending", "approved", "rejected", "all"].map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                    {s !== "all" ? ` (${counts[s] ?? 0})` : ""}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 140 }}>
              <InputLabel>Class</InputLabel>
              <Select
                label="Class"
                value={classFilter}
                onChange={(e) => {
                  setClassFilter(e.target.value);
                  setPage(0);
                }}
              >
                <MenuItem value="all">All classes</MenuItem>
                {classOptions.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 140 }}>
              <InputLabel>Confidence</InputLabel>
              <Select
                label="Confidence"
                value={confidenceFilter}
                onChange={(e) => {
                  setConfidenceFilter(e.target.value);
                  setPage(0);
                }}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="high">High ≥ 80%</MenuItem>
                <MenuItem value="medium">Medium</MenuItem>
                <MenuItem value="low">Low &lt; 50%</MenuItem>
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 130 }}>
              <InputLabel>Category</InputLabel>
              <Select
                label="Category"
                value={categoryFilter}
                onChange={(e) => {
                  setCategoryFilter(e.target.value);
                  setPage(0);
                }}
              >
                <MenuItem value="all">All</MenuItem>
                {categories.map((c) => (
                  <MenuItem key={c.id} value={c.id}>
                    {c.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 120 }}>
              <InputLabel>Date</InputLabel>
              <Select
                label="Date"
                value={dateFilter}
                onChange={(e) => {
                  setDateFilter(e.target.value);
                  setPage(0);
                }}
              >
                <MenuItem value="all">Any time</MenuItem>
                <MenuItem value="24h">Last 24h</MenuItem>
                <MenuItem value="7d">Last 7 days</MenuItem>
                <MenuItem value="30d">Last 30 days</MenuItem>
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 110 }}>
              <InputLabel>Rows</InputLabel>
              <Select
                label="Rows"
                value={rowsPerPage}
                onChange={(e) => {
                  setRowsPerPage(Number(e.target.value));
                  setPage(0);
                }}
              >
                {[10, 25, 50, 100].map((n) => (
                  <MenuItem key={n} value={n}>
                    {n}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>

          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
            <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
              <strong>{selected.length}</strong> selected · {filtered.length} shown
            </Typography>
            <TipButton
              title="Approve selected rows"
              variant="contained"
              color="success"
              startIcon={<CheckCircleOutlined />}
              disabled={busy || !selected.length || status === "approved"}
              onClick={() => setConfirm({ type: "approveSelected" })}
            >
              Approve Selected
            </TipButton>
            <TipButton
              title="Reject selected rows"
              variant="outlined"
              color="error"
              startIcon={<HighlightOffOutlined />}
              disabled={busy || !selected.length}
              onClick={() => setConfirm({ type: "rejectSelected" })}
            >
              Reject Selected
            </TipButton>
            <TipButton
              title="Approve every pending token in the queue"
              variant="outlined"
              color="success"
              startIcon={<DoneAllOutlined />}
              disabled={busy || status !== "pending" || !(counts.pending > 0)}
              loading={busy && confirm?.type === "approveAll"}
              onClick={() => setConfirm({ type: "approveAll" })}
            >
              Approve All
            </TipButton>
            <TipButton
              title="Reject every pending token in the queue"
              variant="text"
              color="error"
              startIcon={<HighlightOffOutlined />}
              disabled={busy || status !== "pending" || !(counts.pending > 0)}
              onClick={() => setConfirm({ type: "rejectAll" })}
            >
              Reject All
            </TipButton>
          </Stack>
        </Stack>
      </Box>

      <Box
        sx={{
          border: 1,
          borderColor: "divider",
          borderRadius: 2,
          bgcolor: "background.paper",
          overflow: "hidden",
        }}
      >
        <TableContainer sx={{ maxHeight: "calc(100vh - 320px)", overflowX: "auto" }}>
          <Table stickyHeader size="medium">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" sx={{ width: 48 }}>
                  <Checkbox
                    checked={allSelected}
                    indeterminate={selected.length > 0 && !allSelected}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked ? pageRows.map((r) => r.id) : []
                      )
                    }
                  />
                </TableCell>
                <TableCell>
                  <TableSortLabel
                    active={sort.key === "token"}
                    direction={sort.key === "token" ? sort.direction : "asc"}
                    onClick={() => toggleSort("token")}
                  >
                    Original token
                  </TableSortLabel>
                </TableCell>
                <TableCell>
                  <TableSortLabel
                    active={sort.key === "prediction"}
                    direction={sort.key === "prediction" ? sort.direction : "asc"}
                    onClick={() => toggleSort("prediction")}
                  >
                    Corrected token
                  </TableSortLabel>
                </TableCell>
                <TableCell>Suggested shape</TableCell>
                <TableCell align="center">
                  <TableSortLabel
                    active={sort.key === "confidence"}
                    direction={sort.key === "confidence" ? sort.direction : "asc"}
                    onClick={() => toggleSort("confidence")}
                  >
                    Confidence
                  </TableSortLabel>
                </TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Pattern helper</TableCell>
                <TableCell>Source</TableCell>
                <TableCell align="center">Status</TableCell>
                <TableCell align="right" sx={{ width: 160 }}>
                  Actions
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pageRows.map((row) => {
                const pct = confPct(row);
                const isEditing = editingId === row.id;
                return (
                  <TableRow
                    key={row.id}
                    hover
                    selected={selected.includes(row.id)}
                    sx={{
                      height: 60,
                      cursor: "pointer",
                      "&:hover": { bgcolor: "action.hover" },
                    }}
                    onClick={() => setDetail(row)}
                  >
                    <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selected.includes(row.id)}
                        onChange={(e) =>
                          setSelected((ids) =>
                            e.target.checked
                              ? [...ids, row.id]
                              : ids.filter((id) => id !== row.id)
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Typography fontFamily="monospace" fontWeight={700} fontSize={13}>
                        {row.token}
                      </Typography>
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      {isEditing ? (
                        <TextField
                          size="small"
                          value={
                            edits[row.id]?.class ??
                            row.corrected_token ??
                            row.prediction ??
                            ""
                          }
                          onChange={(e) =>
                            setEdit(row.id, "class", e.target.value.toUpperCase())
                          }
                          inputProps={{ style: { fontFamily: "monospace", fontSize: 12 } }}
                          sx={{ width: 100 }}
                        />
                      ) : (
                        <Typography fontFamily="monospace" fontSize={13}>
                          {edits[row.id]?.class ||
                            row.corrected_token ||
                            row.prediction ||
                            "-"}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography fontFamily="monospace" fontWeight={700} fontSize={12}>
                        {row.suggested_shape || row.prediction || "-"}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        size="small"
                        color={confColor(pct)}
                        label={`${row.confidence_level || "—"} ${pct}%`}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontSize={12}>
                        {row.category || "—"}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 180 }}>
                      <Typography
                        fontFamily="monospace"
                        fontSize={11}
                        color="text.secondary"
                        noWrap
                        title={row.regex_suggested}
                      >
                        {row.regex_suggested || "—"}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 140 }}>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {row.source_file || "—"}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        size="small"
                        variant="outlined"
                        color={
                          row.status === "approved"
                            ? "success"
                            : row.status === "rejected"
                            ? "error"
                            : "warning"
                        }
                        label={row.status}
                      />
                    </TableCell>
                    <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                      <Stack direction="row" spacing={0.25} sx={{ justifyContent: "flex-end" }}>
                        {row.status === "pending" && (
                          <>
                            <TipIconButton
                              title="Approve"
                              color="success"
                              disabled={busy}
                              onClick={() => approveOne(row)}
                            >
                              <CheckCircleOutlined fontSize="small" />
                            </TipIconButton>
                            <TipIconButton
                              title="Reject"
                              color="error"
                              disabled={busy}
                              onClick={() => rejectOne(row)}
                            >
                              <HighlightOffOutlined fontSize="small" />
                            </TipIconButton>
                            <TipIconButton
                              title="Edit class"
                              onClick={() =>
                                setEditingId(isEditing ? null : row.id)
                              }
                            >
                              <EditOutlined fontSize="small" />
                            </TipIconButton>
                          </>
                        )}
                        <TipIconButton title="View details" onClick={() => setDetail(row)}>
                          <VisibilityOutlined fontSize="small" />
                        </TipIconButton>
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
              {!pageRows.length && (
                <TableRow>
                  <TableCell colSpan={10} align="center" sx={{ py: 8 }}>
                    {loading ? (
                      <Skeleton variant="rounded" height={80} sx={{ mx: "auto", maxWidth: 360 }} />
                    ) : (
                      <>
                        <InboxOutlined sx={{ fontSize: 30, color: "text.disabled", mb: 1 }} />
                        <Typography fontWeight={650}>No tokens found</Typography>
                        <Typography variant="body2" color="text.secondary" mt={0.35}>
                          Adjust the filters or refresh the queue.
                        </Typography>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={filtered.length}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
          rowsPerPageOptions={[10, 25, 50, 100]}
        />
      </Box>

      {/* Detail drawer */}
      <Drawer
        anchor="right"
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 0 } }}
      >
        {detail && (
          <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
            <Stack
              direction="row"
              sx={{
                alignItems: "center",
                justifyContent: "space-between",
                px: 2.5,
                py: 2,
                borderBottom: 1,
                borderColor: "divider",
              }}
            >
              <Typography fontWeight={750}>Token details</Typography>
              <TipIconButton title="Close" onClick={() => setDetail(null)}>
                <CloseOutlined />
              </TipIconButton>
            </Stack>
            <Box sx={{ p: 2.5, flex: 1, overflow: "auto" }}>
              <Typography fontFamily="monospace" fontWeight={800} fontSize={20} mb={2}>
                {detail.token}
              </Typography>
              <Stack spacing={1.75}>
                <DetailRow label="Family" value={detail.family || "—"} mono />
                <DetailRow
                  label="Section"
                  value={detail.section || detail.suggested_shape || detail.prediction || "—"}
                  mono
                />
                <DetailRow label="Prediction" value={detail.prediction || "—"} mono />
                <DetailRow
                  label="Component ID"
                  value={detail.component_id || "-"}
                  mono
                />
                <DetailRow
                  label="Corrected Token"
                  value={detail.corrected_token || detail.section || detail.prediction || "-"}
                  mono
                />
                <DetailRow
                  label="Suggested Shape"
                  value={detail.suggested_shape || detail.section || detail.prediction || "-"}
                  mono
                />
                <DetailRow
                  label="Material"
                  value={detail.material || "-"}
                  mono
                />
                <DetailRow
                  label="Confidence"
                  value={`${detail.confidence_level || "—"} ${confPct(detail)}%`}
                />
                <DetailRow label="Category" value={detail.category || "—"} />
                <DetailRow
                  label="Pattern helper"
                  value={detail.regex_suggested || "—"}
                  mono
                />
                <DetailRow
                  label="AISC confirmation"
                  value={
                    String(detail.database_match).toLowerCase() === "true" ||
                    String(detail.aisc_confirmed).toLowerCase() === "true" ||
                    String(detail.known).toLowerCase() === "true"
                      ? "Confirmed"
                      : "Unverified (reference only)"
                  }
                />
                <DetailRow label="Source" value={detail.source_file || "—"} />
                <DetailRow
                  label="Upload / Created"
                  value={
                    detail.created_at
                      ? new Date(detail.created_at).toLocaleString()
                      : "—"
                  }
                />
                <DetailRow label="Status" value={detail.status} />
              </Stack>

              <Divider sx={{ my: 2.5 }} />
              <Typography variant="subtitle2" fontWeight={700} mb={1.25}>
                Prediction explainability
              </Typography>
              <PredictionExplainability result={detail} compact />

              <Divider sx={{ my: 2.5 }} />
              <Typography variant="subtitle2" fontWeight={700} mb={1.25}>
                Quick edit
              </Typography>
              <Stack spacing={1.25}>
                <TextField
                  label="Class"
                  value={
                    edits[detail.id]?.class ??
                    detail.corrected_token ??
                    detail.prediction ??
                    ""
                  }
                  onChange={(e) =>
                    setEdit(detail.id, "class", e.target.value.toUpperCase())
                  }
                  inputProps={{ style: { fontFamily: "monospace" } }}
                />
                <FormControl fullWidth>
                  <InputLabel>Category</InputLabel>
                  <Select
                    label="Category"
                    value={edits[detail.id]?.category ?? detail.category ?? ""}
                    onChange={(e) => setEdit(detail.id, "category", e.target.value)}
                  >
                    {categories.map((c) => (
                      <MenuItem key={c.id} value={c.id}>
                        {c.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <TextField
                  label="Notes"
                  multiline
                  minRows={2}
                  value={edits[detail.id]?.notes ?? detail.notes ?? ""}
                  onChange={(e) => setEdit(detail.id, "notes", e.target.value)}
                />
              </Stack>
            </Box>
            {detail.status === "pending" && (
              <Stack
                direction="row"
                spacing={1}
                sx={{ p: 2, borderTop: 1, borderColor: "divider" }}
              >
                <TipButton
                  title="Approve this token"
                  variant="contained"
                  color="success"
                  fullWidth
                  startIcon={<CheckCircleOutlined />}
                  disabled={busy}
                  onClick={() => approveOne(detail)}
                >
                  Approve
                </TipButton>
                <TipButton
                  title="Reject this token"
                  variant="outlined"
                  color="error"
                  fullWidth
                  startIcon={<HighlightOffOutlined />}
                  disabled={busy}
                  onClick={() => rejectOne(detail)}
                >
                  Reject
                </TipButton>
              </Stack>
            )}
          </Box>
        )}
      </Drawer>

      <ConfirmDialog
        open={Boolean(confirm)}
        title={
          confirm?.type === "approveAll"
            ? "Approve all pending tokens?"
            : confirm?.type === "rejectAll"
            ? "Reject all pending tokens?"
            : confirm?.type === "rejectSelected"
            ? "Reject selected tokens?"
            : "Approve selected tokens?"
        }
        message={
          confirm?.type === "approveAll"
            ? `This will approve all ${counts.pending ?? 0} pending tokens in the queue using their AI predictions (or edited classes).`
            : confirm?.type === "rejectAll"
            ? `This will reject all ${counts.pending ?? 0} pending tokens in the queue.`
            : confirm?.type === "rejectSelected"
            ? `Reject ${selected.length} selected token(s)?`
            : `Approve ${selected.length} selected token(s)?`
        }
        confirmLabel={
          confirm?.type === "rejectSelected" || confirm?.type === "rejectAll"
            ? "Reject"
            : "Approve"
        }
        confirmColor={
          confirm?.type === "rejectSelected" || confirm?.type === "rejectAll"
            ? "error"
            : "success"
        }
        loading={busy}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (confirm?.type === "approveAll") approveAllPending();
          else if (confirm?.type === "rejectAll") rejectAllPending();
          else if (confirm?.type === "rejectSelected") batch("reject");
          else batch("approve");
        }}
      />

      <Snackbar
        open={snack.open}
        autoHideDuration={3200}
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert
          severity={snack.severity}
          onClose={() => setSnack((s) => ({ ...s, open: false }))}
          variant="filled"
          sx={{ width: "100%" }}
        >
          {snack.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}

function DetailRow({ label, value, mono }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" fontWeight={700}>
        {label}
      </Typography>
      <Typography
        fontSize={13.5}
        fontWeight={600}
        fontFamily={mono ? "monospace" : "inherit"}
        sx={{ wordBreak: "break-word" }}
      >
        {value}
      </Typography>
    </Box>
  );
}
