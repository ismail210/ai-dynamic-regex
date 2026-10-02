import { lazy, Suspense, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { CloseOutlined, ExpandMoreOutlined, FindInPageOutlined } from "@mui/icons-material";
import { documentPdfUrl } from "../api/client";

// pdf.js only loads when a source page is actually opened.
const PdfDocumentViewer = lazy(() => import("./pdf/PdfDocumentViewer"));

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

// "S002 · PDF p. 2" -- sheet only when the extraction read one confidently.
function whereLabel(item) {
  const pages = item.pages?.length ? item.pages : item.page ? [item.page] : [];
  const shown = pages.slice(0, 6).join(", ") + (pages.length > 6 ? ", …" : "");
  const pdf = pages.length ? `PDF ${pages.length > 1 ? "pp." : "p."} ${shown}` : "";
  return item.sheet ? `${item.sheet} · ${pdf}` : pdf;
}

// Badges only for states that change how a row is read.
const STATUS_BADGE = {
  precast: { label: "precast · not steel", color: "default" },
  "not steel": { label: "not steel", color: "default" },
  "no steel": { label: "no steel (N/A)", color: "default" },
  verify: { label: "verify on sheet", color: "warning" },
};

const RULE_LABEL = {
  "default unless otherwise noted": "Default, U.N.O.",
  "symbol denotes": "Symbol",
  "scope of TYP / SIM conditions": "TYP / SIM scope",
  "scoped convention": "Convention",
  "detail reference": "Reference",
  "schedule note": "Schedule note",
};

const COLLAPSED_ROWS = 4;
const COLLAPSED_RULES = 6;

function ModelNote({ text }) {
  if (!text) return null;
  return (
    <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontStyle: "italic" }}>
      Model note: {text}
    </Typography>
  );
}

// What the mark is read as: the catalog designation when one exists, else
// the schedule's printed size/text -- never an invented plate designation.
function designationOf(item) {
  if (item.designation) {
    return { main: item.designation, sub: `${item.role} · ${item.designation_source}` };
  }
  if (item.relation === "mark defines plate") {
    return { main: item.printed, sub: `${item.role} · printed size, no catalog designation` };
  }
  return { main: item.printed || "—", sub: item.role };
}

function conditionsOf(item) {
  return [
    ...(item.configuration || []),
    ...(item.parts || []).map((p) => `${p.role} ${p.printed}`),
  ];
}

// One button per source: opens the uploaded PDF on that page (1-based).
function ViewPageButton({ item, label, onView }) {
  if (!onView || !item.page) return null;
  const where = whereLabel({ sheet: item.sheet, page: item.page });
  return (
    <Button
      size="small"
      variant="outlined"
      startIcon={<FindInPageOutlined fontSize="small" />}
      onClick={() => onView(item)}
      aria-label={`View ${where}${item.mark ? ` for ${item.mark}` : ""}`}
      sx={{ whiteSpace: "nowrap", flexShrink: 0 }}
    >
      {label || `View p. ${item.page}`}
    </Button>
  );
}

