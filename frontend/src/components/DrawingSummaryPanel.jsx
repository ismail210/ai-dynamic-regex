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
import { CloseOutlined, ExpandMoreOutlined } from "@mui/icons-material";
import { documentPdfUrl, getColumnTrace } from "../api/client";
import { formatPlate, formatPrintedSize } from "../lib/dimensions";
import { pagesLabel, ViewPageButton, whereLabel } from "./drawingSummary/sources";
import {
  ConflictComparison,
  Dim,
  EvidenceChain,
  LevelDiagram,
  NUMERIC,
  PlateDims,
  PlateRoles,
  StatusText,
} from "./drawingSummary/visuals";

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
  "notation key": "Notation key",
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

const titleCase = (text) => String(text || "").toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase());

// A printed cell's heading, under its group: "REINFORCEMENT VERTICAL" in the
// REINFORCEMENT group reads "Reinforcement · Vertical".
function cellLabel(cell) {
  const heading = String(cell.heading || "").trim();
  const group = String(cell.group || "").trim();
  if (!group || group === heading) return titleCase(heading) || "Value";
  const rest = heading.startsWith(`${group} `) ? heading.slice(group.length).trim() : heading;
  return `${titleCase(group)} · ${titleCase(rest)}`;
}

// Each printed cell under its own heading. Equal values in two columns are
// two values (vertical and horizontal reinforcement), never merged.
function LabelledCells({ cells }) {
  const shown = (cells || []).filter((c) => c.text);
  if (!shown.length) return <Typography variant="body2" color="text.secondary">Blank in the schedule</Typography>;
  return (
    <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1.5, rowGap: 0.25 }}>
      {shown.map((c, i) => (
        <Box key={`${c.heading}-${i}`} sx={{ display: "contents" }}>
          <Typography component="dt" variant="caption" color="text.secondary">{cellLabel(c)}</Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0 }}>
            {/^[\s\d'"′″/-]+$/.test(c.text) ? <Dim raw={c.text} /> : c.text}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function conditionsOf(item) {
  return [
    ...(item.configuration || []),
    ...(item.parts || []).map((p) => `${p.role} ${p.printed}`),
  ];
}

function EvidenceDetails({ item, note }) {
  return (
    <Box sx={{ py: 1, px: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        Schedule row as extracted ({item.schedule}, {whereLabel(item)})
      </Typography>
      <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-word" }}>
        {item.source_text}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
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
          {item.cells?.length ? (
            <LabelledCells cells={item.cells} />
          ) : (
            <>
              <Typography variant="subtitle1" fontWeight={600}>{main}</Typography>
              <Typography variant="caption" color="text.secondary">{sub}</Typography>
            </>
          )}
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
        {!item.cells?.length && (
          <Typography variant="subtitle1" component="span" fontWeight={600} sx={{ wordBreak: "break-word" }}>
            {main}
          </Typography>
        )}
      </Stack>
      {item.cells?.length ? (
        <LabelledCells cells={item.cells} />
      ) : (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{sub}</Typography>
      )}
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

function MarksAndDefinitions({ definitions, notes, onView, title = "Marks and definitions", intro }) {
  const compact = useMediaQuery(useTheme().breakpoints.down("md"));
  const groups = [];
  for (const item of definitions) {
    // Grouped by the printed table when it has a title (CONCRETE WALL SCHEDULE).
    const key = item.schedule_title || item.component;
    let group = groups.find((g) => g.key === key);
    if (!group) {
      group = {
        key,
        label: item.schedule_title ? titleCase(item.schedule_title) : item.component_label,
        schedule: item.schedule_title ? "Schedule" : item.schedule,
        items: [],
      };
      groups.push(group);
    }
    group.items.push(item);
  }
  return (
    <Section title={title}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {intro ||
          "Each row says how to read that mark where it appears on a plan. A schedule row is a definition, not an installed member — it is never a quantity."}
      </Typography>
      {groups.map(({ key, ...g }) => (
        <DefinitionGroup key={key} {...g} notes={notes} onView={onView} compact={compact} />
      ))}
    </Section>
  );
}

// Column schedules: one row per schedule column -- its section, the printed
// location(s), the base plate and notes, each with where it was read.
// Definitions only: a listed location is never a takeoff quantity.
const COLLAPSED_COLUMNS = 8;

const dimensionsText = (plate) => formatPlate(plate.dimensions).text;
const capitalize = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const plateTypeLabel = (plate) => (plate.type ? capitalize(plate.type) : "Plate");

// Plain words for what a plate value is. Missing, not shown, explicitly not
// applicable, unresolved and conflicting stay distinct.
const PLATE_STATUS_TEXT = {
  read: "Read from drawing",
  resolved: "Linked through schedule",
  reference: "Detail reference — dimensions on that detail",
  blank: "Blank in the schedule",
  not_applicable: "Printed as not applicable",
  not_shown: "Not shown in this schedule",
  conflict: "Sources disagree",
  unresolved: "Not established",
  unreadable: "Not established — could not be read",
};
const PLATE_NEEDS_REVIEW = new Set(["conflict", "unresolved", "unreadable"]);

function plateSummary(plate) {
  const type = plateTypeLabel(plate);
  switch (plate.status) {
    case "read":
      return { main: dimensionsText(plate), sub: `${type} · as printed` };
    case "resolved":
      return { main: dimensionsText(plate), sub: `${type} ${plate.printed}` };
    case "reference":
      return {
        main: `See detail ${plate.reference.detail} on ${plate.reference.sheet}`,
        sub: "Dimensions are on that detail — not read",
      };
    case "blank":
      return { main: "Blank", sub: plate.note };
    case "not_applicable":
      return { main: plate.printed || "N/A", sub: "Printed as not applicable" };
    case "not_shown":
      return { main: "—", sub: "Not given in this schedule" };
    default:
      return { main: plate.printed || "—", sub: plate.note || "Could not be read" };
  }
}

function locationLabel(location) {
  if (location.status !== "parsed") return location.raw;
  return location.grids
    .map((g) => (g.offset ? `${g.label} (${g.offset.raw} offset)` : g.label))
    .join(" × ");
}

function columnLabel(entry) {
  if (entry.mark) return entry.mark;
  const [first, ...rest] = entry.locations || [];
  if (!first) return entry.location_text || "—";
  return rest.length ? `${first.raw} +${rest.length}` : first.raw;
}

function SourceTrail({ via, onView }) {
  if (!via?.length) return null;
  return (
    <Stack spacing={0.75}>
      {via.map((source, i) => (
        <Stack key={`${source.kind}-${i}`} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="caption" color="text.secondary" sx={{ minWidth: "8.5rem" }}>
            {source.kind}
            {source.title ? ` · ${source.title}` : ""}
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-word" }}>
            {source.text}
          </Typography>
          <ViewPageButton
            item={{ ...source, mark: source.text }}
            label={`View ${whereLabel(source)}`}
            onView={onView}
          />
        </Stack>
      ))}
    </Stack>
  );
}

// Level names as the reader says them: "T.O. SLAB LEVEL 1" -> "Level 1".
function shortLevel(name) {
  return titleCase(String(name || "").replace(/^\s*(?:T\.?\s*O\.?|TOP OF)\s+(?:SLAB\s+|STEEL\s+|DECK\s+)?/i, "")) || name;
}

// The answer an estimator looks for first: where, which section, which
// plate (with each dimension's role), which levels the schedule draws it
// between -- and that a level-to-level difference is not a member length.
function ColumnCard({ entry, scheduleName }) {
  const plate = entry.plate || {};
  const designation = entry.sections?.find((s) => s.designation)?.designation;
  const grids = entry.locations?.length === 1 && entry.locations[0].status === "parsed" ? entry.locations[0].grids : null;
  const diff = entry.level_difference;
  const extent = entry.extent;
  const ends = extent && ["top", "bottom"].every((k) => extent[k]?.position === "at");
  return (
    <Box>
      <Typography variant="subtitle1" fontWeight={700} sx={{ userSelect: "text" }}>
        <Box component="span" sx={{ fontFamily: "monospace" }}>{columnLabel(entry)}</Box>
        {designation ? ` · ${designation}` : ""}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {[scheduleName, grids && grids.map((g) => `Grid ${g.label}${g.offset ? ` (offset ${g.offset.raw}, direction not stated)` : ""}`).join(" / ")]
          .filter(Boolean)
          .join(" · ")}
      </Typography>
      {(plate.printed || plate.dimensions?.length) && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" fontWeight={600}>
            {plateTypeLabel(plate)} {plate.printed || ""}
          </Typography>
          {plate.dimensions?.length ? <PlateRoles dimensions={plate.dimensions} /> : (
            <Typography variant="caption" color="text.secondary">{PLATE_STATUS_TEXT[plate.status] || "Not established"}</Typography>
          )}
        </Box>
      )}
      {extent && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2">
            Vertical extent:{" "}
            {ends
              ? `${shortLevel(extent.bottom.line.name)} → ${shortLevel(extent.top.line.name)}`
              : "not established at both ends"}
          </Typography>
          {diff?.status === "computed" ? (
            <>
              <Typography variant="body2">
                Elevation difference: <Dim inches={diff.inches} strong />
              </Typography>
              <StatusText status="calculated" />
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                Fabricated member length unconfirmed.
              </Typography>
            </>
          ) : null}
        </Box>
      )}
    </Box>
  );
}

function ColumnEntryDetails({ entry, onView, documentId, levels, note, scheduleName }) {
  const plate = entry.plate;
  return (
    <Stack spacing={1.25} sx={{ py: 1, px: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
      <ColumnCard entry={entry} scheduleName={scheduleName} />
      <EvidenceChain entry={entry} onView={onView} />
      {entry.extent && levels?.length > 1 && (
        <LevelDiagram levels={levels} extent={entry.extent} scheduleName={scheduleName} />
      )}
      <ModelNote text={note} />
      {entry.key_role === "location" ? (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Location text as printed
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-word" }}>
            {entry.location_text}
          </Typography>
          <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
            {entry.locations.map((location) => (
              <Typography component="li" variant="body2" key={location.raw}>
                {location.status === "parsed" ? (
                  <>
                    Grid {location.grids.map((g) => g.label).join(" and grid ")}
                    {location.grids.some((g) => g.offset) &&
                      ` — offset ${location.grids
                        .filter((g) => g.offset)
                        .map((g) => `${g.offset.raw} from grid ${g.label}`)
                        .join(", ")} (direction not stated)`}
                  </>
                ) : (
                  <>
                    <Box component="span" sx={{ fontFamily: "monospace" }}>{location.raw}</Box> — not a
                    recognized grid intersection; kept as printed
                  </>
                )}
              </Typography>
            ))}
          </Box>
          {entry.repeated_label && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              The same location text is printed at the top and bottom of this column — one entry, not two.
            </Typography>
          )}
          {entry.label_conflict && (
            <Typography variant="caption" color="warning.main" sx={{ mt: 0.5, display: "block" }}>
              Top and bottom location labels differ: {entry.label_conflict}
            </Typography>
          )}
        </Box>
      ) : (
        <Typography variant="body2">{entry.location_note}</Typography>
      )}
      <Box>
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
          Where the base plate was read
        </Typography>
        {plate.via?.length ? (
          <SourceTrail via={plate.via} onView={onView} />
        ) : (
          <Typography variant="body2" color="text.secondary">{plateSummary(plate).sub}</Typography>
        )}
        {plate.status === "reference" && (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.75 }}>
            <Typography variant="body2">
              Detail {plate.reference.detail} / {plate.reference.sheet}
              {plate.reference.page ? "" : " — sheet not found in this PDF"}
            </Typography>
            {plate.reference.page && (
              <ViewPageButton
                item={{ page: plate.reference.page, sheet: plate.reference.sheet, mark: `detail ${plate.reference.detail}` }}
                label={`Open ${plate.reference.sheet}`}
                onView={onView}
              />
            )}
          </Stack>
        )}
        {plate.markers?.length > 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            Printed with the note marker {plate.markers.join(" ")} — check the schedule notes.
          </Typography>
        )}
      </Box>
      {entry.conflicts?.length > 0 && (
        <Alert severity="warning" variant="outlined" sx={{ py: 0 }}>
          {entry.conflicts.join(" ")}
        </Alert>
      )}
      {entry.hidden_text?.length > 0 && (
        <Typography variant="caption" color="text.secondary">
          Text hidden under a white mask in this column was ignored ({entry.hidden_text.join(", ")}); the
          visible drawing was used.
        </Typography>
      )}
      <ColumnExtent entry={entry} />
      {documentId && <ColumnTrace entry={entry} documentId={documentId} onView={onView} />}
      <Typography variant="caption" color="text.secondary">
        A schedule entry is a definition, not a counted member — it is never a takeoff quantity.
      </Typography>
    </Stack>
  );
}

// Section cell: the catalog designation; for a label a schedule note makes
// concrete, "Precast concrete · C1" and its printed size; else the printed text.
function SectionCell({ entry }) {
  const sections = entry.sections || [];
  const material = entry.material?.status === "read" ? entry.material : null;
  if (material) {
    return (
      <Box>
        <Typography variant="body2" fontWeight={600}>
          {capitalize(material.material)} · {material.mark}
        </Typography>
        {material.size ? (
          <Typography variant="body2" sx={NUMERIC} title={`As printed: ${material.size.raw}`}>
            {formatPrintedSize(material.size.raw)}
          </Typography>
        ) : null}
        <Typography variant="caption" color="text.secondary">Per the schedule note · not steel</Typography>
      </Box>
    );
  }
  if (sections.length === 0) return <Typography variant="body2">—</Typography>;
  return sections.map((s, i) => (
    <Box key={`${s.printed}-${i}`}>
      <Typography variant="body2" fontWeight={600} sx={{ userSelect: "all" }}>{s.designation || s.printed}</Typography>
      {!s.designation && (
        <Typography variant="caption" color="text.secondary">Printed text; no catalog section</Typography>
      )}
    </Box>
  ));
}

function PlateCell({ plate }) {
  const hasDims = (plate.status === "read" || plate.status === "resolved") && plate.dimensions?.length;
  const summary = plateSummary(plate);
  return (
    <Box>
      {hasDims ? (
        <>
          {plate.printed && plate.status === "resolved" && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {plateTypeLabel(plate)} {plate.printed}
            </Typography>
          )}
          <PlateDims dimensions={plate.dimensions} />
        </>
      ) : (
        <>
          <Typography variant="body2" fontWeight={600}>{summary.main}</Typography>
          {/* The status line below already says "not shown"; no second line for it. */}
          {plate.status !== "not_shown" && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{summary.sub}</Typography>
          )}
        </>
      )}
      <Typography variant="caption"
        color={PLATE_NEEDS_REVIEW.has(plate.status) ? "warning.main" : "text.secondary"} sx={{ display: "block" }}>
        {PLATE_STATUS_TEXT[plate.status] || "Not established"}
      </Typography>
    </Box>
  );
}

