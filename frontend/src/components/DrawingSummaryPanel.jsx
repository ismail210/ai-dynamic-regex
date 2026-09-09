import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";
import { isSteelTakeoffToken } from "../lib/predictionContract";

// User-facing message only for statuses worth actively telling the user
// about -- DISABLED / NO_CONTEXT_PAGES / SUCCESS render nothing extra when
// there is genuinely nothing to show.
const STATUS_MESSAGES = {
  MODEL_UNAVAILABLE:
    "Project notes analysis unavailable (the configured model could not be reached).",
  MODEL_ERROR:
    "Project notes analysis failed (the model returned an unusable response).",
  VISION_REQUIRED:
    "This document's notes/legend pages appear to be scanned images -- text analysis was not possible yet.",
  NO_RELEVANT_INFORMATION:
    "No notable project-specific notes found beyond standard boilerplate.",
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

const PAGE_ROLE_LABELS = {
  LEGEND: "legend",
  GENERAL_NOTES: "general-note",
  STRUCTURAL_NOTES: "structural-note",
  ABBREVIATIONS: "abbreviation",
  SPECIFICATIONS: "specification",
  VISION_REQUIRED: "scanned notes",
};

const FAMILY_LABELS = {
  W: "W — wide flange",
  HSS: "HSS — hollow structural",
  PIPE: "Pipe",
  C: "C — channel",
  MC: "MC — channel",
  L: "L — angle",
  "2L": "2L — double angle",
  WT: "WT — tee",
  MT: "MT — tee",
  ST: "ST — tee",
  S: "S — beam",
  M: "M — beam",
  HP: "HP — bearing pile",
  PL: "PL — plate",
};

function EvidenceChip({ label, page, quote, color = "default", variant = "outlined" }) {
  const evidence = quote ? `Page ${page ?? "?"}: "${quote}"` : `Page ${page ?? "?"}`;
  return (
    <Chip size="small" variant={variant} color={color} label={label} title={evidence} />
  );
}

function RuleItem({ rule }) {
  const badge = POLICY_BADGE[rule.application_policy];
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
      <Typography component="span" variant="body2" sx={{ flex: 1 }}>
        {rule.statement}{" "}
        {rule.source_quote && (
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ cursor: "help" }}
            title={`Page ${rule.source_page ?? "?"}: "${rule.source_quote}"`}
          >
            (page {rule.source_page ?? "?"})
          </Typography>
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
    <Alert
      severity="info"
      variant="outlined"
      icon={false}
      sx={{ "& .MuiAlert-message": { width: "100%" } }}
    >
      <Stack spacing={0.5}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
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
          <Typography variant="caption" color="text.secondary">
            Impact: {insight.impact}
          </Typography>
        )}
        {basedOn && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ cursor: "help" }}
            title={insight.reasoning_summary || ""}
          >
            Derived from: {basedOn}
          </Typography>
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

// Steel families present in the drawing, derived (display-only) from the
// extracted steel tokens and the abbreviation rules' resolved families. Never
// a prediction input.
function detectFamilies(extraction, abbreviations) {
  const families = new Set();
  for (const rule of abbreviations) {
    if (rule.rhs_family) families.add(String(rule.rhs_family).toUpperCase());
    if (rule.lhs_family) families.add(String(rule.lhs_family).toUpperCase());
  }
  for (const token of extraction?.tokens || []) {
    if (!isSteelTakeoffToken(token)) continue;
    const text = String(token.text || "").toUpperCase().replace(/\s/g, "");
    const match = text.match(/^(2L|WT|MT|ST|MC|HP|HSS|PIPE|PL|W|S|M|C|L)\d|^(PL|BP)\b/);
    if (match) families.add(match[1] || match[2]);
  }
  return [...families].filter((f) => FAMILY_LABELS[f]);
}

/**
 * Read-only display of the Project Drawing-Language profile
 * (services/engineering/legend_profile*.py + project_rules.py) — "what Estima3D
 * understood about this drawing set". Nothing here changes a predicted section,
 * candidate or takeoff quantity; the `auto-applies` badge marks a
 * LABEL_SUBSTITUTION rule that a separate gated resolver may act on.
 */