function EvidenceDetails({ item, note }) {
  return (
    <Box sx={{ py: 1, px: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
      <Typography variant="caption" color="text.secondary" display="block">
        Schedule row as extracted ({item.schedule}, {whereLabel(item)})
      </Typography>
      <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-word" }}>
        {item.source_text}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
        Definition read from the live schedule grid: it tells you how to read {item.mark} on a
        plan. It is not an installed member and not a quantity.
      </Typography>
      <ModelNote text={note} />
    </Box>
  );
}

function StatusBadge({ status }) {
  const badge = STATUS_BADGE[status];
  if (!badge) return null;
  return <Chip size="small" variant="outlined" color={badge.color} label={badge.label} />;
}

function DefinitionTableRow({ item, note, onView, sourceLabel }) {
  const [open, setOpen] = useState(false);
  const { main, sub } = designationOf(item);
  return (
    <>
      <TableRow sx={{ "& > td": { borderBottom: open ? 0 : undefined, verticalAlign: "top" } }}>
        <TableCell sx={{ width: "4.5rem" }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ fontFamily: "monospace" }}>
            {item.mark}
          </Typography>
        </TableCell>
        <TableCell>
          <Typography variant="subtitle1" fontWeight={600}>{main}</Typography>
          <Typography variant="caption" color="text.secondary">{sub}</Typography>
        </TableCell>
        <TableCell>
          <Stack spacing={0.5} sx={{ alignItems: "flex-start" }}>
            {conditionsOf(item).map((c) => (
              <Typography key={c} variant="body2" color="text.secondary">{c}</Typography>
            ))}
            <StatusBadge status={item.status} />
          </Stack>
        </TableCell>
        <TableCell align="right" sx={{ width: "1%" }}>
          <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
            <ViewPageButton item={item} label={sourceLabel} onView={onView} />
            <Button
              size="small"
              onClick={() => setOpen(!open)}
              aria-expanded={open}
              aria-label={`${open ? "Hide" : "Show"} source details for ${item.mark}`}
            >
              {open ? "Hide" : "Details"}
            </Button>
          </Stack>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={4} sx={{ py: 0, borderBottom: open ? undefined : 0 }}>
          <Collapse in={open} unmountOnExit>
            <Box sx={{ pb: 1.5 }}>
              <EvidenceDetails item={item} note={note} />
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

function DefinitionCard({ item, note, onView, sourceLabel }) {
  const [open, setOpen] = useState(false);
  const { main, sub } = designationOf(item);
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "baseline" }}>
        <Typography variant="h6" component="span" fontWeight={700} sx={{ fontFamily: "monospace" }}>
          {item.mark}
        </Typography>
        <Typography variant="subtitle1" component="span" fontWeight={600} sx={{ wordBreak: "break-word" }}>
          {main}
        </Typography>
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block">{sub}</Typography>
      {conditionsOf(item).map((c) => (
        <Typography key={c} variant="body2" color="text.secondary">{c}</Typography>
      ))}
      {item.status && <Box sx={{ mt: 0.75 }}><StatusBadge status={item.status} /></Box>}
      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
        <ViewPageButton item={item} label={sourceLabel} onView={onView} />
        <Button size="small" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide details" : "Details"}
        </Button>
      </Stack>
      <Collapse in={open} unmountOnExit>
        <Box sx={{ mt: 1 }}>
          <EvidenceDetails item={item} note={note} />
        </Box>
      </Collapse>
    </Paper>
  );
}

function DefinitionGroup({ label, schedule, items, notes, onView, compact }) {
  const [open, setOpen] = useState(false);
  // One extra row is shown rather than hidden behind a "Show all" button.
  const collapsible = items.length > COLLAPSED_ROWS + 1;
  const shown = open || !collapsible ? items : items.slice(0, COLLAPSED_ROWS);
  // The whole group usually sits on one sheet/page: say it once, up top.
  const places = new Set(items.map((i) => `${i.sheet}|${i.page}`));
  const common = places.size === 1 ? whereLabel(items[0]) : "";
  const sourceLabel = common ? "View page" : undefined;
  return (
    <Paper variant="outlined" sx={{ mb: 2, overflow: "hidden" }}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ px: 2, py: 1.25, alignItems: "baseline", flexWrap: "wrap", bgcolor: "action.hover" }}
      >
        <Typography variant="subtitle1" fontWeight={700}>{label}</Typography>
        <Typography variant="body2" color="text.secondary">
          {schedule}{common ? ` · ${common}` : ""} · {items.length} mark{items.length === 1 ? "" : "s"}
        </Typography>
      </Stack>
      {compact ? (
        <Stack spacing={1} sx={{ p: 1.5 }}>
          {shown.map((item) => (
            <DefinitionCard key={item.id} item={item} note={notes[item.id]} onView={onView} sourceLabel={sourceLabel} />
          ))}
        </Stack>
      ) : (
        <Table size="small" aria-label={`${label} definitions`}>
          <TableHead>
            <TableRow>
              <TableCell>Mark</TableCell>
              <TableCell>Defined section / component</TableCell>
              <TableCell>Configuration &amp; associated parts</TableCell>
              <TableCell align="right">Source</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {shown.map((item) => (
              <DefinitionTableRow
                key={item.id}
                item={item}
                note={notes[item.id]}
                onView={onView}
                sourceLabel={sourceLabel}
              />
            ))}
          </TableBody>
        </Table>
      )}
      {collapsible && (
        <Box sx={{ px: 1.5, pb: 1 }}>
          <Button size="small" onClick={() => setOpen(!open)}>
            {open ? "Show fewer" : `Show all ${items.length}`}
          </Button>
        </Box>
      )}
    </Paper>
  );
}

function MarksAndDefinitions({ definitions, notes, onView }) {
  const compact = useMediaQuery(useTheme().breakpoints.down("md"));
  const groups = [];
  for (const item of definitions) {
    let group = groups.find((g) => g.component === item.component);
    if (!group) {
      group = { component: item.component, label: item.component_label, schedule: item.schedule, items: [] };
      groups.push(group);
    }
    group.items.push(item);
  }
  return (
    <Section title="Marks and definitions">
      <Typography variant="body2" color="text.secondary" mb={1.5}>
        Each row says how to read that mark where it appears on a plan. A schedule row is a
        definition, not an installed member — it is never a quantity.
      </Typography>
      {groups.map((g) => (
        <DefinitionGroup key={g.component} {...g} notes={notes} onView={onView} compact={compact} />
      ))}
    </Section>
  );
}

