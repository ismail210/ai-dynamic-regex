import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Box, Paper, Stack, Typography } from "@mui/material";
import { PictureAsPdfOutlined, TableRowsOutlined } from "@mui/icons-material";
import { documentPdfUrl } from "../api/client";
import PdfDocumentViewer from "../components/pdf/PdfDocumentViewer";
import SectionResultsList from "../components/pdf/SectionResultsList";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import { TipButton } from "../components/ui/ActionButtons";
import { useAnalysis } from "../context/AnalysisContext";
import { getPredictionLocation, getSection, isInferredLocation } from "../lib/predictionContract";

export default function DrawingReviewPage() {
  const { document, data, restoreNotice } = useAnalysis();
  const [selection, setSelection] = useState(null);

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

  return (
    <Stack spacing={1.75} sx={{ height: { md: "calc(100vh - 140px)" }, minHeight: 520 }}>
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
        severity={selection && !selection.location?.hasLocation ? "warning" : "info"}
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
          gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1.45fr) minmax(320px, 0.9fr)" },
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
          <Typography variant="caption" color="text.secondary" sx={{ px: 0.5, pb: 0.75 }}>
            {document.original_filename || document.source_file || document.document_id}
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
                    ? { key: selection.key, pageNumber: null, boundingBox: null }
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
                const location = next.location || getPredictionLocation(next.result);
                setSelection({
                  key: next.key,
                  result: next.result,
                  location,
                });
              }}
            />
          </Box>
        </Paper>
      </Box>
    </Stack>
  );
}
