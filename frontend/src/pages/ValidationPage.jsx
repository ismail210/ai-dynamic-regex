import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Grid,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import {
  ArrowForwardRounded,
  CheckCircleOutlined,
  DownloadOutlined,
} from "@mui/icons-material";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";
import WorkflowProgress from "../components/ui/WorkflowProgress";
import PredictionExplainability from "../components/PredictionExplainability";
import { approveValidationCorrection } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import { TipButton } from "../components/ui/ActionButtons";

function Metric({ label, value, color }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
      <Typography variant="caption" color="text.secondary" fontWeight={700}>
        {label}
      </Typography>
      <Typography variant="h4" fontWeight={720} color={color || "text.primary"} mt={0.5}>
        {value ?? "—"}
      </Typography>
    </Paper>
  );
}

const EXTRACTION_STATUS_COLOR = {
  VALID: "success",
  SUSPICIOUS: "warning",
  BROKEN: "error",
  INVALID: "error",
};

const SEVERITY_COLOR = {
  PASS: "success",
  WARNING: "warning",
  FAIL: "error",
};

const ISSUE_LABELS = {
  extraction_quality: "Extraction quality",
  prediction_confidence: "Prediction confidence",
  geometry_consistency: "Geometry consistency",
  graph_consistency: "Graph consistency",
  engineering_rules: "Engineering rules",
  missing_members: "Missing members",
  impossible_members: "Impossible members",
  wrong_section_names: "Wrong section names",
  missing_quantities: "Missing quantities",
  incorrect_quantities: "Incorrect quantities",
  missing_dimensions: "Missing dimensions",
  unknown_labels: "Unknown labels",
};

function severityChip(status) {
  return (
    <Chip
      size="small"
      label={status || "—"}
      color={SEVERITY_COLOR[status] || "default"}
    />
  );
}

