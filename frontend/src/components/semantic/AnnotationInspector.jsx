import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Divider,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  CheckCircleOutlined,
  EditOutlined,
  HelpOutlined,
  HighlightOffOutlined,
  ScienceOutlined,
} from "@mui/icons-material";
import OperationBadge from "./OperationBadge";
import DrawingRuleCard from "./DrawingRuleCard";
import GeometryEvidenceCard from "./GeometryEvidenceCard";
import ProcessTimeline from "./ProcessTimeline";
import RepairCandidatesPanel from "./RepairCandidatesPanel";
import BenchmarkTruthPanel from "./BenchmarkTruthPanel";
import ExpectedVsActualPanel from "./ExpectedVsActualPanel";
import {
  evidenceRulesFor,
  getAcceptTargetText,
  getOperation,
  getOperationMeta,
  getRepairCandidates,
  isDemoSynthetic,
  isKnownAcceptCandidate,
  OPERATION,
} from "../../lib/semanticContract";
import { compareExpectedVsActual } from "../../lib/semanticDamageManifest";

const REPAIR_REASON_LABELS = {
  single_char_ocr_confusion_candidate: "Single-character OCR-confusion candidate, gated to an exact catalog match",
};

function ReasonList({ annotation }) {
  const operation = getOperation(annotation);
  const parse = annotation.structural_parse;

  if (operation === OPERATION.NORMALIZATION && parse) {
    return (
      <Stack spacing={0.25} sx={{ fontSize: 13.5 }}>
        <Typography variant="body2">
          Structural family: <b>{parse.family}</b> ({parse.grammar})
        </Typography>
        {Object.entries(parse.fields || {}).map(([field, value]) => (
          <Typography variant="body2" key={field}>
            Parsed {field}: <b>{String(value)}</b>
          </Typography>
        ))}
        <Typography variant="body2">
          Catalog-compatible designation: <b>{parse.catalog_exact_match ? "Yes" : "Not verified"}</b>
        </Typography>
      </Stack>
    );
  }

  if (operation === OPERATION.REPAIR) {
    return (
      <Stack spacing={0.5}>
        {(annotation.correction.reason_codes || [])
          .filter((code) => code !== "demo_synthetic_case")
          .map((code) => (
            <Typography variant="body2" key={code}>
              {REPAIR_REASON_LABELS[code] || code}
            </Typography>
          ))}
        <Alert severity="info" icon={<HelpOutlined fontSize="small" />} sx={{ py: 0, mt: 0.5 }}>
          This is a candidate/model score, not a calibrated probability — confidence is
          reported as <b>unset</b> rather than a made-up percentage.
        </Alert>
      </Stack>
    );
  }

  return null;
}

