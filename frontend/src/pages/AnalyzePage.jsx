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
import { ArrowForwardRounded, HubOutlined } from "@mui/icons-material";
import { analyzeDocument } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";
import { TipButton } from "../components/ui/ActionButtons";


export default function AnalyzePage() {
  const { document, extraction, data, setData } = useAnalysis();
  const [excel, setExcel] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    if (!document?.document_id || !extraction) return;
    setLoading(true);
    setError("");
    try {
      setData(await analyzeDocument(document.document_id, excel));
    } catch (err) {
      setError(
        err.friendlyMessage ||
          err.response?.data?.detail ||
          "Multimodal analysis failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (!document || !extraction) {
    return (
      <EmptyState
        title="Extraction is required"
        subtitle="Analyze becomes available only after engineering objects have been extracted."
        action={
          <TipButton component={Link} to={document ? "/extract" : "/upload"} variant="contained">
            {document ? "Go to extraction" : "Go to upload"}
          </TipButton>
        }
      />
    );
  }

  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Run multimodal analysis"
        subtitle="Build geometry and structural graph features, predict exact sections, correct OCR, validate results, and generate explanations."
      />
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Stack spacing={2}>
          <Box>
            <Typography fontWeight={700}>{document.source_file}</Typography>
            <Typography variant="body2" color="text.secondary">
              {extraction.tokens?.length || 0} engineering objects ready for analysis
            </Typography>
          </Box>
          <Button variant="outlined" component="label" sx={{ alignSelf: "flex-start" }}>
            {excel ? excel.name : "Optional ground-truth Excel"}
            <input
              hidden
              type="file"
              accept=".xlsx,.xls,.xlsm"
              onChange={(event) => setExcel(event.target.files?.[0] || null)}
            />
          </Button>
          <TipButton
            variant="contained"
            startIcon={<HubOutlined />}
            onClick={run}
            loading={loading}
            sx={{ alignSelf: "flex-start" }}
          >
            Analyze
          </TipButton>
          {loading && (
            <Box>
              <LinearProgress />
              <Typography variant="caption" color="text.secondary">
                Extracting geometry, constructing the graph, fusing evidence, correcting OCR, and validating predictions…
              </Typography>
            </Box>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          {data && (
            <Alert
              severity="success"
              action={
                <TipButton
                  component={Link}
                  to="/results"
                  variant="contained"
                  endIcon={<ArrowForwardRounded />}
                >
                  View results
                </TipButton>
              }
            >
              Analysis completed for {data.results?.length || 0} structural objects.
              {data.cached ? " Cached features were reused." : ""}
            </Alert>
          )}
        </Stack>
      </Paper>
    </Stack>
  );
}
