import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Box,
  Chip,
  FormControlLabel,
  LinearProgress,
  Paper,
  Stack,
  Switch,
  Tooltip,
  Typography,
} from "@mui/material";
import { ArrowForwardRounded, ManageSearchOutlined } from "@mui/icons-material";
import { extractDocument } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import useElapsedSeconds from "../hooks/useElapsedSeconds";
import PageHeader from "../components/ui/PageHeader";
import EmptyState from "../components/ui/EmptyState";
import { TipButton } from "../components/ui/ActionButtons";
import { isSteelTakeoffToken } from "../lib/predictionContract";


const DISCARD_LABELS = {
  layout_dims: "layout dimensions",
  title_block: "title block",
  weak_anonymous: "weak anonymous dims",
  standalone_refs: "standalone grades/refs",
  duplicates: "duplicates",
};


function EvidenceChip({ label, page, quote, color = "default", variant = "outlined" }) {
  const evidence = quote
    ? `Page ${page ?? "?"}: "${quote}"`
    : `Page ${page ?? "?"}`;
  return (
    <Tooltip title={evidence} placement="top" arrow>
      <Chip size="small" variant={variant} color={color} label={label} />
    </Tooltip>
  );
}

/**
 * Informational only: the legend/general-notes project-summary profile
 * (services/engineering/legend_profile*.py) never touches predicted
 * sections, candidates, or takeoff quantities -- this panel is read-only
 * display of what Estima3D found on the non-drawing context pages.
 */
function LegendProfilePanel({ profile }) {
  if (!profile) return null;
  const summary = profile.project_summary || "";
  const conventions = profile.important_conventions || [];
  const abbreviations = profile.abbreviation_rules || [];
  const warnings = profile.warnings_or_conflicts || [];
  const hasContent =
    summary || conventions.length > 0 || abbreviations.length > 0 || warnings.length > 0;
  if (!hasContent) return null;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="subtitle2" fontWeight={700} mb={1}>
        Important Project Notes
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
        Extracted from this document's legend/general-notes/specification pages.
        Informational only -- does not change any predicted section.
      </Typography>

      {summary && (
        <Typography variant="body2" sx={{ mb: 1.5 }}>
          {summary}
        </Typography>
      )}

      {abbreviations.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>
            Project-specific shorthand
          </Typography>
          <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap" }}>
            {abbreviations.map((rule, index) => (
              <EvidenceChip
                key={`${rule.lhs}-${index}`}
                label={`${rule.lhs} → ${rule.rhs}`}
                page={rule.source_page}
                quote={rule.source_quote}
                color="info"
              />
            ))}
          </Stack>
        </Box>
      )}

      {conventions.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>
            Conventions
          </Typography>
          <Stack spacing={0.5}>
            {conventions.map((item, index) => (
              <Stack key={index} direction="row" spacing={1} alignItems="flex-start">
                <Chip size="small" label={item.category} sx={{ mt: 0.25 }} />
                <Typography variant="body2">
                  {item.summary}{" "}
                  <Tooltip
                    title={`Page ${item.source_page ?? "?"}: "${item.source_quote || ""}"`}
                    arrow
                  >
                    <Typography
                      component="span"
                      variant="caption"
                      color="text.secondary"
                      sx={{ cursor: "help" }}
                    >
                      (page {item.source_page ?? "?"})
                    </Typography>
                  </Tooltip>
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Box>
      )}

      {warnings.length > 0 && (
        <Stack spacing={0.75}>
          {warnings.map((item, index) => (
            <Alert key={index} severity="warning" variant="outlined" sx={{ py: 0.25 }}>
              {item.summary}{" "}
              <Typography component="span" variant="caption" color="text.secondary">
                (page {item.source_page ?? "?"})
              </Typography>
            </Alert>
          ))}
        </Stack>
      )}
    </Paper>
  );
}

export default function ExtractPage() {
  const { document, extraction, setExtraction, setData } = useAnalysis();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [steelOnly, setSteelOnly] = useState(true);
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

  const visibleTokens = useMemo(() => {
    const tokens = extraction?.tokens || [];
    if (!steelOnly) return tokens;
    return tokens.filter(isSteelTakeoffToken);
  }, [extraction, steelOnly]);

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
  const discardBreakdown = counts.discard_breakdown || {};
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
              Reading OCR, layout, tables, dimensions, and structural callouts…{" "}
              {elapsed}s elapsed
            </Typography>
          </Box>
        )}
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </Paper>

      {extraction && (
        <>
          <LegendProfilePanel profile={extraction.legend_profile} />
          <Paper variant="outlined" sx={{ p: 2.5 }}>
            <Stack direction="row" gap={1} mb={2} sx={{ flexWrap: "wrap" }}>
              <Chip label={`${counts.engineering_objects || 0} engineering objects`} />
              <Chip label={`${counts.discarded_text_candidates || 0} text candidates ignored`} />
              <Chip label={`${extraction.layout?.tables?.length || 0} tables`} />
              <Chip label={`${extraction.layout?.dimensions?.length || 0} dimensions`} />
              <Chip label={`${extraction.layout?.callouts?.length || 0} callouts`} />
              {extraction.cached && <Chip color="info" label="Cached extraction" />}
            </Stack>
            {Object.keys(discardBreakdown).length > 0 && (
              <Stack direction="row" gap={0.75} mb={2} sx={{ flexWrap: "wrap" }}>
                {Object.entries(discardBreakdown).map(([key, value]) => (
                  <Chip
                    key={key}
                    size="small"
                    variant="outlined"
                    color="default"
                    label={`${value} ${DISCARD_LABELS[key] || key}`}
                  />
                ))}
              </Stack>
            )}
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="subtitle2">
                Detected structural labels
                {steelOnly ? ` (${visibleTokens.length} steel-focused)` : ""}
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={steelOnly}
                    onChange={(event) => setSteelOnly(event.target.checked)}
                  />
                }
                label="Steel objects only"
              />
            </Stack>
            <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap" }}>
              {visibleTokens.slice(0, 80).map((token) => (
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