function ExtractionQualityPanel({ report }) {
  if (!report) return null;
  const quality = report.quality || report.diagnostics || {};
  const counts = quality.status_counts || {};
  const tokens = report.tokens || [];
  const layout = quality.layout || {};

  return (
    <Paper variant="outlined" sx={{ p: 2.25, mb: 2.5 }}>
      <Stack spacing={2}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          sx={{ justifyContent: "space-between" }}
        >
          <Box>
            <Typography variant="h6" fontWeight={750}>
              Extraction quality preflight
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Prediction has not started. Review extraction quality first.
            </Typography>
          </Box>
          <Chip
            label={`${quality.status || "INVALID"} · ${Math.round(Number(quality.score || 0) * 100)}%`}
            color={EXTRACTION_STATUS_COLOR[quality.status] || "default"}
          />
        </Stack>

        <Grid container spacing={1.25}>
          {[
            ["Valid", counts.VALID || 0],
            ["Suspicious", counts.SUSPICIOUS || 0],
            ["Broken", counts.BROKEN || 0],
            ["Invalid", counts.INVALID || 0],
            ["OCR repairs", quality.ocr_repairs || 0],
            ["Split labels", quality.split_labels_reconstructed || 0],
            ["Rotated", quality.rotated_tokens || 0],
            ["Noise removed", quality.noise_removed || 0],
            ["Tables", layout.tables || 0],
            ["Schedules", layout.schedules || 0],
            ["Callouts", layout.callouts || 0],
            ["Dimensions", layout.dimensions || 0],
            ["Title blocks", layout.title_blocks || 0],
          ].map(([label, value]) => (
            <Grid size={{ xs: 6, sm: 4, md: 2 }} key={label}>
              <Metric label={label} value={value} />
            </Grid>
          ))}
        </Grid>

        {(quality.warnings || []).length > 0 && (
          <Alert severity={quality.status === "INVALID" ? "error" : "warning"}>
            {(quality.warnings || []).join(" · ")}
          </Alert>
        )}

        <TableContainer sx={{ maxHeight: 280 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Status</TableCell>
                <TableCell>Text</TableCell>
                <TableCell>Page</TableCell>
                <TableCell align="right">Confidence</TableCell>
                <TableCell>Context</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tokens.slice(0, 80).map((token) => (
                <TableRow key={token.token_id} hover>
                  <TableCell>
                    <Chip
                      size="small"
                      label={token.extraction_status || token.status}
                      color={
                        EXTRACTION_STATUS_COLOR[
                          token.extraction_status || token.status
                        ] || "default"
                      }
                    />
                  </TableCell>
                  <TableCell sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                    {token.text}
                  </TableCell>
                  <TableCell>{token.page}</TableCell>
                  <TableCell align="right">
                    {Math.round(Number(token.confidence || 0) * 100)}%
                  </TableCell>
                  <TableCell sx={{ maxWidth: 360 }}>
                    <Typography variant="caption" color="text.secondary">
                      {token.surrounding_text || token.context?.line_text || "—"}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Stack>
    </Paper>
  );
}

function evidenceSummary(evidence = {}) {
  const parts = [];
  if (evidence.extraction_status) {
    parts.push(`Extraction ${evidence.extraction_status}`);
  }
  if (evidence.confidence != null) {
    parts.push(`AI ${Math.round(Number(evidence.confidence) * 100)}%`);
  }
  if (evidence.geometry_score != null) {
    parts.push(`Geometry ${Math.round(Number(evidence.geometry_score) * 100)}%`);
  }
  if (evidence.graph_score != null) {
    parts.push(`Graph ${Math.round(Number(evidence.graph_score) * 100)}%`);
  }
  if (evidence.rule_score != null) {
    parts.push(`Rules ${Math.round(Number(evidence.rule_score) * 100)}%`);
  }
  if (evidence.expected_quantity != null || evidence.predicted_quantity != null) {
    parts.push(
      `Qty pred ${evidence.predicted_quantity ?? "—"} / exp ${evidence.expected_quantity ?? "—"}`,
    );
  }
  if (evidence.database_match != null) {
    parts.push(
      evidence.database_match
        ? "AISC confirmed (reference)"
        : "AISC unverified (reference only)",
    );
  }
  return parts.join(" · ") || "Multimodal evidence available";
}

function correctionLabel(suggestion) {
  if (!suggestion) return "—";
  if (suggestion.section) return suggestion.section;
  if (suggestion.quantity != null) return `Qty ${suggestion.quantity}`;
  if (suggestion.action) return suggestion.action;
  return "—";
}

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value) * 1000) / 10}%`;
}

const GT_FILTERS = ["Largest errors", "Missing", "Excess", "All"];

function GroundTruthEvaluationPanel({ report }) {
  const [showDetails, setShowDetails] = useState(false);
  const [filter, setFilter] = useState("Largest errors");
  const evaluation =
    report?.excel_evaluation ||
    report?.evaluation ||
    report?.validation?.excel_ground_truth ||
    null;
  const metrics = evaluation?.metrics || report?.metrics || report?.summary || null;
  if (!metrics && !evaluation) return null;

  const comparisons = evaluation?.comparisons || report?.comparisons || [];
  // Section × quantity histogram overlap (canonical_takeoff_eval). This is
  // NOT object/member-level matching — see the caption below.
  const rows = (
    evaluation?.estimator_table ||
    report?.estimator_table ||
    comparisons.map((r) => ({
      section: r.section || r.label,
      ground_truth: r.expected_quantity ?? r.ground_truth ?? 0,
      predicted: r.predicted_quantity ?? r.prediction ?? 0,
      correctly_caught:
        r.caught ?? Math.min(r.predicted_quantity ?? 0, r.expected_quantity ?? 0),
    }))
  ).map((r) => ({
    ...r,
    difference: (r.predicted || 0) - (r.ground_truth || 0),
    match_pct:
      r.ground_truth > 0
        ? Math.round(((r.correctly_caught ?? 0) / r.ground_truth) * 1000) / 10
        : null,
  }));

  const gtTotal = metrics.ground_truth_total;
  const auto = metrics.auto_resolved_total ?? metrics.predicted_total;
  const matching = metrics.matching_quantity ?? metrics.caught;
  const sectionPrecision =
    metrics.section_precision_pct ?? (metrics.precision != null ? metrics.precision * 100 : null);
  const sectionRecall =
    metrics.section_recall_pct ??
    metrics.overall_success_pct ??
    (metrics.recall != null ? metrics.recall * 100 : null);
  const f1 =
    metrics.f1 != null
      ? metrics.f1 * 100
      : sectionPrecision != null && sectionRecall != null && sectionPrecision + sectionRecall > 0
        ? Math.round(
            (2 * sectionPrecision * sectionRecall) / (sectionPrecision + sectionRecall) * 10,
          ) / 10
        : null;
  const reviewQty = metrics.review_member_quantity ?? 0;
  const weakQty = metrics.weak_geometry_quantity ?? 0;

  const fmtPct = (v) => (v == null ? "—" : `${Math.round(v * 10) / 10}%`);

  const filtered = rows
    .filter((r) => {
      if (filter === "Missing") return r.predicted === 0 && r.ground_truth > 0;
      if (filter === "Excess") return r.difference > 0;
      return true;
    })
    .sort((a, b) =>
      filter === "All"
        ? (b.ground_truth || 0) - (a.ground_truth || 0)
        : Math.abs(b.difference) - Math.abs(a.difference),
    );

  return (
    <Stack spacing={2.25}>
      <Alert severity="info" variant="outlined">
        Excel is ground truth only — never used as a prediction input. Numbers below
        compare the <strong>section-quantity histogram</strong> (Σ&nbsp;min(Estima3D,
        ground&nbsp;truth) per section); this is not object-level member matching, so a
        section difference does not by itself mean a member was invented.
        {report?.excel_file ? ` (${report.excel_file})` : ""}
      </Alert>

      <Typography variant="subtitle1" fontWeight={750}>
        Ground truth comparison
      </Typography>
      <Grid container spacing={1.5}>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Ground truth" value={gtTotal ?? "—"} />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Estima3D" value={auto ?? "—"} />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Matching quantity" value={matching ?? "—"} color="success.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Section precision" value={fmtPct(sectionPrecision)} />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Section recall" value={fmtPct(sectionRecall)} />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="F1" value={fmtPct(f1)} />
        </Grid>
      </Grid>

      {(reviewQty > 0 || weakQty > 0) && (
        <Typography variant="body2" color="text.secondary">
          <strong>{auto}</strong> members auto-resolved · <strong>{reviewQty}</strong> need
          section review · <strong>{weakQty}</strong> weak geometry candidates. Members
          whose section is geometry/adjacency-only are held for Drawing Review, not
          auto-counted.
        </Typography>
      )}

      <Button
        size="small"
        variant="text"
        onClick={() => setShowDetails((v) => !v)}
        sx={{ alignSelf: "flex-start" }}
      >
        {showDetails ? "Hide technical diagnostics" : "Technical diagnostics"}
      </Button>
      {showDetails && (
        <Grid container spacing={1.5}>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="Excess quantity by section" value={metrics.excess_quantity ?? metrics.false_positives ?? "—"} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="Missing sections" value={metrics.missing_count ?? "—"} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="Extra sections" value={metrics.extra_count ?? "—"} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="Catalog-invalid predictions" value={metrics.catalog_invalid_predictions ?? "—"} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="Abstained (to review)" value={metrics.abstained_predictions ?? "—"} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="Unsupported GT qty" value={metrics.unsupported_gt_quantity ?? "—"} />
          </Grid>
          <Grid size={{ xs: 6, md: 3 }}>
            <Metric label="Excluded GT qty" value={metrics.excluded_gt_quantity ?? "—"} />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Typography variant="caption" color="text.secondary">
              Scope: {metrics.scope || "primary_framing"} (beams, columns, braces, joists).
              Connection angles / stiffeners ({metrics.unsupported_gt_quantity ?? 0}) and
              deck / misc / unparseable rows ({metrics.excluded_gt_quantity ?? 0}) are
              recorded but not counted.
            </Typography>
          </Grid>
        </Grid>
      )}

      {(evaluation?.report_path || report?.report_path || report?.markdown_report_path) && (
        <Typography variant="caption" color="text.secondary">
          Automatic report saved
          {report?.markdown_report_path
            ? `: ${String(report.markdown_report_path).split("/").pop()}`
            : evaluation?.markdown_report_path
              ? `: ${String(evaluation.markdown_report_path).split("/").pop()}`
              : ""}
          {report?.registered_pair_id
            ? ` · Registered training pair: ${report.registered_pair_id}`
            : ""}
          {report?.dataset_build && !report.dataset_build.error
            ? " · Paired dataset refreshed"
            : ""}
        </Typography>
      )}

      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        <Box
          sx={{
            px: 2, py: 1.4, borderBottom: 1, borderColor: "divider",
            display: "flex", flexWrap: "wrap", gap: 1,
            alignItems: "center", justifyContent: "space-between",
          }}
        >
          <Typography variant="subtitle1" fontWeight={750}>
            Section takeoff vs ground truth
          </Typography>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
            {GT_FILTERS.map((f) => (
              <Chip
                key={f}
                size="small"
                label={f}
                color={filter === f ? "primary" : "default"}
                variant={filter === f ? "filled" : "outlined"}
                onClick={() => setFilter(f)}
              />
            ))}
          </Stack>
        </Box>
        <TableContainer sx={{ maxHeight: 420 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Section</TableCell>
                <TableCell align="right">Ground Truth</TableCell>
                <TableCell align="right">Estima3D</TableCell>
                <TableCell align="right">Difference</TableCell>
                <TableCell align="right">Match %</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                      No sections in this view.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {filtered.map((row) => (
                <TableRow key={row.section} hover>
                  <TableCell sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                    {row.section}
                  </TableCell>
                  <TableCell align="right">{row.ground_truth}</TableCell>
                  <TableCell align="right">{row.predicted}</TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color:
                        row.difference === 0
                          ? "text.secondary"
                          : row.difference > 0
                            ? "warning.main"
                            : "error.main",
                      fontWeight: 700,
                    }}
                  >
                    {row.difference > 0 ? `+${row.difference}` : row.difference}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color:
                        row.match_pct == null
                          ? "text.disabled"
                          : row.match_pct >= 90
                            ? "success.main"
                            : row.match_pct >= 60
                              ? "warning.main"
                              : "error.main",
                      fontWeight: 700,
                    }}
                  >
                    {row.match_pct == null ? "—" : `${row.match_pct}%`}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Stack>
  );
}

function AnonymousDimensionMetricsPanel({ metrics }) {
  if (!metrics) return null;
  return (
    <Paper variant="outlined" sx={{ p: 2.25, mb: 2.5 }}>
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="h6" fontWeight={750}>
            Anonymous dimension inference
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Contextual resolver outcomes for extracted anonymous dimensions.
          </Typography>
        </Box>
        <Grid container spacing={1.25}>
          {[
            ["Anonymous dims", metrics.anonymous_dimension_count ?? 0],
            ["Needs context", metrics.needs_context_count ?? 0],
            ["Promoted", metrics.promoted_count ?? 0],
            ["With candidates", metrics.with_semantic_candidates_count ?? 0],
            ["Abstention rate", pct(metrics.abstention_rate)],
            ["Promotion rate", pct(metrics.promotion_rate)],
          ].map(([label, value]) => (
            <Grid size={{ xs: 6, sm: 4, md: 2 }} key={label}>
              <Metric label={label} value={value} />
            </Grid>
          ))}
        </Grid>
      </Stack>
    </Paper>
  );
}

function MultiModalReport({ report, onApprove, approvingId }) {
  const summary = report?.summary || {};
  const validation = report?.validation || {};
  const tokens = validation.tokens || [];
  const issues = (validation.actionable_issues || validation.issues || []).filter(
    (issue) => issue.severity === "WARNING" || issue.severity === "FAIL",
  );
  const [issueFilter, setIssueFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [selectedPrediction, setSelectedPrediction] = useState(null);

  const filteredIssues = useMemo(() => {
    return issues.filter((issue) => {
      if (severityFilter !== "all" && issue.severity !== severityFilter) return false;
      if (issueFilter !== "all" && issue.type !== issueFilter) return false;
      return true;
    });
  }, [issues, issueFilter, severityFilter]);

  const typeCounts = validation.summary?.issue_types || {};

  return (
    <Stack spacing={2.25}>
      <AnonymousDimensionMetricsPanel
        metrics={
          report?.anonymous_dimension_metrics
          || report?.summary?.anonymous_dimension_metrics
        }
      />
      <GroundTruthEvaluationPanel report={report} />

      <Alert severity="info">
        Validation uses extraction, confidence, geometry, graph, engineering rules,
        duplicates, quantities, and labels. AISC database existence never alone decides FAIL.
      </Alert>

      <Grid container spacing={1.5}>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="PASS" value={summary.pass ?? validation.summary?.pass} color="success.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="WARNING" value={summary.warning ?? validation.summary?.warning} color="warning.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="FAIL" value={summary.fail ?? validation.summary?.fail} color="error.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric
            label="Approvable issues"
            value={validation.summary?.approvable_issues ?? 0}
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Missing members" value={summary.missing_components ?? typeCounts.missing_members ?? 0} color="error.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric
            label="Validation score"
            value={`${Math.round((summary.validation_score || validation.summary?.pass_rate || 0) * 100)}%`}
            color="success.main"
          />
        </Grid>
      </Grid>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" fontWeight={750} mb={1.25}>
          Issue coverage
        </Typography>
        <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
          {Object.entries(ISSUE_LABELS).map(([key, label]) => (
            <Chip
              key={key}
              size="small"
              variant={issueFilter === key ? "filled" : "outlined"}
              color={issueFilter === key ? "primary" : "default"}
              label={`${label}: ${typeCounts[key] || 0}`}
              onClick={() => setIssueFilter(issueFilter === key ? "all" : key)}
            />
          ))}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.6, borderBottom: 1, borderColor: "divider" }}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={1}
            sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
          >
            <Box>
              <Typography variant="subtitle1" fontWeight={750}>
                Validation issues
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Every issue includes why, evidence, and a suggested correction when available.
              </Typography>
            </Box>
            <Stack direction="row" spacing={1}>
              {["all", "FAIL", "WARNING"].map((value) => (
                <Chip
                  key={value}
                  size="small"
                  clickable
                  label={value}
                  color={severityFilter === value ? "primary" : "default"}
                  variant={severityFilter === value ? "filled" : "outlined"}
                  onClick={() => setSeverityFilter(value)}
                />
              ))}
            </Stack>
          </Stack>
        </Box>
        <TableContainer sx={{ maxHeight: 560 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Severity</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Member</TableCell>
                <TableCell>Why</TableCell>
                <TableCell>Evidence</TableCell>
                <TableCell>Suggested correction</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredIssues.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7}>
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                      No actionable issues for this filter.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {filteredIssues.map((issue) => {
                const suggestion = issue.suggested_correction;
                const issueKey = `${issue.issue_id}-${issue.severity}`;
                return (
                  <TableRow key={issueKey} hover>
                    <TableCell>{severityChip(issue.severity)}</TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight={650}>
                        {ISSUE_LABELS[issue.type] || issue.type}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                      <Stack spacing={0.25}>
                        <span>{issue.predicted_shape || issue.original_token || "—"}</span>
                        <Typography variant="caption" color="text.secondary">
                          {issue.component_id || issue.object_id || ""}
                        </Typography>
                      </Stack>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 260 }}>
                      <Typography variant="body2">{issue.why}</Typography>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 280 }}>
                      <Typography variant="caption" color="text.secondary">
                        {evidenceSummary(issue.evidence)}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                      <Stack spacing={0.25}>
                        <span>{correctionLabel(suggestion)}</span>
                        <Typography variant="caption" color="text.secondary" fontFamily="inherit">
                          {suggestion?.reason || suggestion?.source || ""}
                        </Typography>
                      </Stack>
                    </TableCell>
                    <TableCell align="right">
                      {issue.approvable && suggestion?.section ? (
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<CheckCircleOutlined />}
                          disabled={approvingId === issueKey}
                          onClick={() => onApprove(issue, issueKey)}
                        >
                          Approve
                        </Button>
                      ) : (
                        <Typography variant="caption" color="text.disabled">
                          —
                        </Typography>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        <Box sx={{ px: 2, py: 1.6, borderBottom: 1, borderColor: "divider" }}>
          <Typography variant="subtitle1" fontWeight={750}>
            Component outcomes
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Aggregate PASS / WARNING / FAIL from multimodal checks per member.
          </Typography>
        </Box>
        <TableContainer sx={{ maxHeight: 420 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Component</TableCell>
                <TableCell>Original</TableCell>
                <TableCell>Section</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Confidence</TableCell>
                <TableCell>Issues</TableCell>
                <TableCell>Correction</TableCell>
                <TableCell align="right">Explain</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tokens.map((token) => {
                const prediction = (report.predictions || []).find(
                  (item) =>
                    (item.component_id || item.object_id)
                    === (token.component_id || token.object_id),
                ) || token;
                return (
                <TableRow key={token.object_id || token.component_id} hover>
                  <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                    {token.component_id || token.object_id || "-"}
                  </TableCell>
                  <TableCell sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                    {token.original_token}
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.25}>
                      <Typography fontFamily="monospace" fontWeight={700} fontSize={13}>
                        {token.corrected_token || token.section || token.predicted_shape}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {[token.family, token.entity_type].filter(Boolean).join(" · ")}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell>{severityChip(token.status)}</TableCell>
                  <TableCell align="right">
                    {Math.round(Number(token.confidence || 0) * 100)}%
                  </TableCell>
                  <TableCell sx={{ maxWidth: 280 }}>
                    <Typography variant="caption" color="text.secondary">
                      {(token.detected_issues || []).map((type) => ISSUE_LABELS[type] || type).join(", ")
                        || "No actionable issues"}
                    </Typography>
                  </TableCell>
                  <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                    {correctionLabel(token.correction_suggestions?.[0])}
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => setSelectedPrediction(prediction)}>
                      Details
                    </Button>
                  </TableCell>
                </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
      <Dialog
        open={Boolean(selectedPrediction)}
        onClose={() => setSelectedPrediction(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Prediction explainability</DialogTitle>
        <DialogContent>
          <PredictionExplainability result={selectedPrediction} />
        </DialogContent>
      </Dialog>
    </Stack>
  );
}

export default function ValidationPage() {
  const { data: report, extraction: extractionReport } = useAnalysis();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [approvingId, setApprovingId] = useState("");
  const [showTech, setShowTech] = useState(false);

  async function approveIssue(issue, issueKey) {
    const suggestion = issue.suggested_correction || {};
    if (!suggestion.section) return;
    setApprovingId(issueKey);
    setError("");
    setNotice("");
    try {
      await approveValidationCorrection({
        documentId: report?.document_id,
        objectId: issue.object_id || issue.component_id || issue.issue_id,
        correctLabel: suggestion.section,
        prediction: {
          original_token: issue.original_token,
          predicted_shape: issue.predicted_shape,
          confidence: issue.evidence?.confidence,
          entity_type: issue.evidence?.entity_type,
        },
        features: {
          issue_type: issue.type,
          evidence: issue.evidence,
          original_token: issue.original_token,
        },
        notes: `Approved validation correction: ${issue.why}`,
        correctGeometry: issue.evidence?.geometry_preview || null,
      });
      setNotice(`Approved correction ${suggestion.section} for ${issue.type.replaceAll("_", " ")}`);
    } catch (err) {
      setError(err.friendlyMessage || err?.response?.data?.detail || err.message || "Failed to approve correction");
    } finally {
      setApprovingId("");
    }
  }

  function exportReport() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `takeoff_validation_${report.pdf_file || report.document_id || "report"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Box>
      <PageHeader
        title="Validation"
        subtitle="AI-based PASS / WARNING / FAIL with reasons across extraction, OCR, geometry, graph, engineering rules, duplicates, and labels."
        actions={
          <>
            {report ? (
              <Button variant="outlined" startIcon={<DownloadOutlined />} onClick={exportReport}>
                Export report
              </Button>
            ) : null}
            {report ? (
              <TipButton
                component={Link}
                to="/takeoff"
                variant="contained"
                endIcon={<ArrowForwardRounded />}
              >
                Continue to Takeoff
              </TipButton>
            ) : null}
          </>
        }
      />
      <WorkflowProgress step="validate" />

      <Paper variant="outlined" sx={{ p: 2.25, mb: 2.5 }}>
        <Typography variant="body2" color="text.secondary">
          Validation is generated by the analysis stage. It does not upload or
          reprocess the drawing.
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
        {notice && (
          <Alert severity="success" sx={{ mt: 2 }}>
            {notice}
          </Alert>
        )}
      </Paper>

      {extractionReport && (
        <Box sx={{ mb: 2.5 }}>
          <Button
            size="small"
            variant="text"
            onClick={() => setShowTech((v) => !v)}
          >
            {showTech ? "Hide technical diagnostics" : "Technical diagnostics"}
          </Button>
          {showTech && (
            <Box sx={{ mt: 1 }}>
              <ExtractionQualityPanel report={extractionReport} />
            </Box>
          )}
        </Box>
      )}

      {!report && (
        <EmptyState
          title="No validation report"
          subtitle="Complete upload, extraction, and multimodal analysis first."
          action={
            <TipButton component={Link} to="/analysis" variant="contained">
              Go to analysis
            </TipButton>
          }
        />
      )}

      {report?.pipeline === "text_geometry_graph_fusion" && (
        <MultiModalReport
          report={report}
          onApprove={approveIssue}
          approvingId={approvingId}
        />
      )}

      {report && report?.pipeline !== "text_geometry_graph_fusion" && (
        <Stack spacing={2}>
          <Alert severity="info">
            Excel ground-truth evaluation report. Multimodal validation also supports the same
            Excel comparison when both PDF and Excel are uploaded together.
          </Alert>
          <GroundTruthEvaluationPanel report={report} />
        </Stack>
      )}
    </Box>
  );
}
