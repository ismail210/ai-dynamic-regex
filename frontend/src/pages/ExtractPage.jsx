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

// User-facing message only for statuses worth actively telling the user
// about -- DISABLED / NO_CONTEXT_PAGES / SUCCESS render nothing extra when
// there is genuinely nothing to show.
const STATUS_MESSAGES = {
  MODEL_UNAVAILABLE: "Project notes analysis unavailable (the configured model could not be reached).",
  MODEL_ERROR: "Project notes analysis failed (the model returned an unusable response).",
  VISION_REQUIRED: "This document's notes/legend pages appear to be scanned images -- text analysis was not possible yet.",
  NO_RELEVANT_INFORMATION: "No notable project-specific notes found beyond standard boilerplate.",
};

// Rule types are grouped into these headed sections of the panel.
const RULE_SECTIONS = [
  { title: "Materials / finishes", types: ["ATTRIBUTE_DEFAULT", "ORIENTATION_RULE"] },
  { title: "Connection / member rules", types: ["CONNECTION_DEFAULT", "INHERITANCE_RULE"] },
  { title: "Scope & document precedence", types: ["SCOPE_RULE", "DOCUMENT_PRECEDENCE"] },
];

// A short, plain badge for what Estima3D is allowed to do with a rule.
const POLICY_BADGE = {
  AUTO_ELIGIBLE: { label: "auto-applies", color: "success" },
  CORROBORATION_REQUIRED: { label: "needs geometry check", color: "warning" },
  PARSER_ASSIST: { label: "parsing aid", color: "info" },
  ATTRIBUTE_ONLY: { label: "attribute only", color: "default" },
  INFORMATION_ONLY: { label: "informational", color: "default" },
  NEVER_AUTO: { label: "review only", color: "default" },
};

function RuleItem({ rule }) {
  const badge = POLICY_BADGE[rule.application_policy];
  return (
    <Stack direction="row" spacing={1} alignItems="flex-start">
      <Typography component="span" variant="body2" sx={{ flex: 1 }}>
        {rule.statement}{" "}
        {rule.source_quote && (
          <Tooltip title={`Page ${rule.source_page ?? "?"}: "${rule.source_quote}"`} arrow>
            <Typography component="span" variant="caption" color="text.secondary" sx={{ cursor: "help" }}>
              (page {rule.source_page ?? "?"})
            </Typography>
          </Tooltip>
        )}
      </Typography>
      {badge && (
        <Chip
          size="small"
          variant="outlined"
          color={badge.color}
          label={badge.label}
          sx={{ mt: 0.1 }}
        />
      )}
    </Stack>
  );
}

function DerivedInsightItem({ insight }) {
  const basedOn = (insight.evidence_refs || []).join(" · ");
  return (
    <Alert severity="info" variant="outlined" icon={false} sx={{ "& .MuiAlert-message": { width: "100%" } }}>
      <Stack spacing={0.5}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" color="info" label="Project inference" />
          <Chip size="small" color="warning" variant="outlined" label="Not stated directly" />
          {insight.confidence != null && (
            <Typography variant="caption" color="text.secondary">
              confidence {Math.round((insight.confidence ?? 0) * 100)}%
            </Typography>
          )}
        </Stack>
        <Typography variant="body2">{insight.statement}</Typography>
        {insight.impact && (
          <Typography variant="caption" color="text.secondary">Impact: {insight.impact}</Typography>
        )}
        {basedOn && (
          <Tooltip title={insight.reasoning_summary || ""} arrow>
            <Typography variant="caption" color="text.secondary" sx={{ cursor: "help" }}>
              Derived from: {basedOn}
            </Typography>
          </Tooltip>
        )}
      </Stack>
    </Alert>
  );
}

function PanelSection({ title, children }) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

/**
 * Read-only display of the Project Drawing-Language profile
 * (services/engineering/legend_profile*.py + project_rules.py). Nothing here
 * changes a predicted section, candidate or takeoff quantity in this
 * checkpoint -- the `auto-applies` badge marks a LABEL_SUBSTITUTION rule that
 * a separate gated resolver may act on.
 *
 * Derived insights carry a "Not stated directly" chip so a reader never
 * mistakes a deduction for engineer-authored text.
 */
function LegendProfilePanel({ profile }) {
  if (!profile) return null;
  const summary = profile.executive_summary || "";
  const abbreviations = profile.abbreviation_rules || [];
  const rules = profile.project_rules || [];
  const drawingLanguage = profile.drawing_language || [];
  const insights = profile.derived_insights || [];
  const warnings = profile.warnings_and_conflicts || [];
  const attentionItems = profile.estimator_attention_items || [];

  const hasContent =
    summary ||
    abbreviations.length > 0 ||
    rules.length > 0 ||
    drawingLanguage.length > 0 ||
    insights.length > 0 ||
    warnings.length > 0 ||
    attentionItems.length > 0;

  const statusMessage = STATUS_MESSAGES[profile.status];
  if (!hasContent && !statusMessage) return null;

  const rulesByType = rules.reduce((acc, rule) => {
    (acc[rule.type] = acc[rule.type] || []).push(rule);
    return acc;
  }, {});

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="subtitle2" fontWeight={700} mb={1}>
        Important Project Notes
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
        The project's drawing language, compiled from this document's
        legend / general-notes / specification pages. Informational only --
        it does not change any predicted section in this build.
      </Typography>

      {!hasContent && statusMessage && (
        <Alert severity={profile.status === "MODEL_ERROR" ? "error" : "info"} variant="outlined">
          {statusMessage}
        </Alert>
      )}

      {summary && (
        <PanelSection title="Overview">
          <Typography variant="body2">{summary}</Typography>
        </PanelSection>
      )}

      {abbreviations.length > 0 && (
        <PanelSection title="Project-specific sections">
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
        </PanelSection>
      )}

      {drawingLanguage.length > 0 && (
        <PanelSection title="Drawing language">
          <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
            {drawingLanguage.map((line, index) => (
              <Typography key={index} component="li" variant="body2">
                {line}
              </Typography>
            ))}
          </Stack>
        </PanelSection>
      )}

      {RULE_SECTIONS.map(({ title, types }) => {
        const sectionRules = types.flatMap((type) => rulesByType[type] || []);
        if (sectionRules.length === 0) return null;
        return (
          <PanelSection key={title} title={title}>
            <Stack spacing={0.5}>
              {sectionRules.map((rule, index) => (
                <RuleItem key={index} rule={rule} />
              ))}
            </Stack>
          </PanelSection>
        );
      })}

      {attentionItems.length > 0 && (
        <PanelSection title="Estimator attention">
          <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
            {attentionItems.map((item, index) => (
              <Typography key={index} component="li" variant="body2">
                {item}
              </Typography>
            ))}
          </Stack>
        </PanelSection>
      )}

      {insights.length > 0 && (
        <PanelSection title="Derived project insights">
          <Stack spacing={0.75}>
            {insights.map((insight, index) => (
              <DerivedInsightItem key={index} insight={insight} />
            ))}
          </Stack>
        </PanelSection>
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
