import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { HubOutlined } from "@mui/icons-material";
import { analyzeDocument } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import useElapsedSeconds from "../hooks/useElapsedSeconds";
import { TipButton } from "./ui/ActionButtons";

/**
 * The "Analyze Drawing" launcher — file summary, optional ground-truth Excel,
 * the analyze action, and inline progress. Lifted from the old Analyze page so
 * the merged Analysis & Results page runs analysis in place instead of on a
 * separate route. On success it populates AnalysisContext `data`; the parent
 * page swaps itself to the results view.
 */
export default function AnalyzeLauncher({ onDone }) {
  const { document, extraction, data, excelFile, setExcelFile, setData } =
    useAnalysis();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const elapsed = useElapsedSeconds(loading);

  async function run() {
    if (!document?.document_id || !extraction || loading) return;
    setLoading(true);
    setError("");
    try {
      const result = await analyzeDocument(
        document.document_id,
        excelFile,
        undefined,
        true,
      );
      setData(result);
      onDone?.(result);
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

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Box>
          <Typography fontWeight={700}>{document?.source_file}</Typography>
          <Typography variant="body2" color="text.secondary">
            {extraction?.tokens?.length || 0} engineering objects ready — geometry,
            structural graph, exact-section prediction, OCR correction, and
            validation run next.
          </Typography>
        </Box>
        <Button variant="outlined" component="label" sx={{ alignSelf: "flex-start" }}>
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
          startIcon={<HubOutlined />}
          onClick={run}
          loading={loading}
          sx={{ alignSelf: "flex-start" }}
        >
          Analyze Drawing
        </TipButton>
        {loading && (
          <Box>
            <LinearProgress />
            <Typography variant="caption" color="text.secondary">
              Extracting geometry, constructing the graph, fusing evidence,
              correcting OCR, and validating predictions… {elapsed}s elapsed
            </Typography>
          </Box>
        )}
        {error && <Alert severity="error">{error}</Alert>}
        {data && !loading && (
          <Alert severity="success">
            Analysis completed for {data.results?.length || 0} structural objects.
            {data.cached ? " Cached features were reused." : ""}
          </Alert>
        )}
      </Stack>
    </Paper>
  );
}