function ReviewActions({
  annotation,
  acceptTarget,
  busy,
  editing,
  editValue,
  setEditValue,
  setEditing,
  onReview,
}) {
  return (
    <Box data-testid="review-actions">
      {editing ? (
        <Stack spacing={1}>
          <Typography variant="caption" color="text.secondary">
            Manual edit is pending until you Accept. Cancel discards the draft.
          </Typography>
          <TextField
            size="small"
            label="New value"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            autoFocus
            inputProps={{ "data-testid": "manual-edit-input" }}
          />
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="contained"
              color="success"
              disabled={busy || !editValue.trim()}
              onClick={() => onReview("edit", editValue.trim())}
              data-testid="manual-edit-accept"
            >
              Accept
            </Button>
            <Button size="small" onClick={() => setEditing(false)} data-testid="manual-edit-cancel">
              Cancel
            </Button>
          </Stack>
        </Stack>
      ) : (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            size="small"
            variant="contained"
            color="success"
            startIcon={<CheckCircleOutlined fontSize="small" />}
            disabled={busy}
            onClick={() => {
              if (!acceptTarget) {
                onReview("accept", null, null);
                return;
              }
              if (isKnownAcceptCandidate(annotation, acceptTarget)) {
                onReview("accept", null, acceptTarget);
                return;
              }
              onReview("edit", acceptTarget);
            }}
            data-testid="review-accept"
          >
            Accept{acceptTarget ? ` (${acceptTarget})` : ""}
          </Button>
          <Button
            size="small"
            variant="outlined"
            color="error"
            startIcon={<HighlightOffOutlined fontSize="small" />}
            disabled={busy}
            onClick={() => onReview("reject")}
            data-testid="review-reject"
          >
            Reject
          </Button>
          <Button
            size="small"
            variant="outlined"
            startIcon={<EditOutlined fontSize="small" />}
            disabled={busy}
            onClick={() => setEditing(true)}
            data-testid="review-manual-edit"
          >
            Manual edit
          </Button>
        </Stack>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
        Status: <b>{annotation.review_status.replace("_", " ")}</b>
      </Typography>
    </Box>
  );
}

export default function AnnotationInspector({
  document,
  annotation,
  onViewSource,
  onReview,
  busy = false,
  documentId = null,
  benchmarkContext = null,
  damageCase = null,
}) {
  const [editValue, setEditValue] = useState("");
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setEditing(false);
    setEditValue(annotation?.correction?.canonical || annotation?.primary_label || "");
  }, [annotation?.annotation_id]);

  const damageComparison = damageCase
    ? compareExpectedVsActual(damageCase, annotation)
    : null;

  if (!annotation) {
    return (
      <Stack spacing={1.5}>
        {damageComparison && <ExpectedVsActualPanel comparison={damageComparison} />}
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
          <Typography color="text.secondary">
            {damageCase
              ? "No matched annotation for this case yet. Process the drawing, or browse with Next/Previous."
              : "Select a highlight on the drawing to inspect it."}
          </Typography>
        </Paper>
      </Stack>
    );
  }

  const operation = getOperation(annotation);
  const meta = getOperationMeta(operation);
  const correction = annotation.correction || {};
  const changed = correction.canonical && correction.canonical !== correction.original;
  const rules = evidenceRulesFor(document, annotation);
  const synthetic = isDemoSynthetic(annotation);
  const candidates = getRepairCandidates(annotation);
  const acceptTarget = getAcceptTargetText(annotation, damageCase);

  return (
    <Stack spacing={1.25}>
      {damageComparison && <ExpectedVsActualPanel comparison={damageComparison} />}

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <OperationBadge operation={operation} />
        <Typography variant="caption" color="text.secondary">
          p{annotation.page} · {annotation?.structural_parse?.family || "—"}
        </Typography>
        {synthetic && (
          <Tooltip title="Injected to demonstrate the repair path — this string does not appear on the real drawing.">
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, color: "text.secondary" }}>
              <ScienceOutlined fontSize="small" />
              <Typography variant="caption">Demo case</Typography>
            </Box>
          </Tooltip>
        )}
      </Stack>

      <Paper variant="outlined" sx={{ p: 1.25 }}>
        <Stack direction="row" spacing={2}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">ORIGINAL</Typography>
            <Typography
              sx={{
                fontFamily: "monospace",
                fontSize: 16,
                textDecoration: changed ? "line-through" : "none",
                color: changed ? "text.secondary" : "text.primary",
              }}
            >
              {correction.original || annotation.original_text}
            </Typography>
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">
              {operation === OPERATION.NORMALIZATION ? "NORMALIZED" : "CURRENT"}
            </Typography>
            <Typography sx={{ fontFamily: "monospace", fontSize: 16, fontWeight: 700, color: `${meta.colorKey}.main` }}>
              {annotation.effective_text || correction.canonical || annotation.primary_label}
            </Typography>
          </Box>
        </Stack>
        {acceptTarget
          && acceptTarget !== (annotation.effective_text || correction.canonical || annotation.primary_label)
          && (
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">PROPOSED</Typography>
            <Typography sx={{ fontFamily: "monospace", fontSize: 15, fontWeight: 700 }}>
              {acceptTarget}
            </Typography>
          </Box>
        )}
      </Paper>

      <ReviewActions
        annotation={annotation}
        acceptTarget={acceptTarget}
        busy={busy}
        editing={editing}
        editValue={editValue}
        setEditValue={setEditValue}
        setEditing={setEditing}
        onReview={onReview}
      />

      {!damageCase && <ProcessTimeline annotation={annotation} />}

      <Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>{meta.explanation}</Typography>
        <ReasonList annotation={annotation} />
      </Box>

      {candidates.length > 0 && (
        <RepairCandidatesPanel
          annotation={annotation}
          busy={busy}
          onAccept={(candidateText) => onReview("accept", null, candidateText)}
        />
      )}

      {rules.length > 0 && (
        <Stack spacing={1}>
          {rules.map((rule) => (
            <DrawingRuleCard key={rule.rule_id} rule={rule} onViewSource={onViewSource} />
          ))}
        </Stack>
      )}

      <Divider />

      <GeometryEvidenceCard document={document} annotation={annotation} />

      {benchmarkContext && documentId && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            Benchmark (dev only)
          </Typography>
          <BenchmarkTruthPanel documentId={documentId} annotationId={annotation.annotation_id} />
        </Box>
      )}
    </Stack>
  );
}