// Revit column schedules: what the schedule prints for each grid location.
// Reference only -- never a detected member and never a quantity.
function ColumnScheduleLocations({ locations, onView }) {
  const [open, setOpen] = useState(false);
  const collapsible = locations.length > COLLAPSED_ROWS + 1;
  const shown = open || !collapsible ? locations : locations.slice(0, COLLAPSED_ROWS);
  const hasLevel = locations.some((l) => l.level);
  const hasPlate = locations.some((l) => l.printed_base_plate);
  const places = new Set(locations.map((l) => `${l.sheet}|${l.page}`));
  const common = places.size === 1 ? whereLabel(locations[0]) : "";
  const schedule = locations[0].schedule;
  return (
    <Section title="Column Schedule Locations">
      <Typography variant="body2" color="text.secondary" mb={1.5}>
        Reference information from column schedules — not a quantity. Each row repeats what the
        schedule prints for a grid location; it is not a detected member.
      </Typography>
      <Paper variant="outlined" sx={{ mb: 2, overflow: "hidden" }}>
        {(schedule || common) && (
          <Typography variant="body2" color="text.secondary" sx={{ px: 2, py: 1.25, bgcolor: "action.hover" }}>
            {[schedule, common].filter(Boolean).join(" · ")}
          </Typography>
        )}
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small" aria-label="Column schedule locations">
            <TableHead>
              <TableRow>
                <TableCell>Location</TableCell>
                {hasLevel && <TableCell>Level</TableCell>}
                <TableCell>Size</TableCell>
                {hasPlate && <TableCell>Base plate</TableCell>}
                <TableCell align="right">Source</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {shown.map((loc, i) => (
                <TableRow key={`${loc.page}-${loc.location}-${loc.level}-${i}`}>
                  <TableCell sx={{ fontFamily: "monospace", fontWeight: 700 }}>{loc.location}</TableCell>
                  {hasLevel && <TableCell>{loc.level || "—"}</TableCell>}
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>
                      {loc.catalog_designation || loc.printed_size || "—"}
                    </Typography>
                    {!loc.catalog_designation && loc.printed_size && (
                      <Typography variant="caption" color="text.secondary">
                        printed size, no catalog designation
                      </Typography>
                    )}
                  </TableCell>
                  {hasPlate && <TableCell>{loc.printed_base_plate || "—"}</TableCell>}
                  <TableCell align="right" sx={{ width: "1%", whiteSpace: "nowrap" }}>
                    {!common && (
                      <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                        {whereLabel(loc)}
                      </Typography>
                    )}
                    <ViewPageButton
                      item={{ ...loc, mark: loc.location }}
                      label={common ? "View page" : undefined}
                      onView={onView}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
        {collapsible && (
          <Box sx={{ px: 1.5, pb: 1 }}>
            <Button size="small" onClick={() => setOpen(!open)}>
              {open ? "Show fewer" : "Show all rows"}
            </Button>
          </Box>
        )}
      </Paper>
    </Section>
  );
}

// The uploaded PDF on the source page, with the mark highlighted when its
// bounding box is known. Reuses the Drawing Review viewer; needs no prediction.
function SourceViewerDialog({ documentId, target, onClose }) {
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("md"));
  if (!target) return null;
  const title = [target.mark, whereLabel({ sheet: target.sheet, page: target.page })]
    .filter(Boolean)
    .join(" — ");
  return (
    <Dialog
      open
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      fullScreen={fullScreen}
      aria-labelledby="summary-source-title"
    >
      <DialogTitle id="summary-source-title" sx={{ pr: 6 }}>
        {title}
      </DialogTitle>
      <IconButton aria-label="Close source page" onClick={onClose} sx={{ position: "absolute", right: 8, top: 8 }}>
        <CloseOutlined />
      </IconButton>
      <DialogContent dividers sx={{ p: 0, height: fullScreen ? "100%" : "78vh" }}>
        <Suspense
          fallback={(
            <Box sx={{ display: "grid", placeItems: "center", height: "100%" }}>
              <CircularProgress size={28} />
            </Box>
          )}
        >
          <PdfDocumentViewer
            fileUrl={documentPdfUrl(documentId)}
            pageWindow={1}
            selection={{
              key: `${target.id || target.mark || "source"}-${target.page}`,
              pageNumber: target.page,
              boundingBox: target.bbox || null,
            }}
          />
        </Suspense>
      </DialogContent>
    </Dialog>
  );
}

function InterpretationRules({ rules, notes, onView }) {
  const [open, setOpen] = useState(false);
  const shown = open ? rules : rules.slice(0, COLLAPSED_RULES);
  return (
    <Section title="Rules affecting interpretation">
      <Stack spacing={0.75}>
        {shown.map((rule) => (
          <Box key={rule.id}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", flexWrap: "wrap" }}>
              <Chip size="small" variant="outlined" label={RULE_LABEL[rule.relation] || rule.relation} />
              <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
                {rule.text}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.25 }}>
              <Typography variant="caption" color="text.secondary">
                {rule.scope} · {whereLabel(rule)}
              </Typography>
              <ViewPageButton item={rule} onView={onView} />
            </Stack>
            <ModelNote text={notes[rule.id]} />
          </Box>
        ))}
      </Stack>
      {rules.length > COLLAPSED_RULES && (
        <Button size="small" onClick={() => setOpen(!open)} sx={{ mt: 0.5, px: 0.5 }}>
          {open ? "Show fewer" : `Show all ${rules.length} rules`}
        </Button>
      )}
    </Section>
  );
}

