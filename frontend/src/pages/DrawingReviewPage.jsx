import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { PictureAsPdfOutlined, TableRowsOutlined } from "@mui/icons-material";
import { approveValidationCorrection, documentPdfUrl } from "../api/client";
import PdfDocumentViewer from "../components/pdf/PdfDocumentViewer";
import SectionResultsList from "../components/pdf/SectionResultsList";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import { TipButton } from "../components/ui/ActionButtons";
import { useAnalysis } from "../context/AnalysisContext";
import {
  formatCandidateLabel,
  getPredictionLocation,
  getSection,
  isInferredLocation,
} from "../lib/predictionContract";

export default function DrawingReviewPage() {
  const { document, data, restoreNotice } = useAnalysis();
  const [selection, setSelection] = useState(null);
  const [correctLabel, setCorrectLabel] = useState("");
  const [reviewMessage, setReviewMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const results = data?.results || data?.predictions || [];
  const pdfUrl = document?.document_id
    ? documentPdfUrl(document.document_id)
    : null;

  const locateHint = useMemo(() => {
    if (!selection) {
      return "Select a steel section on the right to scroll, zoom, and highlight it on the drawing.";
    }
    if (!selection.location?.hasLocation) {
      return "This section has no page/bbox on the drawing — location was not captured during extraction.";
    }
    if (isInferredLocation(selection.result)) {
      return `Inferred member location for ${getSection(selection.result) || "section"} on page ${selection.location.pageNumber} — no OCR label on the drawing.`;
    }
    return `Locating ${getSection(selection.result) || "section"} on page ${selection.location.pageNumber}.`;
  }, [selection]);

  const submitReview = async (userDecision) => {
    if (!selection?.result || !document?.document_id) return;
    setBusy(true);
    setReviewMessage("");
    try {
      const result = selection.result;
      await approveValidationCorrection({
        documentId: document.document_id,
        objectId: result.object_id || result.component_id || selection.key,
        correctLabel:
          userDecision === "approve" || userDecision === "correct"
            ? correctLabel || getSection(result)
            : correctLabel || "",
        prediction: result,
        features: result.features || {},
        notes: `drawing_review:${userDecision}`,
        userDecision,
      });
      setReviewMessage(`Saved review: ${userDecision}`);
    } catch (error) {
      setReviewMessage(
        error?.response?.data?.detail || error.message || "Review failed",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!data || !document?.document_id) {
    if (restoreNotice) {
      const isMissingSource = restoreNotice.kind === "missing-source";
      return (
        <EmptyState
          title={
            isMissingSource
              ? "Original file no longer available"
              : "Previous analysis could not be restored"
          }
          subtitle={restoreNotice.message}
          action={
            <TipButton component={Link} to="/upload" variant="contained">
              {isMissingSource ? "Upload the PDF again" : "Start new analysis"}
            </TipButton>
          }
        />
      );
    }
    return (
      <EmptyState
        title="Drawing review needs an analysis"
        subtitle="Upload, extract, and analyze a drawing first, then open this page to locate sections on the PDF."
        action={
          <TipButton component={Link} to="/upload" variant="contained">
            Start workflow
          </TipButton>
        }
      />
    );
  }

  const ann =
    selection?.result?.explanation?.annotation_interpretation ||
    selection?.result?.annotation_interpretation ||
    null;
  // Older analyses have no annotation payload, and the state may arrive in any
  // casing, so normalize instead of assuming the field exists.
  const annotationState = String(ann?.understandability?.status || "")
    .trim()
    .toUpperCase();
  const annotationType = String(ann?.annotation?.annotation_type || "")
    .trim()
    .toUpperCase();
  const topK = Array.isArray(ann?.ambiguity?.top_k)
    ? ann.ambiguity.top_k
    : Array.isArray(selection?.result?.canonical_candidates)
      ? selection.result.canonical_candidates
      : [];

  return (
    <Stack
      spacing={1.75}
      sx={{ height: { md: "calc(100vh - 140px)" }, minHeight: 520 }}
    >
      <PageHeader
        title="Drawing review"
        subtitle="PDF on the left, predicted steel sections on the right — click a section to zoom and highlight it."
        actions={
          <TipButton
            component={Link}
            to="/results"
            variant="outlined"
            startIcon={<TableRowsOutlined />}
          >
            Results table
          </TipButton>
        }
      />

      <Alert
        severity={
          selection && !selection.location?.hasLocation ? "warning" : "info"
        }
        icon={<PictureAsPdfOutlined />}
        variant="outlined"
      >
        {locateHint}
      </Alert>

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            md: "minmax(0, 1.45fr) minmax(320px, 0.9fr)",
          },
          gap: 1.5,
        }}
      >
        <Paper
          variant="outlined"
          sx={{
            minHeight: { xs: 420, md: 0 },
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            p: 1,
          }}
        >
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ px: 0.5, pb: 0.75 }}
          >
            {document.original_filename ||
              document.source_file ||
              document.document_id}
          </Typography>
          <Box sx={{ flex: 1, minHeight: 0 }}>
            <PdfDocumentViewer
              fileUrl={pdfUrl}
              selection={
                selection?.location?.hasLocation
                  ? {
                      key: selection.key,
                      pageNumber: selection.location.pageNumber,
                      boundingBox: selection.location.boundingBox,
                      variant: isInferredLocation(selection.result)
                        ? "inferred"
                        : "text",
                    }
                  : selection
                    ? {
                        key: selection.key,
                        pageNumber: null,
                        boundingBox: null,
                      }
                    : null
              }
            />
          </Box>
        </Paper>

        <Paper
          variant="outlined"
          sx={{
            minHeight: { xs: 360, md: 0 },
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            p: 1.25,
          }}
        >
          <Typography variant="subtitle2" fontWeight={750} sx={{ mb: 1 }}>
            Steel sections in this drawing
          </Typography>
          <Box sx={{ flex: 1, minHeight: 0 }}>
            <SectionResultsList
              results={results}
              selectedKey={selection?.key ?? null}
              onSelect={(next) => {
                const location =
                  next.location || getPredictionLocation(next.result);
                setSelection({
                  key: next.key,
                  result: next.result,
                  location,
                });
                setCorrectLabel(getSection(next.result) || "");
                setReviewMessage("");
              }}
            />
          </Box>
          {selection?.result ? (
            <Stack
              spacing={1}
              sx={{ pt: 1.25, borderTop: 1, borderColor: "divider" }}
            >
              <Typography variant="caption" color="text.secondary">
                {annotationState || selection.result.review_status || "review"}
                {annotationType ? ` · ${annotationType}` : ""}
              </Typography>
              {topK.length > 0 ? (
                <Typography variant="caption">
                  Top-K:{" "}
                  {topK
                    .slice(0, 5)
                    .map((item) => formatCandidateLabel(item))
                    .filter(Boolean)
                    .join(", ")}
                </Typography>
              ) : null}
              <TextField
                size="small"
                label="Correct label"
                value={correctLabel}
                onChange={(event) => setCorrectLabel(event.target.value)}
              />
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                <Button
                  size="small"
                  variant="contained"
                  disabled={busy}
                  onClick={() => submitReview("approve")}
                >
                  Accept
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={busy || !correctLabel}
                  onClick={() => submitReview("correct")}
                >
                  Correct
                </Button>
                <Button
                  size="small"
                  color="warning"
                  disabled={busy}
                  onClick={() => submitReview("mark_unreadable")}
                >
                  Mark Unreadable
                </Button>
                <Button
                  size="small"
                  color="inherit"
                  disabled={busy}
                  onClick={() => submitReview("mark_unsupported")}
                >
                  Mark Unsupported
                </Button>
              </Stack>
              {reviewMessage ? (
                <Typography variant="caption" color="text.secondary">
                  {reviewMessage}
                </Typography>
              ) : null}
            </Stack>
          ) : null}
        </Paper>
      </Box>
    </Stack>
  );
}