export default function DrawingSummaryPanel({ profile, extraction, data }) {
  if (!profile) return null;
  const summary = profile.executive_summary || "";
  const abbreviations = profile.abbreviation_rules || [];
  const rules = profile.project_rules || [];
  const drawingLanguage = profile.drawing_language || [];
  const insights = profile.derived_insights || [];
  const warnings = profile.warnings_and_conflicts || [];
  const attentionItems = profile.estimator_attention_items || [];
  const contextPages = profile.context_pages || {};

  const families = detectFamilies(extraction, abbreviations);
  const objectCount =
    extraction?.object_counts?.engineering_objects ??
    data?.token_count ??
    (extraction?.tokens || []).length;

  const roleCounts = Object.values(contextPages).reduce((acc, role) => {
    const label = PAGE_ROLE_LABELS[role];
    if (label) acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});
  const structuralBits = [
    ...Object.entries(roleCounts).map(
      ([label, n]) => `${n} ${label} page${n === 1 ? "" : "s"}`,
    ),
    objectCount ? `${objectCount} engineering objects extracted` : null,
  ].filter(Boolean);

  const hasContent =
    summary ||
    abbreviations.length > 0 ||
    rules.length > 0 ||
    drawingLanguage.length > 0 ||
    insights.length > 0 ||
    warnings.length > 0 ||
    attentionItems.length > 0 ||
    families.length > 0 ||
    structuralBits.length > 0;

  const statusMessage = STATUS_MESSAGES[profile.status];
  if (!hasContent && !statusMessage) return null;

  const rulesByType = rules.reduce((acc, rule) => {
    (acc[rule.type] = acc[rule.type] || []).push(rule);
    return acc;
  }, {});
  const lowConfidenceInsights = insights.filter((i) => (i.confidence ?? 1) < 0.75);

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
        <Alert
          severity={profile.status === "MODEL_ERROR" ? "error" : "info"}
          variant="outlined"
        >
          {statusMessage}
        </Alert>
      )}

      {summary ? (
        <PanelSection title="Drawing overview">
          <Typography variant="body2">{summary}</Typography>
        </PanelSection>
      ) : hasContent && statusMessage ? (
        <PanelSection title="Drawing overview">
          <Typography variant="body2" color="text.secondary">
            {statusMessage}
          </Typography>
        </PanelSection>
      ) : null}

      {structuralBits.length > 0 && (
        <PanelSection title="Structural content">
          <Typography variant="body2" color="text.secondary">
            {structuralBits.join(" · ")}
          </Typography>
        </PanelSection>
      )}

      {families.length > 0 && (
        <PanelSection title="Steel families detected">
          <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap" }}>
            {families.map((family) => (
              <Chip key={family} size="small" label={FAMILY_LABELS[family]} />
            ))}
          </Stack>
        </PanelSection>
      )}

      {(drawingLanguage.length > 0 || abbreviations.length > 0) && (
        <PanelSection title="Drawing language / conventions">
          {abbreviations.length > 0 && (
            <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap", mb: drawingLanguage.length ? 1 : 0 }}>
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
          )}
          {drawingLanguage.length > 0 && (
            <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
              {drawingLanguage.map((line, index) => (
                <Typography key={index} component="li" variant="body2">
                  {line}
                </Typography>
              ))}
            </Stack>
          )}
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
        <PanelSection title="Important notes">
          <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
            {attentionItems.map((item, index) => (
              <Typography key={`att-${index}`} component="li" variant="body2">
                {item}
              </Typography>
            ))}
          </Stack>
        </PanelSection>
      )}

      {(warnings.length > 0 || lowConfidenceInsights.length > 0) && (
        <PanelSection title="Uncertainties">
          <Stack spacing={0.75}>
            {warnings.map((item, index) => (
              <Alert key={`w-${index}`} severity="warning" variant="outlined" sx={{ py: 0.25 }}>
                {item.summary}{" "}
                <Typography component="span" variant="caption" color="text.secondary">
                  (page {item.source_page ?? "?"})
                </Typography>
              </Alert>
            ))}
            {lowConfidenceInsights.map((insight, index) => (
              <DerivedInsightItem key={`i-${index}`} insight={insight} />
            ))}
          </Stack>
        </PanelSection>
      )}

      {insights.length > lowConfidenceInsights.length && (
        <PanelSection title="Derived project insights">
          <Stack spacing={0.75}>
            {insights
              .filter((i) => (i.confidence ?? 1) >= 0.75)
              .map((insight, index) => (
                <DerivedInsightItem key={index} insight={insight} />
              ))}
          </Stack>
        </PanelSection>
      )}
    </Paper>
  );
}
