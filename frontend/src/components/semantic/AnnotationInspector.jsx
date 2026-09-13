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
import {
  evidenceRulesFor,
  getOperation,
  getOperationMeta,
  getRepairCandidates,
  isDemoSynthetic,
  OPERATION,
} from "../../lib/semanticContract";

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

export default function AnnotationInspector({
  document,
  annotation,
  onViewSource,
  onReview,
  busy = false,
  documentId = null,
  benchmarkContext = null,
}) {
  const [editValue, setEditValue] = useState("");
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setEditing(false);
    setEditValue(annotation?.correction?.canonical || annotation?.primary_label || "");
  }, [annotation?.annotation_id]);

  if (!annotation) {
    return (
      <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
        <Typography color="text.secondary">
          Select an annotation on the drawing to inspect it.
        </Typography>
      </Paper>
    );
  }

  const operation = getOperation(annotation);
  const meta = getOperationMeta(operation);
  const correction = annotation.correction || {};
  const changed = correction.canonical && correction.canonical !== correction.original;
  const rules = evidenceRulesFor(document, annotation);
  const synthetic = isDemoSynthetic(annotation);

  const candidates = getRepairCandidates(annotation);

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <OperationBadge operation={operation} />
        {synthetic && (
          <Tooltip title="Injected to demonstrate the repair path — this string does not appear on the real drawing. See docs/upstream_semantic_preprocessor.md.">
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, color: "text.secondary" }}>
              <ScienceOutlined fontSize="small" />
              <Typography variant="caption">Demo case</Typography>
            </Box>
          </Tooltip>
        )}
        {benchmarkContext && (
          <Tooltip title={`Attacked from real project: ${benchmarkContext.source_pdf}`}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, color: "text.secondary" }}>
              <ScienceOutlined fontSize="small" />
              <Typography variant="caption">Attack Benchmark</Typography>
            </Box>
          </Tooltip>
        )}
      </Stack>

      <ProcessTimeline annotation={annotation} />

      <Paper variant="outlined" sx={{ p: 1.5 }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">
              ORIGINAL
            </Typography>
            <Typography
              sx={{
                fontFamily: "monospace",
                fontSize: 17,
                textDecoration: changed ? "line-through" : "none",
                color: changed ? "text.secondary" : "text.primary",
              }}
            >
              {correction.original || annotation.original_text}
            </Typography>
          </Box>
          {changed && (
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="caption" color="text.secondary">
                CANONICAL
              </Typography>
              <Typography sx={{ fontFamily: "monospace", fontSize: 17, fontWeight: 700, color: `${meta.colorKey}.main` }}>
                {correction.canonical}
              </Typography>
            </Box>
          )}
        </Stack>
        {annotation.modifiers?.length > 0 && (
          <>
            <Divider sx={{ my: 1 }} />
            <Typography variant="caption" color="text.secondary">MODIFIER</Typography>
            {annotation.modifiers.map((m) => (
              <Typography key={m.raw_text} sx={{ fontFamily: "monospace", fontSize: 14 }}>
                {m.raw_text} <Typography component="span" variant="caption" color="text.secondary">({m.type.replace("_", " ")})</Typography>
              </Typography>
            ))}
          </>
        )}
      </Paper>

      <Box>
        <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
          Why
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>{meta.explanation}</Typography>
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
        <Box>
          <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
            Evidence
          </Typography>
          <Stack spacing={1} sx={{ mt: 0.5 }}>
            {rules.map((rule) => (
              <DrawingRuleCard key={rule.rule_id} rule={rule} onViewSource={onViewSource} />
            ))}
          </Stack>
        </Box>
      )}

      <Box>
        <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
          Geometry
        </Typography>
        <Box sx={{ mt: 0.5 }}>
          <GeometryEvidenceCard document={document} annotation={annotation} />
        </Box>
      </Box>

      <Box>
        <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
          Location
        </Typography>
        <Typography variant="body2">
          Page {annotation.page} · <Typography component="span" sx={{ fontFamily: "monospace" }}>{annotation.annotation_id}</Typography>
        </Typography>
      </Box>

      <Divider />

      <Box>
        <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4, display: "block", mb: 1 }}>
          Review
        </Typography>
        {editing ? (
          <Stack spacing={1}>
            <TextField
              size="small"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              autoFocus
            />
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                variant="contained"
                disabled={busy || !editValue.trim()}
                onClick={() => onReview("edit", editValue.trim())}
              >
                Save
              </Button>
              <Button size="small" onClick={() => setEditing(false)}>Cancel</Button>
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
              onClick={() => onReview("accept", null, candidates[0]?.candidate_text)}
            >
              Accept{candidates.length > 0 ? ` proposal (${candidates[0].candidate_text})` : ""}
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="error"
              startIcon={<HighlightOffOutlined fontSize="small" />}
              disabled={busy}
              onClick={() => onReview("reject")}
            >
              Reject
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<EditOutlined fontSize="small" />}
              disabled={busy}
              onClick={() => setEditing(true)}
            >
              Edit text
            </Button>
          </Stack>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
          Status: <b>{annotation.review_status.replace("_", " ")}</b>
        </Typography>
      </Box>

      {benchmarkContext && documentId && (
        <Box>
          <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4, display: "block", mb: 0.5 }}>
            Benchmark (dev only)
          </Typography>
          <BenchmarkTruthPanel documentId={documentId} annotationId={annotation.annotation_id} />
        </Box>
      )}
    </Stack>
  );
}
