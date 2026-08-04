import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Box,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { ArrowForwardRounded, ManageSearchOutlined } from "@mui/icons-material";
import { extractDocument } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";
import { TipButton } from "../components/ui/ActionButtons";


export default function ExtractPage() {
  const { document, extraction, setExtraction, setData } = useAnalysis();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runExtraction() {
    if (!document?.document_id) return;
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

  if (!document) {
    return (
      <EmptyState
        title="Upload a drawing first"
        subtitle="Extraction operates on a registered document and never starts during upload."
        action={
          <TipButton component={Link} to="/upload" variant="contained">
            Go to upload
          </TipButton>
        }
      />
    );
  }

  const counts = extraction?.object_counts || {};
  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Extract engineering objects"
        subtitle="OCR, layout, tables, dimensions, callouts, reading order, and structural labels. Notes and non-object text are filtered out."
        actions={
          <TipButton
            variant="contained"
            onClick={runExtraction}
            loading={loading}
            startIcon={<ManageSearchOutlined />}
          >
            {extraction ? "Re-extract" : "Extract"}
          </TipButton>
        }
      />

      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography fontWeight={700}>{document.source_file}</Typography>
        <Typography variant="body2" color="text.secondary">
          {document.document_id} · {document.page_count} pages
        </Typography>
        {loading && (
          <Box sx={{ mt: 2 }}>
            <LinearProgress />
            <Typography variant="caption" color="text.secondary">
              Reading OCR, layout, tables, dimensions, and structural callouts…
            </Typography>
          </Box>
        )}
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </Paper>

      {extraction && (
        <>
          <Paper variant="outlined" sx={{ p: 2.5 }}>
            <Stack direction="row" gap={1} mb={2} sx={{ flexWrap: "wrap" }}>
              <Chip label={`${counts.engineering_objects || 0} engineering objects`} />
              <Chip label={`${counts.discarded_text_candidates || 0} text candidates ignored`} />
              <Chip label={`${extraction.layout?.tables?.length || 0} tables`} />
              <Chip label={`${extraction.layout?.dimensions?.length || 0} dimensions`} />
              <Chip label={`${extraction.layout?.callouts?.length || 0} callouts`} />
              {extraction.cached && <Chip color="info" label="Cached extraction" />}
            </Stack>
            <Typography variant="subtitle2" mb={1}>Detected structural labels</Typography>
            <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap" }}>
              {(extraction.tokens || []).slice(0, 80).map((token) => (
                <Chip
                  key={token.token_id}
                  variant="outlined"
                  size="small"
                  label={`${token.text} · ${token.engineering_object_type}`}
                />
              ))}
            </Stack>
          </Paper>
          <Box>
            <TipButton
              component={Link}
              to="/analyze"
              variant="contained"
              endIcon={<ArrowForwardRounded />}
            >
              Continue to analysis
            </TipButton>
          </Box>
        </>
      )}
    </Stack>
  );
}
