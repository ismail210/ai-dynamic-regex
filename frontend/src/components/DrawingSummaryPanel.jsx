import { Alert, Box, Chip, Divider, Paper, Stack, Typography } from "@mui/material";

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

// Rule types grouped into headed sections of the (secondary) project-rule list.
const RULE_SECTIONS = [
  { title: "Materials / finishes", types: ["ATTRIBUTE_DEFAULT", "ORIENTATION_RULE"] },
  { title: "Connection / member rules", types: ["CONNECTION_DEFAULT", "INHERITANCE_RULE"] },
  { title: "Scope & document precedence", types: ["SCOPE_RULE", "DOCUMENT_PRECEDENCE"] },
];

const POLICY_BADGE = {
  AUTO_ELIGIBLE: { label: "auto-applies", color: "success" },
  CORROBORATION_REQUIRED: { label: "needs geometry check", color: "warning" },
  PARSER_ASSIST: { label: "parsing aid", color: "info" },
  ATTRIBUTE_ONLY: { label: "attribute only", color: "default" },
  INFORMATION_ONLY: { label: "informational", color: "default" },
  NEVER_AUTO: { label: "review only", color: "default" },
};

function pagesLabel(pages) {
  if (!pages || pages.length === 0) return "";
  const shown = pages.slice(0, 8).join(", ");
  return pages.length > 8 ? `pp. ${shown}, +${pages.length - 8}` : `p. ${shown}`;
}

function Section({ title, source, children }) {
  return (
    <Box sx={{ mb: 1.75 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
        <Typography variant="caption" fontWeight={700} display="block">
          {title}
        </Typography>
        {source && (
          <Typography variant="caption" color="text.secondary">
            {source}
          </Typography>
        )}
      </Stack>
      <Box sx={{ mt: 0.5 }}>{children}</Box>
    </Box>
  );
}

function Para({ children, muted }) {
  return (
    <Typography variant="body2" color={muted ? "text.secondary" : "text.primary"}>
      {children}
    </Typography>
  );
}

function Bullets({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
      {items.map((line, i) => (
        <Typography key={i} component="li" variant="body2">
          {line}
        </Typography>
      ))}
    </Stack>
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
        <Chip size="small" variant="outlined" color={badge.color} label={badge.label} sx={{ mt: 0.1 }} />
      )}
    </Stack>
  );
}

/**
 * "What Estima3D understood about this drawing set" -- renders the
 * deterministic Drawing Intelligence Profile
 * (services/engineering/drawing_intelligence.py), optionally LLM-polished.
 * Nothing here changes a predicted section, candidate or takeoff quantity.
 */
