import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import {
  ArrowForwardRounded,
  ManageSearchOutlined,
} from "@mui/icons-material";
import { extractDocument } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import useElapsedSeconds from "../hooks/useElapsedSeconds";
import FileUpload from "../components/FileUpload";
import ExtractionSummary from "../components/ExtractionSummary";
import PageHeader from "../components/ui/PageHeader";
import WorkflowProgress from "../components/ui/WorkflowProgress";
import { TipButton } from "../components/ui/ActionButtons";

/**
 * Merged Upload + Extract. Upload stores the PDF; extraction runs in place on
 * the same page; the ground-truth Excel can be attached here so it is ready
 * when Analysis runs. Continues to Drawing Summary.
 */
export default function UploadExtractPage() {
  const { document, extraction, excelFile, setExcelFile, setExtraction, setData } =
    useAnalysis();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const elapsed = useElapsedSeconds(loading);

  async function runExtraction() {
    if (!document?.document_id || loading) return;
    setLoading(true);
    setError("");
    setData(null);
    try {
      setExtraction(await extractDocument(document.document_id));
    } catch (err) {
      setError(
        err.friendlyMessage ||
          err.response?.data?.detail ||
          "Document extraction failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Upload & Extract"
        subtitle="Store the drawing, then read its pages — OCR, layout, tables, dimensions, callouts, and structural labels. Notes and non-object text are filtered out."
      />
      <WorkflowProgress step="upload" />

      {!document && <FileUpload />}

      {document && (
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          <Stack spacing={2}>
            <Box>
              <Typography fontWeight={700}>{document.source_file}</Typography>
              <Typography variant="body2" color="text.secondary">
                {document.document_id} · {document.page_count} pages
              </Typography>
            </Box>

            <Button
              variant="outlined"
              component="label"
              sx={{ alignSelf: "flex-start" }}
            >
              {excelFile ? excelFile.name : "Optional ground-truth Excel"}
              <input
                hidden
                type="file"
                accept=".xlsx,.xls,.xlsm"
                onChange={(event) => setExcelFile(event.target.files?.[0] || null)}
              />
            </Button>

            <TipButton
              variant="contained"
              onClick={runExtraction}
              loading={loading}
              startIcon={<ManageSearchOutlined />}
              sx={{ alignSelf: "flex-start" }}
            >
              {extraction ? "Re-extract" : "Extract drawing"}
            </TipButton>

            {loading && (
              <Box>
                <LinearProgress />
                <Typography variant="caption" color="text.secondary">
                  Reading OCR, layout, tables, dimensions, and structural callouts…{" "}
                  {elapsed}s elapsed
                </Typography>
              </Box>
            )}
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </Paper>
      )}

      {extraction && (
        <>
          <ExtractionSummary extraction={extraction} />
          <Box>
            <TipButton
              component={Link}
              to="/drawing-summary"
              variant="contained"
              endIcon={<ArrowForwardRounded />}
            >
              Continue to Drawing Summary
            </TipButton>
          </Box>
        </>
      )}
    </Stack>
  );
}
