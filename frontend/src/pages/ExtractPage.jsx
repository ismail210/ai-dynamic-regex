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

const CATEGORY_LABELS = {
  SECTION_NOTATION: "Section notation",
  MATERIAL: "Materials",
  CONNECTION: "Connections",
  FABRICATION: "Fabrication",
  INTERPRETATION: "Interpretation",
  RESPONSIBILITY: "Responsibility",
  SCOPE: "Estimator scope",
  OTHER: "Other",
};

// User-facing message only for statuses worth actively telling the user
// about -- DISABLED/NO_CONTEXT_PAGES/SUCCESS render nothing extra when
// there's genuinely nothing to show, matching "don't dump a blank panel
// with an error for a normal non-applicable case".
const STATUS_MESSAGES = {
  MODEL_UNAVAILABLE: "Project notes analysis unavailable (the configured model could not be reached).",
  MODEL_ERROR: "Project notes analysis failed (the model returned an unusable response).",
  VISION_REQUIRED: "This document's notes/legend pages appear to be scanned images -- text analysis was not possible yet.",
  NO_RELEVANT_INFORMATION: "No notable project-specific notes found beyond standard boilerplate.",
};

function SourceFactItem({ fact }) {
  return (
    <Stack direction="row" spacing={1} alignItems="flex-start">
      <Chip size="small" label={CATEGORY_LABELS[fact.category] || fact.category} sx={{ mt: 0.25 }} />
      <Typography variant="body2">
        {fact.statement}{" "}
        <Tooltip title={`Page ${fact.source_page ?? "?"}: "${fact.source_quote || ""}"`} arrow>
          <Typography component="span" variant="caption" color="text.secondary" sx={{ cursor: "help" }}>
            (page {fact.source_page ?? "?"})
          </Typography>
        </Tooltip>
      </Typography>
    </Stack>
  );
}

function DerivedInsightItem({ insight }) {
  const basedOn = (insight.evidence_refs || []).join(" · ");
  return (
    <Alert
      severity="info"
      variant="outlined"
      icon={false}
      sx={{ "& .MuiAlert-message": { width: "100%" } }}
    >
      <Stack spacing={0.5}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" color="info" label="Project inference" />
          {insight.human_review_recommended && (
            <Chip size="small" color="warning" variant="outlined" label="Review recommended" />
          )}
          <Typography variant="caption" color="text.secondary">
            confidence {Math.round((insight.confidence ?? 0) * 100)}%
          </Typography>
        </Stack>
        <Typography variant="body2">{insight.inference}</Typography>
        {insight.impact && (
          <Typography variant="caption" color="text.secondary">
            Impact: {insight.impact}
          </Typography>
        )}
        {basedOn && (
          <Tooltip title={insight.reasoning_summary || ""} arrow>
            <Typography variant="caption" color="text.secondary" sx={{ cursor: "help" }}>
              Based on: {basedOn}
            </Typography>
          </Tooltip>
        )}
      </Stack>
    </Alert>
  );
}

/**
 * Informational only: the project context profile
 * (services/engineering/legend_profile*.py) never touches predicted
 * sections, candidates, or takeoff quantities -- this panel is read-only
 * display of what Estima3D found on the non-drawing context pages.
 *
 * SOURCE FACTS are directly quoted from the document (evidence-grounded).
 * DERIVED INSIGHTS are the model's reasoning ACROSS multiple facts -- shown
 * with distinct styling (blue "Project inference" chip) so a reader never
 * mistakes a deduction for something the document states outright.
 */
function LegendProfilePanel({ profile }) {
  if (!profile) return null;
  const summary = profile.executive_summary || "";
  const facts = profile.source_facts || [];
  const insights = profile.derived_insights || [];
  const abbreviations = profile.abbreviation_rules || [];
  const warnings = profile.warnings_and_conflicts || [];
  const attentionItems = profile.estimator_attention_items || [];
  const hasContent =
    summary ||
    facts.length > 0 ||
    insights.length > 0 ||
    abbreviations.length > 0 ||
    warnings.length > 0 ||
    attentionItems.length > 0;

  const statusMessage = STATUS_MESSAGES[profile.status];
  if (!hasContent && !statusMessage) return null;

  const factsByCategory = facts.reduce((acc, fact) => {
    const key = fact.category || "OTHER";
    (acc[key] = acc[key] || []).push(fact);
    return acc;
  }, {});

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="subtitle2" fontWeight={700} mb={1}>
        Important Project Notes
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
        Extracted from this document's legend/general-notes/specification pages.
        Informational only -- does not change any predicted section.
      </Typography>

      {!hasContent && statusMessage && (
        <Alert severity={profile.status === "MODEL_ERROR" ? "error" : "info"} variant="outlined">
          {statusMessage}
        </Alert>
      )}

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

      {Object.keys(factsByCategory).length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>
            Explicit project facts
          </Typography>
          <Stack spacing={0.5}>
            {Object.entries(factsByCategory).map(([category, items]) =>
              items.map((fact, index) => (
                <SourceFactItem key={`${category}-${index}`} fact={fact} />
              )),
            )}
          </Stack>
        </Box>
      )}

      {insights.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>
            Potential interpretation (derived, not stated directly)
          </Typography>
          <Stack spacing={0.75}>
            {insights.map((insight, index) => (
              <DerivedInsightItem key={index} insight={insight} />
            ))}
          </Stack>
        </Box>
      )}

      {attentionItems.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>
            Estimator attention
          </Typography>
          <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
            {attentionItems.map((item, index) => (
              <Typography key={index} component="li" variant="body2">
                {item}
              </Typography>
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
