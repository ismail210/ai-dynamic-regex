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
  CheckCircleOutlined,
  DownloadOutlined,
} from "@mui/icons-material";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";
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
  duplicate_members: "Duplicate members",
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
          justifyContent="space-between"
          spacing={1}
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

function GroundTruthEvaluationPanel({ report }) {
  const evaluation =
    report?.excel_evaluation ||
    report?.evaluation ||
    report?.validation?.excel_ground_truth ||
    null;
  const metrics = evaluation?.metrics || report?.metrics || report?.summary || null;
  if (!metrics && !evaluation) return null;

  const missing = evaluation?.missing_elements || report?.missing_elements || [];
  const extra = evaluation?.extra_elements || report?.extra_elements || [];
  const comparisons = evaluation?.comparisons || report?.comparisons || [];
  const precision = metrics.precision ?? metrics.section?.precision;
  const recall = metrics.recall ?? metrics.section?.recall;
  const quantityAccuracy = metrics.quantity_accuracy;
  const f1 = metrics.f1 ?? metrics.section?.f1;

  return (
    <Stack spacing={2.25}>
      <Alert severity="success">
        Excel is ground truth only — never used as prediction input. Compared section,
        quantity, length, weight, and member fields against the uploaded workbook
        {report?.excel_file ? ` (${report.excel_file})` : ""}.
      </Alert>

      <Grid container spacing={1.5}>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Precision" value={pct(precision)} color="success.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="Recall" value={pct(recall)} color="success.main" />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric label="F1" value={pct(f1)} />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric
            label="Quantity accuracy"
            value={pct(quantityAccuracy)}
            color="primary.main"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric
            label="Missing elements"
            value={metrics.missing_count ?? missing.length}
            color="error.main"
          />
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <Metric
            label="Extra elements"
            value={metrics.extra_count ?? extra.length}
            color="warning.main"
          />
        </Grid>
      </Grid>

      <Grid container spacing={1.5}>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric label="Length accuracy" value={pct(metrics.length_accuracy)} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric label="Weight accuracy" value={pct(metrics.weight_accuracy)} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric label="Member accuracy" value={pct(metrics.member_accuracy)} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric
            label="Qty coverage"
            value={pct(metrics.quantity_coverage)}
          />
        </Grid>
      </Grid>

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
        <Box sx={{ px: 2, py: 1.6, borderBottom: 1, borderColor: "divider" }}>
          <Typography variant="subtitle1" fontWeight={750}>
            Section comparison
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Predicted vs Excel ground truth for section, quantity, length, weight, member.
          </Typography>
        </Box>
        <TableContainer sx={{ maxHeight: 360 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Section</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Pred qty</TableCell>
                <TableCell align="right">GT qty</TableCell>
                <TableCell>Length</TableCell>
                <TableCell>Weight</TableCell>
                <TableCell>Member</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {comparisons.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7}>
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                      No Excel comparisons available.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {comparisons.map((row) => (
                <TableRow key={`${row.section}-${row.status}`} hover>
                  <TableCell sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                    {row.section || row.label}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={String(row.status || "").replaceAll("_", " ")}
                      color={
                        row.status === "match"
                          ? "success"
                          : row.status === "missing_member" || row.status === "missing"
                            ? "error"
                            : "warning"
                      }
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell align="right">
                    {row.predicted_quantity ?? row.prediction ?? 0}
                  </TableCell>
                  <TableCell align="right">
                    {row.expected_quantity ?? row.ground_truth ?? 0}
                  </TableCell>
                  <TableCell>
                    {row.length_match == null ? "—" : row.length_match ? "Match" : "Miss"}
                  </TableCell>
                  <TableCell>
                    {row.weight_match == null ? "—" : row.weight_match ? "Match" : "Miss"}
                  </TableCell>
                  <TableCell>
                    {row.member_match == null ? "—" : row.member_match ? "Match" : "Miss"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <Typography variant="subtitle2" fontWeight={750} mb={1}>
              Missing elements
            </Typography>
            {missing.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                None
              </Typography>
            ) : (
              <Stack spacing={0.75}>
                {missing.slice(0, 40).map((item) => (
                  <Typography
                    key={`missing-${item.section}-${item.expected_quantity}`}
                    variant="body2"
                    fontFamily="monospace"
                  >
                    {item.section} ×{item.expected_quantity}
                  </Typography>
                ))}
              </Stack>
            )}
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <Typography variant="subtitle2" fontWeight={750} mb={1}>
              Extra elements
            </Typography>
            {extra.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                None
              </Typography>
            ) : (
              <Stack spacing={0.75}>
                {extra.slice(0, 40).map((item) => (
                  <Typography
                    key={`extra-${item.section}-${item.predicted_quantity}`}
                    variant="body2"
                    fontFamily="monospace"
                  >
                    {item.section} ×{item.predicted_quantity}
                  </Typography>
                ))}
              </Stack>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Stack>
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
        <Stack direction="row" flexWrap="wrap" useFlexGap spacing={1}>
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
            justifyContent="space-between"
            spacing={1}
            alignItems={{ sm: "center" }}
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
          report ? (
            <Button variant="outlined" startIcon={<DownloadOutlined />} onClick={exportReport}>
              Export report
            </Button>
          ) : null
        }
      />

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

      <ExtractionQualityPanel report={extractionReport} />

      {!report && (
        <EmptyState
          title="No validation report"
          subtitle="Complete upload, extraction, and multimodal analysis first."
          action={
            <TipButton component={Link} to="/analyze" variant="contained">
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