function NeedsAttention({ items, notes, onView }) {
  return (
    <Section title="Needs attention">
      <Alert severity="warning" variant="outlined" icon={false} sx={{ py: 0.25 }}>
        <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.75}>
          {items.map((u) => (
            <Typography key={u.id} component="li" variant="body2">
              {u.text}{" "}
              <Typography component="span" variant="caption" color="text.secondary">
                ({whereLabel(u)})
              </Typography>{" "}
              <ViewPageButton item={{ ...u, page: u.page || u.pages?.[0] }} onView={onView} />
              <ModelNote text={notes[u.id]} />
            </Typography>
          ))}
        </Stack>
      </Alert>
    </Section>
  );
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
export default function DrawingSummaryPanel({ profile, documentId = null }) {
  const [sourceTarget, setSourceTarget] = useState(null);
  if (!profile) return null;
  const onView = documentId ? setSourceTarget : null;

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
  const uncertainties = di?.uncertainties || [];
  const method = di?.method;

  const definitions = di?.definitions || [];
  const interpretationRules = di?.interpretation_rules || [];
  const unresolved = di?.unresolved || [];
  const columnLocations = di?.column_locations || [];
  const hasEvidence =
    definitions.length > 0 ||
    columnLocations.length > 0 ||
    interpretationRules.length > 0 ||
    unresolved.length > 0;
  // Model notes only ever annotate an existing evidence id (validated server-side).
  const modelNotes = Object.fromEntries(
    [...(di?.summary_llm?.key_facts || []), ...(di?.summary_llm?.cautions || [])].map((n) => [
      n.id,
      n.why,
    ]),
  );

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

          {definitions.length > 0 && (
            <MarksAndDefinitions definitions={definitions} notes={modelNotes} onView={onView} />
          )}
          {columnLocations.length > 0 && (
            <ColumnScheduleLocations locations={columnLocations} onView={onView} />
          )}
          {interpretationRules.length > 0 && (
            <InterpretationRules rules={interpretationRules} notes={modelNotes} onView={onView} />
          )}
          {unresolved.length > 0 && (
            <NeedsAttention items={unresolved} notes={modelNotes} onView={onView} />
          )}

          <SupportingDetails collapsed={hasEvidence}>
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
                  <Alert severity="warning" variant="outlined" icon={false} sx={{ py: 0.25 }}>
                    <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.25}>
                      {uncertainties.map((u, i) => (
                        <Typography key={i} component="li" variant="body2">
                          {u.value}
                          {u.source_pages?.length > 0 && (
                            <Typography component="span" variant="caption" color="text.secondary">
                              {" "}
                              (PDF {pagesLabel(u.source_pages)})
                            </Typography>
                          )}
                        </Typography>
                      ))}
                    </Stack>
                  </Alert>
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

          </SupportingDetails>
        </>
      )}
      <SourceViewerDialog
        documentId={documentId}
        target={sourceTarget}
        onClose={() => setSourceTarget(null)}
      />
    </Paper>
  );
}

// Page make-up, label families, TYP frequencies, scope stamps and page-level
// uncertainties: useful background, but not the default view once verified
// definitions exist. Without them (older cached profiles) it renders inline.
function SupportingDetails({ collapsed, children }) {
  if (!collapsed) return children;
  return (
    <Accordion disableGutters elevation={0} variant="outlined" sx={{ mt: 1 }}>
      <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
        <Typography variant="body2" fontWeight={600}>
          Supporting details
        </Typography>
      </AccordionSummary>
      <AccordionDetails>{children}</AccordionDetails>
    </Accordion>
  );
}