function ColumnEntryRow({ entry, onView, documentId, levels, note, scheduleName }) {
  const [open, setOpen] = useState(false);
  const notes = [
    ...(entry.notes || []),
    ...(entry.other_plates || []).map((p) => `${p.type}: ${dimensionsText(p)} (schedule note)`),
  ];
  const label = columnLabel(entry);
  return (
    <>
      <TableRow sx={{ "& > td": { borderBottom: open ? 0 : undefined, verticalAlign: "top" } }}>
        <TableCell>
          <Typography variant="body2" fontWeight={700} sx={{ fontFamily: "monospace" }}>
            {label}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {entry.key_role === "location"
              ? entry.listed_location_count > 1
                ? `${entry.listed_location_count} locations listed`
                : "grid location"
              : "column mark"}
          </Typography>
        </TableCell>
        <TableCell>
          <SectionCell entry={entry} />
        </TableCell>
        <TableCell>
          <PlateCell plate={entry.plate} />
        </TableCell>
        <TableCell>
          {notes.map((n) => (
            <Typography key={n} variant="body2" color="text.secondary">{n}</Typography>
          ))}
        </TableCell>
        <TableCell align="right" sx={{ width: "1%", whiteSpace: "nowrap" }}>
          <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
            <ViewPageButton item={{ ...entry, mark: label }} label="View column schedule" onView={onView} />
            <Button
              size="small"
              onClick={() => setOpen(!open)}
              aria-expanded={open}
              aria-label={`${open ? "Hide" : "Show"} details for ${label}`}
            >
              {open ? "Hide" : "Details"}
            </Button>
          </Stack>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={5} sx={{ py: 0, borderBottom: open ? undefined : 0 }}>
          <Collapse in={open} unmountOnExit>
            <Box sx={{ pb: 1.5 }}>
              <ColumnEntryDetails entry={entry} onView={onView} documentId={documentId} levels={levels} note={note}
                scheduleName={scheduleName} />
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

function ColumnScheduleBlock({ schedule, entries, onView, documentId, levels, notes = {} }) {
  const [open, setOpen] = useState(false);
  const collapsible = entries.length > COLLAPSED_COLUMNS + 1;
  const shown = open || !collapsible ? entries : entries.slice(0, COLLAPSED_COLUMNS);
  const where = whereLabel({ sheet: schedule.sheets.filter(Boolean).join(", "), pages: schedule.pages });
  return (
    <Paper variant="outlined" sx={{ mb: 2, overflow: "hidden" }}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ px: 2, py: 1.25, alignItems: "center", flexWrap: "wrap", bgcolor: "action.hover" }}
      >
        <Typography variant="subtitle1" fontWeight={700}>{schedule.name}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
          {[
            where,
            schedule.layout === "graphical" ? "graphical schedule" : "table",
            schedule.block_count > 1 ? `printed in ${schedule.block_count} parts` : "",
            `${entries.length} schedule entr${entries.length === 1 ? "y" : "ies"}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </Typography>
        <ViewPageButton item={{ ...schedule, mark: schedule.name }} label="View column schedule" onView={onView} />
      </Stack>
      {(schedule.notes.length > 0 || schedule.hidden_text.length > 0) && (
        <Box sx={{ px: 2, pt: 1 }}>
          {schedule.notes.map((n) => (
            <Typography key={n} variant="body2" color="text.secondary">{n}</Typography>
          ))}
          {schedule.hidden_text.length > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {schedule.hidden_text.length} text item{schedule.hidden_text.length === 1 ? "" : "s"} hidden
              under white masks in this schedule {schedule.hidden_text.length === 1 ? "was" : "were"} ignored;
              values come from the visible drawing.
            </Typography>
          )}
        </Box>
      )}
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small" aria-label={`${schedule.name} columns`}>
          <TableHead>
            <TableRow>
              <TableCell>{schedule.key_role === "location" ? "Location" : "Mark"}</TableCell>
              <TableCell>Section</TableCell>
              <TableCell>Base plate</TableCell>
              <TableCell>Notes</TableCell>
              <TableCell align="right">Source</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {shown.map((entry) => (
              <ColumnEntryRow key={entry.id} entry={entry} onView={onView} documentId={documentId} levels={levels}
                note={notes[entry.id]} scheduleName={schedule.name} />
            ))}
          </TableBody>
        </Table>
      </Box>
      {collapsible && (
        <Box sx={{ px: 1.5, pb: 1 }}>
          <Button size="small" onClick={() => setOpen(!open)}>
            {open ? "Show fewer" : `Show all ${entries.length}`}
          </Button>
        </Box>
      )}
    </Paper>
  );
}

function ColumnSchedules({ data, schedules, title, intro, onView, documentId, levelsBySchedule = {}, notes = {} }) {
  return (
    <Section title={title}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{intro}</Typography>
      {schedules.map((schedule) => (
        <ColumnScheduleBlock
          key={schedule.id}
          schedule={schedule}
          entries={data.entries.filter((e) => e.schedule_id === schedule.id)}
          onView={onView}
          documentId={documentId}
          levels={levelsBySchedule[schedule.id]}
          notes={notes}
        />
      ))}
    </Section>
  );
}

// Column tracing pilot: the schedule column looked for on the framing plans of
// the levels it spans. Observations are shown with their sources; ends are
// established only by the schedule's drawn extent or an explicit annotation.
const OBSERVATION_LABEL = {
  column_symbol: "column symbol drawn at the grid intersection",
  not_detected: "no column symbol detected at the grid intersection (not evidence of absence)",
  grids_not_found: "both grid lines were not found on this plan",
};

// The ends themselves are shown by ColumnExtent; the trace adds only what a
// plan prints at that end (``POST UP`` where the column starts).
function TraceEnd({ which, end, onView }) {
  return end.plan_annotations?.map((a, i) => (
    <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center" }}>
      <Typography variant="body2">
        {which} end: {a.sheet || `p. ${a.page}`} prints “{a.text}” with a leader to the column
      </Typography>
      <ViewPageButton item={{ ...a, mark: `${a.text} (${which.toLowerCase()} end)` }} label="View" onView={onView} />
    </Stack>
  ));
}

const SCOPE_LABEL = {
  consistent: "same building / area",
  supported_by_datum: "same building / area (datum note)",
  consistent_by_sheet_family: "same building / area (sheet family)",
  single_schedule: "one column schedule in the set",
  unresolved: "building / area not established",
};

function ScopeLine({ scope }) {
  if (!scope) return null;
  const counts = scope.status !== "unresolved";
  return (
    <Typography variant="caption" color={counts ? "text.secondary" : "warning.main"} sx={{ display: "block" }}>
      Scope: {SCOPE_LABEL[scope.status] || scope.status}
      {scope.view_title || scope.sheet_title ? ` — ${scope.view_title || scope.sheet_title}` : ""}. {scope.note}
    </Typography>
  );
}

const SCALE_LABEL = {
  calibrated: "calibrated from grid dimensions",
  printed: "printed, not validated",
  nts: "not to scale",
  unresolved: "not established",
};
const OFFSET_LABEL = {
  unresolved_direction: "side not established",
  unresolved_scale: "not placed (scale)",
  unresolved_two_offsets: "not placed",
};

function OffsetLine({ candidate, plan, levelName, onView }) {
  const { scale, offset } = candidate;
  return (
    <Box sx={{ pl: 1 }}>
      {scale && (
        <Typography variant="caption" color={["validated", "calibrated"].includes(scale.status) ? "text.secondary" : "warning.main"} sx={{ display: "block" }}>
          Scale: {SCALE_LABEL[scale.status] || scale.status}
          {scale.printed?.raw ? ` — ${scale.printed.raw}` : ""}. {scale.note}
        </Typography>
      )}
      {offset && (
        <>
          <Typography variant="caption" sx={{ display: "block" }}>
            Offset {offset.printed} from grid {offset.grid}: <b>{OFFSET_LABEL[offset.status] || offset.status}</b>. {offset.note}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
            {offset.sides?.map((side, j) => (
              <ViewPageButton
                key={j}
                item={{ page: candidate.page, sheet: plan.sheet, bbox: side.symbol?.bbox || side.point_bbox,
                  mark: `${levelName} offset toward grid ${side.toward || "?"}` }}
                label={`Toward ${side.toward ? `grid ${side.toward}` : "edge"}${side.symbol ? " (column drawn)" : ""}`}
                onView={onView}
              />
            ))}
          </Stack>
        </>
      )}
    </Box>
  );
}

function TracePlan({ plan, levelName, onView }) {
  return (
    <Box sx={{ pl: 2, mb: 0.75 }}>
      <Typography variant="body2">
        {plan.sheet || `p. ${plan.page}`} · {plan.plan}{" "}
        <Typography component="span" variant="caption" color="text.secondary">({plan.matched_by})</Typography>
      </Typography>
      <Typography
        variant="caption"
        color={plan.observation === "column_symbol" ? "success.main" : "text.secondary"} sx={{ display: "block" }}>
        {OBSERVATION_LABEL[plan.observation] || plan.observation}
      </Typography>
      {plan.note && <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{plan.note}</Typography>}
      <ScopeLine scope={plan.scope} />
      {plan.scope_unresolved && (
        <Typography variant="caption" color="warning.main" sx={{ display: "block" }}>
          Shown as a candidate only: nothing printed ties this view to the schedule's building or area.
        </Typography>
      )}
      {plan.candidates.map((c, i) => (
        <Stack key={i} spacing={0.25} sx={{ pl: 1.5, mt: 0.25 }}>
          <ScopeLine scope={c.scope} />
          <OffsetLine candidate={c} plan={plan} levelName={levelName} onView={onView} />
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <ViewPageButton
              item={{
                page: c.page,
                sheet: plan.sheet,
                bbox: c.symbol?.bbox || c.point_bbox,
                mark: `${levelName} grid intersection${plan.candidates.length > 1 ? ` ${i + 1}` : ""}`,
              }}
              label={plan.candidates.length > 1 ? `Intersection ${i + 1}` : "View intersection"}
              onView={onView}
            />
            {c.annotations.map((a, j) => (
              <Typography key={j} variant="caption">“{a.text}” — {a.how}</Typography>
            ))}
          </Stack>
          {c.nearby_text.length > 0 && (
            <Typography variant="caption" color="text.secondary">
              Nearby, not associated: {c.nearby_text.slice(0, 6).map((n) => n.text).join("; ")}
            </Typography>
          )}
        </Stack>
      ))}
    </Box>
  );
}

function ColumnTrace({ entry, documentId, onView }) {
  const [state, setState] = useState({ loading: false, trace: null, error: null });
  const location = entry.location_text || entry.mark;
  if (!location) return null;
  // An entry listing several locations is traced one location at a time.
  const locations = entry.locations?.length > 1 ? entry.locations.map((loc) => loc.raw) : [location];
  const load = async (location) => {
    setState({ loading: true, trace: null, error: null });
    try {
      const trace = await getColumnTrace(documentId, location, entry.schedule_id);
      setState({ loading: false, trace, error: null });
    } catch (error) {
      setState({ loading: false, trace: null, error: error.friendlyMessage || "The trace could not be loaded." });
    }
  };
  const trace = state.trace;
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
        On the framing plans (pilot)
      </Typography>
      {!trace && (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", alignItems: "center" }} useFlexGap>
          {state.loading && <CircularProgress size={14} />}
          {locations.length > 1 && <Typography variant="caption">Look for one location on the plans:</Typography>}
          {locations.map((loc) => (
            <Button key={loc} size="small" variant="outlined" onClick={() => load(loc)} disabled={state.loading}>
              {locations.length > 1 ? loc : "Look for this column on the plans"}
            </Button>
          ))}
        </Stack>
      )}
      {trace && locations.length > 1 && (
        <Button size="small" onClick={() => setState({ loading: false, trace: null, error: null })}>
          Trace another location
        </Button>
      )}
      {state.error && <Alert severity="warning" variant="outlined" sx={{ py: 0, mt: 0.5 }}>{state.error}</Alert>}
      {trace && trace.status !== "traced" && (
        <Typography variant="body2" color="text.secondary">{trace.note}</Typography>
      )}
      {trace?.status === "traced" && (
        <Stack spacing={0.75}>
          <TraceEnd which="Top" end={trace.ends.top} onView={onView} />
          <TraceEnd which="Bottom" end={trace.ends.bottom} onView={onView} />
          {trace.levels.map((level) => (
            <Box key={level.name}>
              <Typography variant="body2" fontWeight={600}>
                {level.name}{level.elevation ? ` (${level.elevation})` : ""}
              </Typography>
              {level.note && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", pl: 2 }}>{level.note}</Typography>
              )}
              {level.plans.map((plan) => (
                <TracePlan key={plan.page} plan={plan} levelName={level.name} onView={onView} />
              ))}
              {level.other_scope_views?.map((o, i) => (
                <Typography key={`o${i}`} variant="caption" color="text.secondary" sx={{ display: "block", pl: 2 }}>
                  Not this building / area: {o.sheet || `p. ${o.page}`} · {o.view_title || o.sheet_title} — {o.note}
                </Typography>
              ))}
              {level.other_titled_sheets?.length > 0 && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", pl: 2 }}>
                  Also titled for this level, without these grid labels: {level.other_titled_sheets.join(", ")}
                </Typography>
              )}
            </Box>
          ))}
          {trace.directional_evidence?.length > 0 && (
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                Notes with a leader to the column (continuation evidence, not an end by themselves):
              </Typography>
              {trace.directional_evidence.map((d, i) => (
                <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center", pl: 2 }}>
                  <Typography variant="caption">
                    {d.level} · {d.sheet || `p. ${d.page}`}: “{d.text}”{d.direction ? ` (${d.direction})` : ""}
                    {d.scope_counts ? "" : " — scope not established"}
                  </Typography>
                  <ViewPageButton item={{ ...d, mark: `${d.text} on ${d.level}` }} label="View" onView={onView} />
                </Stack>
              ))}
            </Box>
          )}
          {trace.notes.map((note, i) => (
            <Typography key={i} variant="caption" color="text.secondary" sx={{ display: "block" }}>{note}</Typography>
          ))}
          <Typography variant="caption" color="text.secondary">{trace.summary.note}</Typography>
        </Stack>
      )}
    </Box>
  );
}

// Levels and elevations: what the schedules and plan notes state about each
// level, kept as separate sourced records. A difference between two level
// elevations is never presented as a column length.
const surfaceLabel = (s) => capitalize(s) || "Elevation";
const COLLAPSED_ELEVATIONS = 12;

function endLabel(end) {
  if (!end) return "—";
  const level = (ref) => `${ref.name || "unnamed line"}${ref.elevation_text ? ` (${ref.elevation_text})` : ""}`;
  switch (end.position) {
    case "at":
      return `at ${level(end.line)}`;
    case "between":
      return `between ${level(end.upper)} and ${level(end.lower)}${
        end.near ? ` — drawn just ${end.near === "upper" ? "below" : "above"} ${end[end.near].name}` : ""
      }`;
    case "above":
      return `above ${level(end.lower)}`;
    case "below":
      return `below ${level(end.upper)}`;
    default:
      return "not on a level line";
  }
}

function ColumnExtent({ entry }) {
  if (!entry.extent) return null;
  const diff = entry.level_difference;
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        Ends as drawn in the schedule
      </Typography>
      <Typography variant="body2">Top: {endLabel(entry.extent.top)}</Typography>
      <Typography variant="body2">Bottom: {endLabel(entry.extent.bottom)}</Typography>
      {diff?.status === "computed" ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          Elevation difference = {diff.upper.name} {diff.upper.elevation} − {diff.lower.name} {diff.lower.elevation}:
          the difference between two printed level elevations, not the column's length.
        </Typography>
      ) : (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          No height shown: {diff?.note || "the schedule does not establish both ends."}
        </Typography>
      )}
    </Box>
  );
}

// Never "no elevation": an unlinked level may still be stated somewhere.
const ASSOCIATION_EMPTY = {
  checked_no_value: "Elevation not found in the linked sources",
  unresolved: "No linked plan evidence yet",
};

function LevelRow({ level, onView, note }) {
  const sourceItem = { page: level.page, sheet: level.sheet, bbox: level.bbox, mark: level.name };
  const linked = level.plan_matches || [];
  return (
    <TableRow sx={{ "& > td": { verticalAlign: "top" } }}>
      <TableCell>
        <Typography variant="body2" fontWeight={700}>{level.name || "Unnamed level line"}</Typography>
        {level.surface && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{surfaceLabel(level.surface)}</Typography>
        )}
      </TableCell>
      <TableCell>
        <Typography variant="body2" fontWeight={600}>{level.printed ? <Dim raw={level.printed} /> : "—"}</Typography>
        <StatusText status={level.status === "read" ? "read" : "not_established"} />
        {level.resolved && (
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            {surfaceLabel(level.resolved.surface)} <Dim raw={level.resolved.display} /> on {level.resolved.via}
          </Typography>
        )}
        {level.note && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{level.note}</Typography>
        )}
      </TableCell>
      <TableCell>
        {linked.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            {ASSOCIATION_EMPTY[level.association] || ASSOCIATION_EMPTY.unresolved}
            {level.also_titled?.length > 0 ? ` (checked ${level.also_titled.join(", ")})` : ""}
          </Typography>
        )}
        {linked.map((match) => (
          <Box key={match.page} sx={{ mb: 0.75 }}>
            <Typography variant="body2">
              {match.plan} ({match.sheet || `p. ${match.page}`})
            </Typography>
            {match.plan_qualifiers?.length > 0 && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                The plan names it with “{match.plan_qualifiers.join(" ")}”; the schedule does not.
              </Typography>
            )}
            {match.values.map((v, i) => (
              <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                <Typography variant="body2">
                  {surfaceLabel(v.surface)}{v.name ? ` (${titleCase(v.name)})` : ""} <Dim raw={v.raw || v.display} />
                  {v.status === "derived" ? " (derived)" : ""}
                </Typography>
                <ViewPageButton item={{ ...v.source, mark: `${surfaceLabel(v.surface)} ${v.display}` }}
                  label="View plan note" onView={onView} />
              </Stack>
            ))}
            <StatusText
              status={match.association === "candidate" ? "candidate" : match.comparison === "differs" ? "disagree" : "linked"}
            >
              {match.comparison === "agrees" ? " · agrees with the schedule" : ""}
            </StatusText>
          </Box>
        ))}
        {linked.length > 0 && level.also_titled?.length > 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Also checked {level.also_titled.join(", ")}: no elevation stated there.
          </Typography>
        )}
        {level.excluded_scope?.length > 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Not this building / area:{" "}
            {level.excluded_scope
              .map((x) => `${x.sheet || `p. ${x.page}`}${x.sheet_title ? ` (${titleCase(x.sheet_title)})` : ""}`)
              .join(", ")}
          </Typography>
        )}
        <ModelNote text={note} />
      </TableCell>
      <TableCell align="right" sx={{ width: "1%" }}>
        <Stack spacing={0.5} sx={{ alignItems: "flex-end" }}>
          {(level.occurrences?.length > 1 ? level.occurrences : [sourceItem]).map((o, i, all) => (
            <ViewPageButton
              key={i}
              item={{ ...o, mark: all.length > 1 ? `${level.name} (schedule part ${i + 1})` : level.name }}
              label={all.length > 1 ? `Part ${i + 1}` : "View level"}
              onView={onView}
            />
          ))}
        </Stack>
      </TableCell>
    </TableRow>
  );
}

const ELEVATION_STATUS = {
  read: { label: "read from note", color: "success" },
  derived: { label: "derived by note", color: "info" },
  unresolved: { label: "not established", color: "default" },
};

function PlanElevationRow({ item, onView }) {
  const badge = ELEVATION_STATUS[item.status];
  return (
    <TableRow sx={{ "& > td": { verticalAlign: "top" } }}>
      <TableCell>
        <Typography variant="body2" fontWeight={600}>{item.plan || "Plan"}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          {[item.sheet || `p. ${item.page}`, item.area && `at ${item.area.toLowerCase()}`].filter(Boolean).join(" · ")}
        </Typography>
      </TableCell>
      <TableCell>{surfaceLabel(item.surface)}</TableCell>
      <TableCell>
        <Typography variant="body2" fontWeight={600}>{item.value ? item.value.display : "—"}</Typography>
        {item.value?.raw && item.value.raw !== item.value.display && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>printed {item.value.raw}</Typography>
        )}
        <Chip size="small" variant="outlined" color={badge.color} label={badge.label} sx={{ mt: 0.5 }} />
      </TableCell>
      <TableCell>
        {item.status === "derived" && item.offset && (
          <Typography variant="body2">
            {item.inputs?.[0]?.text ? `${item.inputs[0].text} ` : ""}
            {item.offset.display.replace(/^-/, "")} {item.offset.direction} {item.offset.relative_to}
          </Typography>
        )}
        {item.status === "derived" && item.true_elevation && (
          <Typography variant="body2">True elevation {item.true_elevation.raw} (reference elevation note)</Typography>
        )}
        {item.rule && <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>“{item.rule}”</Typography>}
        {item.note && <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{item.note}</Typography>}
        {item.unless_noted && item.exceptions && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Unless noted otherwise{item.exceptions.notation ? ` thus ${item.exceptions.notation}…` : ""}:{" "}
            {item.exceptions.count} local value{item.exceptions.count === 1 ? "" : "s"} noted on this sheet.
          </Typography>
        )}
      </TableCell>
      <TableCell align="right" sx={{ width: "1%" }}>
        <Stack spacing={0.5} sx={{ alignItems: "flex-end" }}>
          {(item.inputs?.length ? item.inputs : [item.source]).map((source, i) => (
            <ViewPageButton key={i}
              item={{ ...source, mark: item.inputs?.length > 1
                ? (i === 0 ? "the value it is derived from" : "the offset note")
                : surfaceLabel(item.surface) }}
              label={item.inputs?.length > 1 ? (i === 0 ? "View value" : "View offset note") : "View note"}
              onView={onView} />
          ))}
        </Stack>
      </TableCell>
    </TableRow>
  );
}

function LevelBands({ bands }) {
  if (!bands?.length) return null;
  return (
    <Paper variant="outlined" sx={{ mb: 2, p: 1.5 }}>
      <Typography variant="subtitle2" fontWeight={700}>How the schedule's printed level labels read</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>
        Each level's name is printed above its line and its elevation below it, so the label between two
        lines joins the elevation of one level with the name of the next one down. Schedule rows keep that
        label exactly as printed.
      </Typography>
      {bands.map((b) => (
        <Typography key={`${b.schedule_id}-${b.printed}`} variant="body2" sx={{ mb: 0.25 }}>
          <Box component="span" sx={{ fontFamily: "monospace" }}>{b.printed}</Box> —{" "}
          {b.pairing === "unpaired" && (
            <>
              two levels: {b.upper.elevation} is {b.upper.name}; {b.lower.name} is at{" "}
              {b.lower.elevation || "an elevation the schedule does not print"}
            </>
          )}
          {b.pairing === "paired" && <>one level: {b.level.name} at {b.level.elevation_text}</>}
          {b.pairing === "ambiguous" && <>reads more than one way in this schedule; not attributed to a level</>}
          {b.schedule_rows > 0 ? ` · the label of ${b.schedule_rows} schedule row${b.schedule_rows === 1 ? "" : "s"}` : ""}
        </Typography>
      ))}
    </Paper>
  );
}

// The backend's level-conflict facts, with the level and plan match they
// refer to: both values, each with its own source. Nothing is derived here.
function levelConflicts(facts, levels) {
  const out = [];
  for (const fact of facts || []) {
    if (fact.type !== "level_conflict") continue;
    const level = (levels || []).find((l) => l.schedule_id === fact.refs?.schedule_id && l.name === fact.refs?.level);
    const match = level?.plan_matches?.find((m) => m.page === fact.refs?.plan_page);
    const value = match?.values.find((v) => v.compared);
    if (level && match && value) out.push({ level, match, value, difference: fact.difference_inches });
  }
  return out;
}

function LevelsAndElevations({ data, onView, schedules = [], notes = {} }) {
  const levels = data.schedule_levels || [];
  const groupOf = Object.fromEntries(schedules.map((s) => [s.id, s.material_group]));
  const bySchedule = [];
  for (const level of levels) {
    let group = bySchedule.find((g) => g.id === level.schedule_id);
    if (!group) {
      bySchedule.push((group = { id: level.schedule_id, name: level.schedule, items: [], material: groupOf[level.schedule_id] }));
    }
    group.items.push(level);
  }
  // Steel schedules first; a concrete / parking schedule's levels stay separate.
  const rank = { steel: 0, unclassified: 1, concrete: 2 };
  bySchedule.sort((a, b) => (rank[a.material] ?? 1) - (rank[b.material] ?? 1));
  return (
    <Section title="Levels and supported vertical extents">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Each schedule level with what the plans state for it in the same building or area. A plan is linked
        only by its title or datum note and its building / area — never because two elevations happen to be
        equal. Differing values are both shown. Elevations are read as printed; nothing is measured.
      </Typography>
      {bySchedule.map((group) => (
        <Paper key={group.id} variant="outlined" sx={{ mb: 2, overflow: "hidden" }}>
          <Stack direction="row" spacing={1} sx={{ px: 2, py: 1.25, bgcolor: "action.hover", alignItems: "baseline", flexWrap: "wrap" }}>
            <Typography variant="subtitle1" fontWeight={700}>Levels in {group.name}</Typography>
            {group.material === "concrete" && (
              <Typography variant="body2" color="text.secondary">concrete / parking schedule — kept separate</Typography>
            )}
          </Stack>
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small" aria-label={`Levels in ${group.name}`}>
              <TableHead>
                <TableRow>
                  <TableCell>Level</TableCell>
                  <TableCell>Elevation in schedule</TableCell>
                  <TableCell>Linked plan evidence</TableCell>
                  <TableCell align="right">Source</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {group.items.map((level, i) => (
                  <LevelRow key={`${level.name}-${i}`} level={level} onView={onView}
                    note={notes[`${level.schedule_id}|${level.name}`]} />
                ))}
              </TableBody>
            </Table>
          </Box>
        </Paper>
      ))}
    </Section>
  );
}

// Detailed level evidence, behind an expander: how printed band labels read,
// every elevation stated on plans, datum notes, notation legends, values
// noted on plans (with counts), grid-location offsets and legend examples.
// Distinct drawing occurrences are all kept, even when their values match.
function LevelEvidenceDetails({ data, onView }) {
  const [showAll, setShowAll] = useState(false);
  const elevations = data.plan_elevations || [];
  const shownElevations = showAll ? elevations : elevations.slice(0, COLLAPSED_ELEVATIONS);
  return (
    <Box>
      <LevelBands bands={data.level_bands} />
      {elevations.length > 0 && (
        <Paper variant="outlined" sx={{ mb: 2, overflow: "hidden" }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ px: 2, py: 1.25, bgcolor: "action.hover" }}>
            Elevations stated on plans
          </Typography>
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small" aria-label="Elevations stated on plans">
              <TableHead>
                <TableRow>
                  <TableCell>Plan / area</TableCell>
                  <TableCell>Surface</TableCell>
                  <TableCell>Elevation</TableCell>
                  <TableCell>How it is established</TableCell>
                  <TableCell align="right">Source</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {shownElevations.map((item, i) => (
                  <PlanElevationRow key={i} item={item} onView={onView} />
                ))}
              </TableBody>
            </Table>
          </Box>
          {elevations.length > COLLAPSED_ELEVATIONS && (
            <Box sx={{ px: 1.5, pb: 1 }}>
              <Button size="small" onClick={() => setShowAll(!showAll)}>
                {showAll ? "Show fewer" : `Show all ${elevations.length}`}
              </Button>
            </Box>
          )}
        </Paper>
      )}
      {(data.datums?.length > 0 || data.noted_on_plans?.length > 0) && (
        <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
          {data.datums?.map((d, i) => (
            <Stack key={`d${i}`} direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5, flexWrap: "wrap" }}>
              <Typography variant="body2">
                <b>Datum</b> ({d.sheet || `p. ${d.page}`}): {d.relation}
              </Typography>
              <ViewPageButton item={{ ...d.source, mark: "datum note" }} label="View plan note" onView={onView} />
            </Stack>
          ))}
          {data.noted_on_plans?.map((g) => {
            const read = g.examples.filter((e) => e.status !== "flagged");
            const flagged = g.examples.filter((e) => e.status === "flagged");
            return (
              <Box key={`v${g.page}`} sx={{ mb: 0.5 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                  <Typography variant="body2">
                    {g.sheet || `p. ${g.page}`}: {g.count} value{g.count === 1 ? "" : "s"} noted on plan ({g.meaning.join(", ")})
                    {read.length ? ` — e.g. ${read.slice(0, 3).map((e) => e.text).join("; ")}` : ""}
                    {g.rule_sheets?.length > 0 ? ` · notation defined on ${g.rule_sheets.join(", ")}` : ""}
                  </Typography>
                  {read[0] && (
                    <ViewPageButton item={{ ...read[0], mark: read[0].value }} label="View example" onView={onView} />
                  )}
                </Stack>
                {flagged.map((e, i) => (
                  <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", pl: 2 }}>
                    <Chip size="small" variant="outlined" color="warning" label="flagged" />
                    <Typography variant="caption">
                      Printed <Box component="span" sx={{ fontFamily: "monospace" }}>{e.value}</Box> — {e.flag}; reads
                      as {e.candidate} if completed. Kept as a candidate, not used as an elevation.
                    </Typography>
                    <ViewPageButton item={{ ...e, mark: `${e.value} (flagged ${i + 1})` }} label="View" onView={onView} />
                  </Stack>
                ))}
              </Box>
            );
          })}
        </Paper>
      )}
    </Box>
  );
}

// Bracketed values that are not elevations: a grid's offset inside a printed
// location, and a legend's own example. Each occurrence keeps its source.
function NonElevationBrackets({ offsets, examples, onView }) {
  if (!offsets?.length && !examples?.length) return null;
  return (
    <Box sx={{ mt: 1 }}>
      {offsets?.length > 0 && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="body2">
            Bracketed values inside grid locations are offsets of that grid, not elevations — the legend's
            bracket notation does not apply to them:
          </Typography>
          <Stack spacing={0.5} sx={{ mt: 0.5, pl: 1 }}>
            {offsets.map((o, i) => (
              <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                <Typography variant="body2">
                  <Box component="span" sx={{ fontFamily: "monospace", userSelect: "all" }}>{o.location}</Box>
                  {" — "}grid {o.grid} offset <Dim raw={o.offset.raw} /> (direction not stated) · {o.sheet || `p. ${o.page}`}
                </Typography>
                <ViewPageButton item={{ ...o, mark: o.location }} label="View location" onView={onView} />
              </Stack>
            ))}
          </Stack>
        </Box>
      )}
      {examples?.length > 0 && (
        <Typography variant="body2" color="text.secondary">
          Legend examples, not project values:{" "}
          {examples.map((e) => `${e.text} (${e.sheet || `p. ${e.page}`})`).join("; ")}
        </Typography>
      )}
    </Box>
  );
}

// One source page of the uploaded PDF with its box highlighted (pdf.js loads lazily).
function SourcePdf({ documentId, source, selectionKey }) {
  return (
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
        selection={{ key: selectionKey, pageNumber: source.page, boundingBox: source.bbox || null }}
      />
    </Suspense>
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
        <SourcePdf documentId={documentId} source={target} selectionKey={`${target.id || target.mark || "source"}-${target.page}`} />
      </DialogContent>
    </Dialog>
  );
}

// A framing key's callout parts, each with the printed label its leader ends
// at. A part with no leader to a label is said to be undefined, not guessed.
function FramingKeyParts({ parts }) {
  return (
    <Box component="dl" sx={{ m: 0, mt: 0.5, pl: 1, display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1.5, rowGap: 0.25 }}>
      {(parts || []).map((part) => (
        <Box key={part.token} sx={{ display: "contents" }}>
          <Typography component="dt" variant="body2" sx={{ fontFamily: "monospace" }}>{part.token}</Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0 }}>
            {part.status === "defined"
              ? `${part.meaning.charAt(0) + part.meaning.slice(1).toLowerCase()} (label at the end of its leader)`
              : part.status === "conflicting"
                ? "Two labels at its leaders — not decoded"
                : "No leader to a printed label — not decoded"}
          </Typography>
        </Box>
      ))}
      <Typography variant="caption" color="text.secondary" sx={{ gridColumn: "1 / -1" }}>
        The key's numbers are an example, not a count of anything.
      </Typography>
    </Box>
  );
}

function InterpretationRules({ rules, notes, onView, title = "Rules affecting interpretation", children }) {
  const [open, setOpen] = useState(false);
  const shown = open ? rules : rules.slice(0, COLLAPSED_RULES);
  return (
    <Section title={title}>
      <Stack spacing={0.75}>
        {shown.map((rule) => (
          <Box key={rule.id}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", flexWrap: "wrap" }}>
              <Chip size="small" variant="outlined" label={RULE_LABEL[rule.relation] || rule.relation} />
              <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
                {rule.kind === "framing_key" ? `In a beam callout such as ${rule.source_text}:` : rule.text}
              </Typography>
            </Stack>
            {rule.kind === "framing_key" && <FramingKeyParts parts={rule.parts} />}
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
      {children}
    </Section>
  );
}

// What an estimator must check before relying on the summary: sources that
// disagree (both values, side by side), items the drawing leaves open, and
// plates whose dimensions could not be linked. Nothing here is resolved.
function NeedsAttention({ conflicts = [], items = [], plateIssues = [], notes = {}, onView, onCompare }) {
  if (!conflicts.length && !items.length && !plateIssues.length) return null;
  return (
    <Section title="Items needing attention">
      <Stack spacing={1.25}>
        {conflicts.map((c) => (
          <Box key={`${c.level.schedule_id}-${c.level.name}-${c.match.page}`}>
            <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
              {c.level.name} — {c.level.schedule}
            </Typography>
            <ConflictComparison {...c} onView={onView} onCompare={onCompare} />
            <ModelNote text={notes[`${c.level.schedule_id}|${c.level.name}`]} />
          </Box>
        ))}
        {items.length > 0 && (
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
        )}
        {plateIssues.length > 0 && (
          <Typography variant="body2" color="warning.main">
            Plate not established for {plateIssues.length} schedule entr{plateIssues.length === 1 ? "y" : "ies"}:{" "}
            {plateIssues.slice(0, 6).map(columnLabel).join(", ")}
            {plateIssues.length > 6 ? ", …" : ""} — see the column schedule.
          </Typography>
        )}
      </Stack>
    </Section>
  );
}

// Two sources side by side, each on its own page with its own highlight.
function CompareSourcesDialog({ documentId, pair, onClose }) {
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("md"));
  if (!pair) return null;
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xl" fullScreen={fullScreen} aria-labelledby="summary-compare-title">
      <DialogTitle id="summary-compare-title" sx={{ pr: 6 }}>Compare sources</DialogTitle>
      <IconButton aria-label="Close comparison" onClick={onClose} sx={{ position: "absolute", right: 8, top: 8 }}>
        <CloseOutlined />
      </IconButton>
      <DialogContent dividers sx={{ p: 0 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, height: fullScreen ? "100%" : "78vh" }}>
          {pair.map((source, i) => (
            <Box key={i} sx={{ display: "flex", flexDirection: "column", minHeight: 320, borderLeft: i ? 1 : 0, borderColor: "divider" }}>
              <Typography variant="body2" fontWeight={600} sx={{ px: 1.5, py: 0.75 }}>
                {source.mark} — {whereLabel(source)}
              </Typography>
              <Box sx={{ flex: 1, minHeight: 0 }}>
                <SourcePdf documentId={documentId} source={source} selectionKey={`compare-${i}-${source.page}`} />
              </Box>
            </Box>
          ))}
        </Box>
      </DialogContent>
    </Dialog>
  );
}

function Section({ title, source, children }) {
  return (
    <Box component="section" sx={{ mb: 2.5 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
        <Typography variant="subtitle1" component="h3" fontWeight={700} sx={{ display: "block" }}>
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
  const [comparePair, setComparePair] = useState(null);
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

  const columnSchedule = di?.column_schedule;
  const columnEntries = columnSchedule?.entries || [];
  const hasColumnSchedule = columnEntries.length > 0;
  const columnSchedules = columnSchedule?.schedules || [];
  // Steel first; a schedule a note makes concrete (parking precast) is
  // supporting information, not part of the steel overview.
  const steelSchedules = columnSchedules.filter((s) => s.material_group !== "concrete");
  const concreteSchedules = columnSchedules.filter((s) => s.material_group === "concrete");
  const levels = di?.levels;
  const scheduleLevels = levels?.schedule_levels || [];
  const levelsBySchedule = scheduleLevels.reduce((acc, level) => {
    (acc[level.schedule_id] = acc[level.schedule_id] || []).push(level);
    return acc;
  }, {});
  const hasLevels = scheduleLevels.length > 0;
  const hasLevelDetails = Boolean(
    levels && ["plan_elevations", "datums", "noted_on_plans", "level_bands"].some((key) => levels[key]?.length),
  );
  // Column marks the column schedule already shows (with plates and notes).
  const scheduledColumns = new Set(
    columnEntries.filter((e) => e.mark).map((e) => `${e.page}|${e.mark}`),
  );
  const allDefinitions = (di?.definitions || []).filter(
    (d) => !(d.component === "column" && scheduledColumns.has(`${d.page}|${d.mark}`)),
  );
  // Concrete / non-steel marks (walls, piers, footings) belong with the
  // supporting schedules; their data and sources stay one click away.
  const nonSteel = (d) => d.status === "not steel" || d.status === "precast" || d.status === "no steel";
  const definitions = allDefinitions.filter((d) => !nonSteel(d));
  const supportingDefinitions = allDefinitions.filter(nonSteel);
  const interpretationRules = di?.interpretation_rules || [];
  const unresolved = di?.unresolved || [];
  const conflicts = levelConflicts(di?.facts, scheduleLevels);
  const steelIds = new Set(steelSchedules.map((s) => s.id));
  const plateIssues = columnEntries.filter((e) => steelIds.has(e.schedule_id) && PLATE_NEEDS_REVIEW.has(e.plate?.status));
  const notations = levels?.notations || [];
  const hasEvidence =
    allDefinitions.length > 0 ||
    hasColumnSchedule ||
    hasLevels ||
    interpretationRules.length > 0 ||
    unresolved.length > 0;
  // Model notes only ever annotate an evidence record (validated server-side);
  // facts carry what they describe, so a note lands on that card.
  const facts = Object.fromEntries((di?.facts || []).map((f) => [f.id, f]));
  const modelNotes = {};
  for (const n of [...(di?.summary_llm?.key_facts || []), ...(di?.summary_llm?.cautions || [])]) {
    const refs = facts[n.id]?.refs;
    if (refs?.column_entry) modelNotes[refs.column_entry] = n.why;
    else if (refs?.level) modelNotes[`${refs.schedule_id}|${refs.level}`] = n.why;
    else modelNotes[n.id] = n.why;
  }

  const hasNarrative = Boolean(narrative);
  const hasRules = rules.length > 0 || (profile.abbreviation_rules || []).length > 0;

  if (!hasNarrative && !hasRules && !statusMessage) return null;

  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2.5 } }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", mb: 0.5, flexWrap: "wrap" }}>
        <Typography variant="subtitle1" component="h2" fontWeight={700}>
          What Estima3D read from this drawing set
        </Typography>
        {method === "llm_enhanced" && (
          <Typography variant="caption" color="text.secondary">overview wording by model, checked against the drawing</Typography>
        )}
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, display: "block" }}>
        Compiled from the extracted pages, notes and schedules. Informational only — it does not change any
        predicted section or takeoff quantity, and it never uses the ground-truth Excel. “Read from drawing” means
        read as printed, not verified or approved.
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
          {/* A. Short project orientation */}
          <Section title="Project orientation">
            <Typography variant="body1">{narrative.project_overview}</Typography>
          </Section>

          {/* B. Items needing attention */}
          <NeedsAttention
            conflicts={conflicts}
            items={unresolved}
            plateIssues={plateIssues}
            notes={modelNotes}
            onView={onView}
            onCompare={documentId ? setComparePair : null}
          />

          {/* C. Steel column schedules and plate assignments */}
          {steelSchedules.length > 0 && (
            <ColumnSchedules
              data={columnSchedule}
              schedules={steelSchedules}
              title="Steel column schedules and plate assignments"
              intro="Each row is one schedule entry: its location, section and base plate, with the sheet each value was read from. Open Details for the plate's roles, the evidence chain and the levels it is drawn between. A schedule entry is a definition, not an installed column."
              onView={onView}
              documentId={documentId}
              levelsBySchedule={levelsBySchedule}
              notes={modelNotes}
            />
          )}
          {definitions.length > 0 && (
            <MarksAndDefinitions definitions={definitions} notes={modelNotes} onView={onView}
              title="Steel marks and definitions" />
          )}

          {/* D. Levels and supported vertical extents */}
          {hasLevels && (
            <LevelsAndElevations data={levels} onView={onView} schedules={columnSchedules} notes={modelNotes} />
          )}

          {/* E. Drawing notation and interpretation rules */}
          {(interpretationRules.length > 0 || notations.length > 0 || levels?.location_offsets?.length > 0) && (
            <InterpretationRules
              rules={interpretationRules}
              notes={modelNotes}
              onView={onView}
              title="Drawing notation and interpretation rules"
            >
              {notations.length > 0 && (
                <Box sx={{ mt: 1 }}>
                  {notations.map((n, i) => (
                    <Stack key={`n${i}`} direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5, flexWrap: "wrap" }}>
                      <Typography variant="body2">
                        <Box component="span" sx={{ fontFamily: "monospace" }}>{n.sample}</Box> on a plan means {n.meaning}
                        {n.relative_to ? `, measured from the ${n.relative_to}` : ""} ({n.scope}, {n.sheet || `p. ${n.page}`})
                      </Typography>
                      <ViewPageButton item={{ ...n.source, mark: n.sample }} label="View note" onView={onView} />
                    </Stack>
                  ))}
                </Box>
              )}
              <NonElevationBrackets offsets={levels?.location_offsets} examples={levels?.legend_examples} onView={onView} />
            </InterpretationRules>
          )}

          {/* F. Supporting schedules and detailed extraction evidence */}
          {(concreteSchedules.length > 0 || supportingDefinitions.length > 0 || hasLevelDetails) && (
            <Accordion disableGutters elevation={0} variant="outlined" sx={{ mt: 1 }}>
              <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
                <Typography variant="body2" fontWeight={600}>
                  Supporting schedules and level evidence
                  {concreteSchedules.length > 0 && ` · ${concreteSchedules.map((s) => s.name).join(", ")}`}
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                {concreteSchedules.length > 0 && (
                  <ColumnSchedules
                    data={columnSchedule}
                    schedules={concreteSchedules}
                    title="Concrete / parking column schedules"
                    intro="Kept apart from the steel: the schedule's own note states the material of the labels it names. Labels the note does not name show their printed text only."
                    onView={onView}
                    documentId={documentId}
                    levelsBySchedule={levelsBySchedule}
                    notes={modelNotes}
                  />
                )}
                {supportingDefinitions.length > 0 && (
                  <MarksAndDefinitions
                    definitions={supportingDefinitions}
                    notes={modelNotes}
                    onView={onView}
                    title="Concrete and other non-steel schedules"
                    intro="Each printed cell is shown under its own heading. Equal values in two columns are two values."
                  />
                )}
                {hasLevelDetails && (
                  <Section title="Level evidence details">
                    <LevelEvidenceDetails data={levels} onView={onView} />
                  </Section>
                )}
              </AccordionDetails>
            </Accordion>
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
      <CompareSourcesDialog documentId={documentId} pair={comparePair} onClose={() => setComparePair(null)} />
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