export default function DrawingSummaryPanel({ profile }) {
  if (!profile) return null;

  const di = profile.drawing_intelligence || null;
  const narrative = di?.narrative || null;
  const rules = profile.project_rules || [];
  const rulesByType = rules.reduce((acc, rule) => {
    (acc[rule.type] = acc[rule.type] || []).push(rule);
    return acc;
  }, {});
  const insights = (profile.derived_insights || []).filter((i) => (i.confidence ?? 1) >= 0.75);
  const statusMessage = STATUS_MESSAGES[profile.status];

  const families = di?.steel_system?.families || [];
  const typicalActive = (di?.typical_conditions || []).filter((i) => i.detail?.present);
  const schedules = di?.schedule_insights || [];
  const scopeActive = (di?.scope_signals || []).filter((i) => i.detail?.present);
  const notes = di?.structural_notes || [];
  const uncertainties = di?.uncertainties || [];
  const method = di?.method;

  const hasNarrative = Boolean(narrative);
  const hasRules = rules.length > 0 || (profile.abbreviation_rules || []).length > 0;

  if (!hasNarrative && !hasRules && !statusMessage) return null;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", mb: 0.5 }}>
        <Typography variant="subtitle2" fontWeight={700}>
          What Estima3D read from this drawing set
        </Typography>
        {method === "llm_enhanced" && (
          <Chip size="small" variant="outlined" label="summary polished by model" />
        )}
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" mb={1.75}>
        Compiled from the extracted pages, notes, schedules and section labels.
        Informational only — it does not change any predicted section or takeoff
        quantity, and it never uses the ground-truth Excel.
      </Typography>

      {!hasNarrative && statusMessage && (
        <Alert
          severity={profile.status === "MODEL_ERROR" ? "error" : "info"}
          variant="outlined"
          sx={{ mb: hasRules ? 2 : 0 }}
        >
          {statusMessage}
        </Alert>
      )}

      {hasNarrative && (
        <>
          <Section title="Project overview">
            <Para>{narrative.project_overview}</Para>
          </Section>

          <Section title="Structural content">
            <Para muted>{narrative.structural_content}</Para>
          </Section>

          <Section title="Steel system">
            <Para>{narrative.steel_system}</Para>
            {families.length > 0 && (
              <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap", mt: 0.75 }}>
                {families.map((f) => (
                  <Chip
                    key={f.family}
                    size="small"
                    label={`${f.label} · ${f.explicit_occurrences}×`}
                    title={
                      f.representative?.length
                        ? `e.g. ${f.representative.join(", ")}`
                        : undefined
                    }
                  />
                ))}
              </Stack>
            )}
          </Section>

          <Section title="Drawing language & project rules">
            <Para muted={narrative.drawing_language.startsWith("No ")}>
              {narrative.drawing_language}
            </Para>
            {(profile.abbreviation_rules || []).length > 0 && (
              <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap", mt: 0.75 }}>
                {profile.abbreviation_rules.map((rule, i) => (
                  <Chip
                    key={`${rule.lhs}-${i}`}
                    size="small"
                    variant="outlined"
                    color="info"
                    label={`${rule.lhs} = ${rule.rhs}`}
                    title={
                      rule.source_quote
                        ? `Page ${rule.source_page ?? "?"}: "${rule.source_quote}"`
                        : `Page ${rule.source_page ?? "?"}`
                    }
                  />
                ))}
              </Stack>
            )}
            {RULE_SECTIONS.map(({ title, types }) => {
              const sectionRules = types.flatMap((t) => rulesByType[t] || []);
              if (sectionRules.length === 0) return null;
              return (
                <Box key={title} sx={{ mt: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    {title}
                  </Typography>
                  <Stack spacing={0.5} sx={{ mt: 0.25 }}>
                    {sectionRules.map((rule, i) => (
                      <RuleItem key={i} rule={rule} />
                    ))}
                  </Stack>
                </Box>
              );
            })}
          </Section>

          <Section title="Typical / repeated conditions">
            <Para muted={typicalActive.length === 0}>{narrative.typical_conditions}</Para>
            {typicalActive.length > 0 && (
              <Stack component="ul" sx={{ m: 0, pl: 2.5, mt: 0.5 }} spacing={0.25}>
                {typicalActive.map((i, idx) => (
                  <Typography
                    key={idx}
                    component="li"
                    variant="caption"
                    color="text.secondary"
                    title={i.source_text || undefined}
                  >
                    {i.value}
                  </Typography>
                ))}
              </Stack>
            )}
          </Section>

          {(schedules.length > 0 || !narrative.schedules.startsWith("No ")) && (
            <Section title="Schedules">
              <Stack spacing={0.5}>
                {schedules.map((s, i) => (
                  <Typography key={i} variant="body2">
                    {s.detail?.label} ({pagesLabel(s.source_pages)}) —{" "}
                    <Typography component="span" variant="caption" color="text.secondary">
                      {s.detail?.note}
                    </Typography>
                  </Typography>
                ))}
                {schedules.length === 0 && <Para muted>{narrative.schedules}</Para>}
              </Stack>
            </Section>
          )}

          <Section title="Scope / revision signals" source={scopeActive.length ? "" : ""}>
            <Para muted={scopeActive.length === 0}>{narrative.scope_revision}</Para>
            {scopeActive.length > 0 && (
              <Stack direction="row" gap={0.75} sx={{ flexWrap: "wrap", mt: 0.5 }}>
                {scopeActive.map((s, i) => (
                  <Chip
                    key={i}
                    size="small"
                    color="warning"
                    variant="outlined"
                    label={`${s.detail?.label} (${pagesLabel(s.source_pages)})`}
                    title={s.source_text || undefined}
                  />
                ))}
              </Stack>
            )}
          </Section>

          {narrative.important_notes?.length > 0 && (
            <Section title="Important structural notes">
              <Bullets items={narrative.important_notes} />
            </Section>
          )}

          {(uncertainties.length > 0 || insights.length > 0) && (
            <>
              <Divider sx={{ my: 1.5 }} />
              {uncertainties.length > 0 && (
                <Section title="Uncertainties">
                  <Stack spacing={0.5}>
                    {uncertainties.map((u, i) => (
                      <Alert
                        key={i}
                        severity="warning"
                        variant="outlined"
                        icon={false}
                        sx={{ py: 0.25, "& .MuiAlert-message": { width: "100%" } }}
                      >
                        <Typography variant="body2">{u.value}</Typography>
                      </Alert>
                    ))}
                  </Stack>
                </Section>
              )}
              {insights.length > 0 && (
                <Section title="Derived project insights">
                  <Stack spacing={0.5}>
                    {insights.map((insight, i) => (
                      <Alert
                        key={i}
                        severity="info"
                        variant="outlined"
                        icon={false}
                        sx={{ py: 0.25, "& .MuiAlert-message": { width: "100%" } }}
                      >
                        <Stack spacing={0.25}>
                          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                            <Chip size="small" color="info" label="Project inference" />
                            <Chip
                              size="small"
                              color="warning"
                              variant="outlined"
                              label="Not stated directly"
                            />
                          </Stack>
                          <Typography variant="body2">{insight.statement}</Typography>
                          {insight.impact && (
                            <Typography variant="caption" color="text.secondary">
                              Impact: {insight.impact}
                            </Typography>
                          )}
                        </Stack>
                      </Alert>
                    ))}
                  </Stack>
                </Section>
              )}
            </>
          )}

          {notes.length > 0 && (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              Source pages retained for every claim above (open the browser console profile object to expand).
            </Typography>
          )}
        </>
      )}
    </Paper>
  );
}
