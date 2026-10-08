import { useEffect, useRef, useState } from "react";
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
  InputAdornment,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { CloseOutlined, ExpandMoreOutlined, PrintOutlined, SearchOutlined } from "@mui/icons-material";
import { getColumnTrace } from "../api/client";
import { formatPlate, formatPrintedSize } from "../lib/dimensions";
import {
  completenessText,
  directoryRows,
  printedRowsText,
  ScheduleDirectory,
  supportingGroupsOf,
  supportingRowsOf,
} from "./drawingSummary/directory";
import EngineeringIntelligence from "./drawingSummary/EngineeringIntelligence";
import { LevelReview, reviewSourcesText } from "./drawingSummary/levelReview";
import { LocateButton, LocateDialog, LocationProvider, locateSources, PlanPreview, useLocation } from "./drawingSummary/locate";
import { SourcePdf } from "./drawingSummary/pdf";
import SheetIndex from "./drawingSummary/SheetIndex";
import { pagesLabel, sourceIdentity, ViewPageButton, whereLabel } from "./drawingSummary/sources";
import {
  ConflictComparison,
  Dim,
  EvidenceChain,
  LevelDiagram,
  NUMERIC,
  PlateRoles,
  StatusText,
} from "./drawingSummary/visuals";

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

// The app theme sizes body text for dense tool pages; the summary is read,
// so its text sits at 14 px (secondary 12.5 px) and table headings in
// sentence case. Scoped to this panel only.
const SUMMARY_TYPE = {
  "& .MuiTypography-body1": { fontSize: "1rem" },
  "& .MuiTypography-body2, & .MuiTableCell-body": { fontSize: "0.875rem" },
  "& .MuiTypography-caption": { fontSize: "0.78rem" },
  "& .MuiTableCell-head": { fontSize: "0.78rem", textTransform: "none", letterSpacing: 0 },
  "& .MuiButton-sizeSmall": { fontSize: "0.8125rem" },
};

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

// A printed cell's full heading: REINFORCEMENT > TOP > SHORT WAY reads
// "Reinforcement · Top · Short Way" (older profiles: heading under its group).
function cellLabel(cell) {
  if (cell.path?.length) return cell.path.map(titleCase).join(" · ");
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
          {[schedule, common, `${items.length} mark${items.length === 1 ? "" : "s"}`].filter(Boolean).join(" · ")}
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
        // A printed title already names the schedule ("Concrete Wall Schedule").
        schedule: item.schedule_title ? null : item.schedule,
        items: [],
      };
      groups.push(group);
    }
    group.items.push(item);
  }
  const content = (
    <>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {intro ||
          "Each row says how to read that mark where it appears on a plan. A schedule row is a definition, not an installed member — it is never a quantity."}
      </Typography>
      {groups.map(({ key, ...g }) => (
        <DefinitionGroup key={key} {...g} notes={notes} onView={onView} compact={compact} />
      ))}
    </>
  );
  return title ? <Section title={title}>{content}</Section> : content;
}

// Column schedules: one row per schedule column -- its section, the printed
// location(s), the base plate and notes, each with where it was read.
// Definitions only: a listed location is never a takeoff quantity.
const COLLAPSED_COLUMNS = 8;
// A schedule this short is shown whole: hiding a few rows behind "Show all"
// hides real coverage (OSSE's later D / R locations).
const SHOW_WHOLE_UP_TO = 30;

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
      return { main: "—", sub: plate.note || "Not given in this schedule" };
    default:
      return { main: plate.printed || "—", sub: plate.note || "Could not be read" };
  }
}

function columnLabel(entry) {
  if (entry.mark) return entry.mark;
  const [first, ...rest] = entry.locations || [];
  if (!first) return entry.location_text || "—";
  return rest.length ? `${first.raw} +${rest.length}` : first.raw;
}

// Level names as the reader says them: "T.O. SLAB LEVEL 1" -> "Level 1".
function shortLevel(name) {
  return titleCase(String(name || "").replace(/^\s*(?:T\.?\s*O\.?|TOP OF)\s+(?:SLAB\s+|STEEL\s+|DECK\s+)?/i, "")) || name;
}

const plateHasDims = (plate) => ["read", "resolved"].includes(plate?.status) && plate.dimensions?.length > 0;

// "Level 1 to Roof" when the schedule draws both ends on level lines.
function extentLabel(extent) {
  const both = extent && ["top", "bottom"].every((k) => extent[k]?.position === "at");
  return both ? `${shortLevel(extent.bottom.line.name)} to ${shortLevel(extent.top.line.name)}` : null;
}

// "18" × 24" · 6-#8 · #3@12" O.C." -- a linked definition row's printed cells.
const definitionCells = (definition) => (definition?.cells || []).filter((c) => c.text)
  .map((c) => `${(c.path || [c.heading]).slice(-1)[0].toLowerCase()} ${c.text}`).join(" · ");

// A label printed on the column (pier P1, concrete RC1) and the supporting
// row that defines the same mark; differing sizes are both shown.
function DefinitionLink({ label, definition, onView }) {
  return (
    <>
      {label}
      {definition && (
        <Typography component="span" variant="caption" color={definition.sizes === "differ" ? "warning.main" : "text.secondary"}
          sx={{ display: "block" }}>
          {definition.mark} in the {titleCase(definition.schedule_title)}: {definitionCells(definition)}
          {definition.sizes === "differ" ? " — sizes differ from the label; both are kept" : ""}
          {" "}
          <ViewPageButton item={{ ...definition, mark: `${definition.mark} definition` }} label={definition.sheet || "View"}
            onView={onView} />
        </Typography>
      )}
    </>
  );
}

// One column as an estimator reads it: location, section, plate and its
// dimensions, the levels the schedule draws it between, and the difference
// of those two printed elevations -- which is not a member length.
function ColumnCard({ entry, onView }) {
  const plate = entry.plate || {};
  const section = entry.sections?.find((s) => s.designation)?.designation || entry.sections?.[0]?.printed;
  const diff = entry.level_difference;
  const extent = extentLabel(entry.extent);
  const offsets = (entry.locations || []).flatMap((l) =>
    (l.grids || []).filter((g) => g.offset).map((g) => `${g.offset.raw} from grid ${g.label}`));
  const dims = plateHasDims(plate) ? formatPlate(plate.dimensions) : null;
  const rows = [
    ["Location", (
      <>
        <Box component="span" sx={{ fontFamily: "monospace", userSelect: "all" }}>{entry.location_text || columnLabel(entry)}</Box>
        {offsets.length > 0 && (
          <Typography component="span" variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Offset {offsets.join(", ")} — the printed sign is not a direction on the sheet
          </Typography>
        )}
      </>
    )],
    ["Section", entry.definition
      ? <DefinitionLink label={section} definition={entry.definition} onView={onView} />
      : section ? <Box component="span" sx={{ userSelect: "all" }}>{section}</Box> : "—"],
  ];
  if (entry.material?.status !== "read" || plate.status !== "not_shown") {
    rows.push(["Base plate", plate.printed || plateSummary(plate).main]);
    rows.push(["Dimensions", dims ? (
      <>
        <Box component="span" aria-label={dims.spoken} sx={{ ...NUMERIC, fontWeight: 600 }}>{dims.text}</Box>
        <Typography component="span" variant="caption" color="text.secondary" sx={{ display: "block" }}>{dims.roles}</Typography>
      </>
    ) : PLATE_STATUS_TEXT[plate.status] || "Not established"]);
  }
  for (const support of entry.supports || []) {
    rows.push(["Printed below", <DefinitionLink key={support.printed} label={support.printed} definition={support.definition}
      onView={onView} />]);
  }
  if (entry.extent) {
    rows.push(["Supported levels", extent || "Ends not established"]);
  } else if (entry.extent_note) {
    rows.push(["Vertical extent", entry.extent_note]);
  }
  if (diff?.status === "computed") {
    rows.push(["Elevation difference", (
      <>
        <Dim inches={diff.inches} strong />
        <Typography component="span" variant="caption" color="text.secondary" sx={{ display: "block" }}>
          Calculated from the two printed level elevations
        </Typography>
      </>
    )]);
  }
  if (entry.extent || entry.extent_note) rows.push(["Fabricated length", "Unconfirmed"]);
  return (
    <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "minmax(8rem, auto) 1fr", columnGap: 2, rowGap: 0.75 }}>
      {rows.map(([label, value]) => (
        <Box key={label} sx={{ display: "contents" }}>
          <Typography component="dt" variant="body2" color="text.secondary">{label}</Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0, minWidth: 0, wordBreak: "break-word" }}>{value}</Typography>
        </Box>
      ))}
    </Box>
  );
}

function ColumnEntryDetails({ entry, onView, documentId, levels, note, scheduleName, scopeId, onLocate }) {
  const plate = entry.plate;
  const locations = entry.locations || [];
  const single = entry.key_role === "location" && locations.length === 1 && locations[0].status === "parsed"
    ? locations[0].raw : null;
  // The plan views "Locate on plan" found join the schedule and plate sources,
  // so the source viewer can switch between all of them.
  const { result } = useLocation(documentId, single, scopeId, Boolean(single));
  // A multi-location entry has no single intersection: its traced plan views are the sources.
  const [tracedSources, setTracedSources] = useState([]);
  const planSources = single ? locateSources(result, single) : tracedSources;
  const listLocations = entry.key_role === "location"
    && (locations.length > 1 || locations.some((l) => l.status !== "parsed") || entry.repeated_label || entry.label_conflict);
  const bothEnds = extentLabel(entry.extent);
  return (
    <Stack spacing={1.5} sx={{ py: 1.5, px: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
      <ColumnCard entry={entry} onView={onView} />
      <EvidenceChain entry={entry} onView={onView} planSources={planSources} />
      {single && <PlanPreview documentId={documentId} location={single} scheduleId={scopeId} onOpen={onLocate} />}
      {entry.extent && levels?.length > 1 && (
        <LevelDiagram levels={levels} extent={entry.extent} scheduleName={scheduleName} />
      )}
      <ModelNote text={note} />
      {listLocations && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Location text as printed
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-word", userSelect: "all" }}>
            {entry.location_text}
          </Typography>
          <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
            {locations.map((location) => (
              <Typography component="li" variant="body2" key={location.raw}>
                {location.status === "parsed" ? (
                  <>
                    Grid {location.grids.map((g) => g.label).join(" and grid ")}{" "}
                    <LocateButton location={location.raw} onLocate={onLocate} />
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
      )}
      {entry.key_role !== "location" && entry.location_note && <Typography variant="body2">{entry.location_note}</Typography>}
      {(!plate.via?.length || plate.status === "not_shown") && plate.note && (
        <Typography variant="body2" color="text.secondary">{plate.note}</Typography>
      )}
      {plate.status === "reference" && (
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
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
        <Typography variant="caption" color="text.secondary">
          Printed with the note marker {plate.markers.join(" ")} — check the schedule notes.
        </Typography>
      )}
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
      {entry.extent && !bothEnds && <ColumnExtent entry={entry} />}
      {documentId && !entry.assignment_only && (
        <ColumnTrace entry={entry} documentId={documentId} onView={onView} onTraced={setTracedSources} />
      )}
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
            {formatPrintedSize(material.size.raw)} column section
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
        <Typography variant="caption" color="text.secondary">
          {entry.definition ? `Defined in the ${titleCase(entry.definition.schedule_title)}` : "Printed text; no catalog section"}
        </Typography>
      )}
    </Box>
  ));
}

// The plate mark (or what stands in its place). An ordinary linked plate is
// just its mark; only states that change how the row is read get a line.
function PlateCell({ plate, onPlate }) {
  if (plateHasDims(plate)) {
    if (!plate.printed) return <Typography variant="body2" color="text.secondary">As printed</Typography>;
    return onPlate ? (
      <Button size="small" onClick={() => onPlate(plate.printed)} aria-label={`Plate mark ${plate.printed}: roles, source and locations`}
        sx={{ px: 0.75, minWidth: 0, fontFamily: "monospace", fontWeight: 700, fontSize: "0.875rem" }}>
        {plate.printed}
      </Button>
    ) : (
      <Typography variant="body2" fontWeight={700} sx={{ fontFamily: "monospace" }}>{plate.printed}</Typography>
    );
  }
  const summary = plateSummary(plate);
  return (
    <Box>
      <Typography variant="body2" fontWeight={plate.status === "not_shown" ? 400 : 600}>{summary.main}</Typography>
      <Typography variant="caption"
        color={PLATE_NEEDS_REVIEW.has(plate.status) ? "warning.main" : "text.secondary"} sx={{ display: "block" }}>
        {PLATE_STATUS_TEXT[plate.status] || "Not established"}
      </Typography>
    </Box>
  );
}

// Width × Length × Thickness, or a dash: an unresolved plate is never forced
// into the numeric template.
function PlateDimsCell({ plate }) {
  if (!plateHasDims(plate)) return <Typography variant="body2" color="text.secondary" aria-label="Not established">—</Typography>;
  const dims = formatPlate(plate.dimensions);
  return (
    <Typography variant="body2" fontWeight={600} aria-label={dims.spoken} title={dims.roles} sx={NUMERIC}>
      {dims.text}
    </Typography>
  );
}

const entryNotes = (entry) => [
  ...(entry.notes || []),
  ...(entry.other_plates || []).map((p) => `${p.type}: ${dimensionsText(p)} (schedule note)`),
];

// The printed location: one "Locate" per listed location (each is its own
// intersection); a mark (C-1) is never treated as a grid location.
function LocationCell({ entry, onLocate }) {
  const parsed = (entry.locations || []).filter((l) => l.status === "parsed");
  const several = entry.key_role === "location" && parsed.length > 1;
  return (
    <>
      <Typography variant="body2" fontWeight={700} sx={{ fontFamily: "monospace", userSelect: "text" }}>
        {columnLabel(entry)}
      </Typography>
      {entry.assignment_only && <Typography variant="caption" color="text.secondary">table only · no levels</Typography>}
      {entry.listed_location_count > 1 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          {entry.listed_location_count} locations
        </Typography>
      )}
      {several && onLocate && (
        <Stack spacing={0} sx={{ alignItems: "flex-start" }}>
          {parsed.map((location) => (
            <LocateButton key={location.raw} location={location.raw} onLocate={onLocate} compact />
          ))}
        </Stack>
      )}
    </>
  );
}

function ColumnEntryRow({ entry, onView, documentId, levels, note, scheduleName, showNotes, onPlate, open, onToggle,
  concrete, scopeId, onLocate }) {
  const label = columnLabel(entry);
  const single = entry.key_role === "location" && entry.locations?.length === 1 && entry.locations[0].status === "parsed";
  const columns = concrete ? 4 : showNotes ? 6 : 5;
  return (
    <>
      <TableRow sx={{ "& > td": { borderBottom: open ? 0 : undefined, verticalAlign: "top" } }}>
        <TableCell>
          <LocationCell entry={entry} onLocate={onLocate} />
        </TableCell>
        <TableCell>
          <SectionCell entry={entry} />
        </TableCell>
        {concrete ? (
          <TableCell>
            {entry.definition ? (
              <Typography variant="body2">{definitionCells(entry.definition)}</Typography>
            ) : (
              <Typography variant="body2" color="text.secondary" aria-label="No linked definition">—</Typography>
            )}
          </TableCell>
        ) : (
          <>
            <TableCell>
              <PlateCell plate={entry.plate} onPlate={onPlate} />
            </TableCell>
            <TableCell>
              <PlateDimsCell plate={entry.plate} />
            </TableCell>
          </>
        )}
        {!concrete && showNotes && (
          <TableCell>
            {entryNotes(entry).map((n) => (
              <Typography key={n} variant="body2" color="text.secondary">{n}</Typography>
            ))}
          </TableCell>
        )}
        <TableCell align="right" sx={{ width: "1%", whiteSpace: "nowrap" }}>
          <Stack direction="row" spacing={0.5} sx={{ justifyContent: "flex-end" }}>
            {single && <LocateButton location={entry.locations[0].raw} onLocate={onLocate} />}
            <ViewPageButton item={{ ...entry, mark: label }} label={entry.assignment_only ? "Table row" : "Schedule"}
              onView={onView} />
            <Button
              size="small"
              onClick={onToggle}
              aria-expanded={open}
              aria-label={`${open ? "Hide" : "Show"} details for ${label}`}
            >
              {open ? "Hide" : "Details"}
            </Button>
          </Stack>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={columns} sx={{ py: 0, borderBottom: open ? undefined : 0 }}>
          <Collapse in={open} unmountOnExit>
            <Box sx={{ pb: 1.5 }}>
              <ColumnEntryDetails key={`${documentId}-${entry.id}`} entry={entry} onView={onView} documentId={documentId}
                levels={levels} note={note} scheduleName={scheduleName} scopeId={scopeId} onLocate={onLocate} />
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

function ColumnScheduleBlock({ schedule, entries, total, filtered, onView, documentId, levels, notes = {}, onPlate,
  onLocate, scopeName }) {
  const [open, setOpen] = useState(false);
  const [expandedEntries, setExpandedEntries] = useState({});
  const concrete = schedule.material_group === "concrete";
  const collapsible = !filtered && entries.length > SHOW_WHOLE_UP_TO;
  const shown = open || !collapsible ? entries : entries.slice(0, COLLAPSED_COLUMNS);
  const where = whereLabel({ sheet: schedule.sheets.filter(Boolean).join(", "), pages: schedule.pages });
  const showNotes = entries.some((e) => entryNotes(e).length > 0);
  const scopeId = schedule.scope_schedule_id || schedule.id;
  const locate = onLocate && ((location) => onLocate(location, scopeId));
  return (
    <Paper variant="outlined" sx={{ mb: 2, overflow: "hidden", scrollMarginTop: 72 }} id={`summary-schedule-${schedule.id}`}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ px: 2, py: 1.25, alignItems: "center", flexWrap: "wrap", bgcolor: "action.hover" }}
      >
        <Typography variant="subtitle1" fontWeight={700}>{schedule.name}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
          {[
            where,
            schedule.source === "location_table" ? "location table" : schedule.layout === "graphical" ? "graphical schedule" : "table",
            schedule.block_count > 1 ? `printed in ${schedule.block_count} parts` : "",
            `${total} printed entr${total === 1 ? "y" : "ies"}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </Typography>
        <ViewPageButton item={{ ...schedule, mark: schedule.name }}
          label={schedule.source === "location_table" ? "View table" : "View column schedule"} onView={onView} />
      </Stack>
      {(schedule.notes.length > 0 || schedule.hidden_text.length > 0 || schedule.source === "location_table") && (
        <Box sx={{ px: 2, pt: 1 }}>
          {schedule.source === "location_table" && (
            <Typography variant="body2" color="text.secondary">
              These locations are listed only in this table, which assigns a section and a base plate; no column schedule
              prints them and no levels are given.{schedule.scope_basis && scopeName
                ? ` Looked for on the plans of ${scopeName}: ${schedule.scope_basis}.` : ""}
            </Typography>
          )}
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
      {entries.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ px: 2, py: 1.5 }}>No location in this schedule matches.</Typography>
      ) : (
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small" aria-label={`${schedule.name} columns`}>
            <TableHead>
              <TableRow>
                <TableCell>{schedule.key_role === "location" ? "Location" : "Mark"}</TableCell>
                <TableCell>{concrete ? "Section / label" : "Section"}</TableCell>
                {concrete ? <TableCell>Linked definition</TableCell> : (
                  <>
                    <TableCell>Base plate</TableCell>
                    <TableCell>Plate — W × L × T</TableCell>
                  </>
                )}
                {!concrete && showNotes && <TableCell>Notes</TableCell>}
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {shown.map((entry) => (
                <ColumnEntryRow key={entry.id} entry={entry} onView={onView} documentId={documentId} levels={levels}
                  note={notes[entry.id]} scheduleName={schedule.name} showNotes={showNotes} concrete={concrete}
                  open={Boolean(expandedEntries[entry.id])} scopeId={scopeId} onLocate={locate}
                  onToggle={() => setExpandedEntries((previous) => ({ ...previous, [entry.id]: !previous[entry.id] }))}
                  onPlate={onPlate && ((mark) => onPlate(schedule, mark))} />
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
      {collapsible && (
        <Stack direction="row" spacing={1} sx={{ px: 2, py: 1, alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="body2" color="text.secondary" role="status">
            {open ? `All ${entries.length} printed entries shown` : `Showing ${COLLAPSED_COLUMNS} of ${entries.length} printed entries — the search covers all of them`}
          </Typography>
          <Button size="small" onClick={() => setOpen(!open)}>
            {open ? "Show fewer" : `Show all ${entries.length}`}
          </Button>
        </Stack>
      )}
    </Paper>
  );
}

// Spacing and case are ignored; primes, decimals and offsets are kept, so
// "c.8 - 8.9" finds C.8-8.9 but C.8' is not C.8.
const normalizeLocation = (text) => String(text || "").replace(/\s+/g, "").toUpperCase();

function entryMatches(entry, query) {
  const q = normalizeLocation(query);
  if (!q) return true;
  return [entry.mark, entry.location_text, ...(entry.locations || []).map((l) => l.raw),
    ...(entry.sections || []).flatMap((s) => [s.printed, s.designation]), entry.plate?.printed,
    entry.material?.mark, entry.definition?.mark, ...(entry.supports || []).map((s) => s.printed)]
    .some((text) => normalizeLocation(text).includes(q));
}

// Everything the schedule says about one plate mark: its dimensions with
// their roles, where they are printed and the schedule entries it is
// assigned to. Scoped to one schedule; equal dimensions never merge marks.
function PlateMarkDialog({ target, entries, onView, onClose }) {
  if (!target) return null;
  const assigned = entries.filter((e) => e.schedule_id === target.schedule.id && e.plate?.printed === target.mark);
  const plate = assigned.find((e) => plateHasDims(e.plate))?.plate || assigned[0]?.plate || {};
  const dimensions = plate.via?.find((v) => v.kind === "plate schedule");
  const titleId = "summary-plate-title";
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" aria-labelledby={titleId}>
      <DialogTitle id={titleId} sx={{ pr: 6 }}>
        {plateTypeLabel(plate)} <Box component="span" sx={{ fontFamily: "monospace" }}>{target.mark}</Box>
      </DialogTitle>
      <IconButton aria-label="Close plate details" onClick={onClose} sx={{ position: "absolute", right: 8, top: 8 }}>
        <CloseOutlined />
      </IconButton>
      <DialogContent dividers>
        <Stack spacing={1.5}>
          {plateHasDims(plate) ? <PlateRoles dimensions={plate.dimensions} /> : (
            <Typography variant="body2">{PLATE_STATUS_TEXT[plate.status] || "Dimensions not established"}</Typography>
          )}
          {dimensions && (
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="body2" color="text.secondary">
                Dimensions printed in {dimensions.title ? titleCase(dimensions.title) : "the plate schedule"} ·{" "}
                {whereLabel(dimensions)}
              </Typography>
              <ViewPageButton item={{ ...dimensions, mark: `${target.mark} dimensions` }} label="View plate dimensions"
                onView={onView} />
            </Stack>
          )}
          <Box>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              Assigned in {target.schedule.name} to {assigned.length} schedule entr{assigned.length === 1 ? "y" : "ies"}:
            </Typography>
            <Box component="ul" sx={{ m: 0, p: 0, listStyle: "none", display: "flex", flexWrap: "wrap", gap: 1 }}>
              {assigned.map((e) => (
                <Typography key={e.id} component="li" variant="body2" sx={{ fontFamily: "monospace", userSelect: "all" }}>
                  {(e.locations || []).map((location) => location.raw).join(", ") || columnLabel(e)}
                </Typography>
              ))}
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
              Schedule entries are definitions, not a count of plates. Plate marks with the same dimensions stay
              separate marks.
            </Typography>
          </Box>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

function ColumnSchedules({ data, schedules, title, intro, onView, documentId, levelsBySchedule = {}, notes = {}, searchable,
  onLocate }) {
  const [query, setQuery] = useState("");
  const [plateTarget, setPlateTarget] = useState(null);
  const blocks = schedules.map((schedule) => {
    const all = data.entries.filter((e) => e.schedule_id === schedule.id);
    return { schedule, all, entries: all.filter((e) => entryMatches(e, query)) };
  });
  const matches = blocks.reduce((n, b) => n + b.entries.length, 0);
  const total = blocks.reduce((n, b) => n + b.all.length, 0);
  const filtered = Boolean(query.trim());
  const nameOf = (id) => schedules.find((s) => s.id === id)?.name;
  const content = (
    <>
      {intro && <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{intro}</Typography>}
      {searchable && (
        <Stack direction="row" spacing={1.5} sx={{ mb: 1.5, alignItems: "center", flexWrap: "wrap" }} useFlexGap>
          <TextField
            size="small"
            label="Find a location, section or plate"
            placeholder="e.g. C.8-8.9"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            sx={{ width: { xs: "100%", sm: 280 } }}
            slotProps={{
              input: {
                startAdornment: <InputAdornment position="start"><SearchOutlined fontSize="small" /></InputAdornment>,
                endAdornment: query ? (
                  <InputAdornment position="end">
                    <IconButton size="small" aria-label="Clear location search" onClick={() => setQuery("")}>
                      <CloseOutlined fontSize="small" />
                    </IconButton>
                  </InputAdornment>
                ) : null,
              },
            }}
          />
          <Typography variant="body2" color="text.secondary" role="status">
            {filtered
              ? `${matches} of ${total} printed entries match` + (matches
                ? ` (${blocks.filter((b) => b.entries.length).map((b) => `${b.entries.length} in ${b.schedule.name}`).join("; ")})`
                : "")
              : `Searches all ${total} printed entries in ${blocks.length} group${blocks.length === 1 ? "" : "s"}`}
          </Typography>
        </Stack>
      )}
      {blocks.map(({ schedule, all, entries }) => (
        <ColumnScheduleBlock
          key={schedule.id}
          schedule={schedule}
          entries={entries}
          total={all.length}
          filtered={filtered}
          onView={onView}
          documentId={documentId}
          levels={levelsBySchedule[schedule.id]}
          notes={notes}
          onLocate={onLocate}
          scopeName={nameOf(schedule.scope_schedule_id)}
          onPlate={(s, mark) => setPlateTarget({ schedule: s, mark })}
        />
      ))}
      <PlateMarkDialog target={plateTarget} entries={data.entries} onView={onView} onClose={() => setPlateTarget(null)} />
    </>
  );
  return title ? <Section title={title} id="summary-columns">{content}</Section> : content;
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

// Each plan view the trace found, as a source the viewer can switch to.
function planSourcesOf(trace, location) {
  if (trace?.status !== "traced") return [];
  const sources = trace.levels.flatMap((level) => level.plans.flatMap((plan) => plan.candidates.flatMap((c, i) => [{
    page: c.page,
    sheet: plan.sheet,
    bbox: c.symbol?.bbox || c.point_bbox,
    mark: `${level.name} grid intersection${plan.candidates.length > 1 ? ` ${i + 1}` : ""}`,
    tab: `Plan ${plan.sheet || `p. ${c.page}`}${plan.candidates.length > 1 ? ` (${i + 1})` : ""}`,
    location,
  }, ...(c.offset?.sides || []).map((side) => ({
    page: c.page, sheet: plan.sheet, bbox: side.symbol?.bbox || side.point_bbox, location,
    mark: `${location} offset toward grid ${side.toward || "?"}`,
    tab: `${plan.sheet || `p. ${c.page}`} offset toward ${side.toward || "edge"}`,
  }))])));
  return [...new Map(sources.map((source) => [sourceIdentity(source), source])).values()];
}

function ColumnTrace({ entry, documentId, onView, onTraced }) {
  const [state, setState] = useState({ loading: false, trace: null, error: null });
  const request = useRef(0);
  useEffect(() => () => { request.current += 1; }, []);
  const location = entry.location_text || entry.mark;
  if (!location) return null;
  // An entry listing several locations is traced one location at a time.
  const locations = entry.locations?.length > 1 ? entry.locations.map((loc) => loc.raw) : [location];
  const load = async (location) => {
    const ticket = ++request.current;
    onTraced?.([]);
    setState({ loading: true, trace: null, error: null, location });
    try {
      const trace = await getColumnTrace(documentId, location, entry.schedule_id);
      if (request.current !== ticket) return;
      setState({ loading: false, trace, error: null, location });
      onTraced?.(planSourcesOf(trace, location));
    } catch (error) {
      if (request.current !== ticket) return;
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
      {state.location && <Typography variant="body2">Selected location: {state.location}</Typography>}
      {(trace || state.loading) && locations.length > 1 && (
        <Button size="small" onClick={() => { request.current += 1; setState({ loading: false, trace: null, error: null }); onTraced?.([]); }}>
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

const comparedValue = (match) => match.values.find((v) => v.compared) || match.values[0];

// What the plan says for the level: its name when it agrees ("Office roof ·
// S123"), its value when it differs ("55′-2″ · S122").
function LinkedEvidence({ match }) {
  const value = comparedValue(match);
  const where = match.sheet || `p. ${match.page}`;
  if (match.association === "candidate") return <>Candidate: {titleCase(match.plan)} · {where}</>;
  if (match.comparison === "differs" && value) return <><Dim raw={value.raw || value.display} /> · {where}</>;
  return <>{titleCase(value?.name || match.plan)} · {where}</>;
}

function Comparison({ match, difference }) {
  if (match.association === "candidate") return <Typography variant="body2" color="text.secondary">Not compared — candidate</Typography>;
  if (match.comparison === "differs") {
    return (
      <Typography variant="body2" color="warning.main">
        Sources disagree{difference !== undefined ? <> — <Dim inches={Math.abs(difference)} /></> : null}
      </Typography>
    );
  }
  if (match.comparison === "agrees") return <Typography variant="body2">Agrees</Typography>;
  return <Typography variant="body2" color="text.secondary">Not compared</Typography>;
}

// Why the plan evidence is (or is not) linked: alternate titles checked,
// sheets without an elevation, other buildings excluded, the scope reasoning.
function levelDiagnostics(level) {
  const matches = level.plan_matches || [];
  return [
    `Printed in the schedule as “${level.name}”${level.surface ? ` (${level.surface})` : ""}.`,
    ...matches.filter((m) => m.plan_qualifiers?.length).map((m) =>
      `${m.sheet || `p. ${m.page}`} names it “${m.plan_qualifiers.join(" ")}”; the schedule does not.`),
    ...matches.map((m) => `${m.sheet || `p. ${m.page}`} (${titleCase(m.plan)}): ${
      m.association === "candidate" ? "title fits, building / area not established" : "same building / area"}.`),
    level.also_titled?.length ? `Also checked ${level.also_titled.join(", ")}: no elevation stated there.` : null,
    level.excluded_scope?.length
      ? `Not this building / area: ${level.excluded_scope
        .map((x) => `${x.sheet || `p. ${x.page}`}${x.sheet_title ? ` (${titleCase(x.sheet_title)})` : ""}`).join(", ")}.`
      : null,
    level.association_note,
    level.note,
  ].filter(Boolean);
}

function LevelRow({ level, onView, note, differences = {} }) {
  const [open, setOpen] = useState(false);
  const sourceItem = { page: level.page, sheet: level.sheet, bbox: level.bbox, mark: level.name };
  const linked = level.plan_matches || [];
  const name = shortLevel(level.name) || "Unnamed level line";
  return (
    <>
      <TableRow sx={{ "& > td": { verticalAlign: "top", borderBottom: open ? 0 : undefined } }}>
        <TableCell>
          <Typography variant="body2" fontWeight={700}>{name}</Typography>
        </TableCell>
        <TableCell>
          <Typography variant="body2" fontWeight={600}>{level.printed ? <Dim raw={level.printed} /> : "—"}</Typography>
          {level.status !== "read" && <StatusText status="not_established" />}
          {level.resolved && (
            <Typography variant="body2">
              {surfaceLabel(level.resolved.surface)} <Dim raw={level.resolved.display} /> on {level.resolved.via}
            </Typography>
          )}
        </TableCell>
        <TableCell>
          {linked.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              {ASSOCIATION_EMPTY[level.association] || ASSOCIATION_EMPTY.unresolved}
            </Typography>
          )}
          {linked.map((match) => (
            <Typography key={match.page} variant="body2"><LinkedEvidence match={match} /></Typography>
          ))}
          {level.review && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              All printed sources: {reviewSourcesText(level.review)} (see Items needing attention)
            </Typography>
          )}
        </TableCell>
        <TableCell>
          {linked.length === 0 ? <Typography variant="body2" color="text.secondary">—</Typography> : linked.map((match) => (
            <Comparison key={match.page} match={match} difference={differences[match.page]} />
          ))}
        </TableCell>
        <TableCell align="right" sx={{ width: "1%" }}>
          <Stack direction="row" spacing={0.75} sx={{ justifyContent: "flex-end", flexWrap: "wrap" }} useFlexGap>
            {(level.occurrences?.length > 1 ? level.occurrences : [sourceItem]).map((o, i, all) => (
              <ViewPageButton
                key={i}
                item={{ ...o, mark: all.length > 1 ? `${level.name} (schedule part ${i + 1})` : level.name }}
                label={all.length > 1 ? `Schedule ${i + 1}` : "Schedule"}
                onView={onView}
              />
            ))}
            {linked.map((match) => {
              const value = comparedValue(match);
              return value ? (
                <ViewPageButton key={`p${match.page}`} item={{ ...value.source, mark: `${level.name} on ${match.sheet || `p. ${match.page}`}` }}
                  label={`Plan ${match.sheet || `p. ${match.page}`}`} onView={onView} />
              ) : null;
            })}
            <Button size="small" onClick={() => setOpen(!open)} aria-expanded={open}
              aria-label={`Why this source? ${level.name}`}>
              Why this source?
            </Button>
          </Stack>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={5} sx={{ py: 0, borderBottom: open ? undefined : 0 }}>
          <Collapse in={open} unmountOnExit>
            <Box component="ul" sx={{ m: 0, mb: 1.5, pl: 2.5 }}>
              {levelDiagnostics(level).map((line) => (
                <Typography key={line} component="li" variant="body2" color="text.secondary">{line}</Typography>
              ))}
            </Box>
            <ModelNote text={note} />
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

// Plan elevations in the same plain status words as the rest of the summary.
const ELEVATION_STATUS = { read: "read", derived: "calculated", unresolved: "not_established" };

function PlanElevationRow({ item, onView }) {
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
        <Typography variant="body2" fontWeight={600}>{item.value ? <Dim raw={item.value.raw || item.value.display} /> : "—"}</Typography>
        <StatusText status={ELEVATION_STATUS[item.status]} />
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

function LevelTable({ group, onView, notes, differences }) {
  return (
    <Paper variant="outlined" sx={{ mb: 2, overflow: "hidden" }}>
      <Typography variant="subtitle1" fontWeight={700} sx={{ px: 2, py: 1.25, bgcolor: "action.hover" }}>
        Levels in {group.name}
      </Typography>
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small" aria-label={`Levels in ${group.name}`}>
          <TableHead>
            <TableRow>
              <TableCell>Level</TableCell>
              <TableCell>Schedule elevation</TableCell>
              <TableCell>Linked plan evidence</TableCell>
              <TableCell>Comparison</TableCell>
              <TableCell align="right">Source actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {group.items.map((level, i) => (
              <LevelRow key={`${level.name}-${i}`} level={level} onView={onView}
                note={notes[`${level.schedule_id}|${level.name}`]}
                differences={differences[`${level.schedule_id}|${level.name}`]} />
            ))}
          </TableBody>
        </Table>
      </Box>
    </Paper>
  );
}

function LevelsAndElevations({ data, onView, schedules = [], notes = {}, conflicts = [] }) {
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
  // The backend's conflict facts give each disagreement's difference.
  const differences = {};
  for (const c of conflicts) {
    (differences[`${c.level.schedule_id}|${c.level.name}`] ||= {})[c.match.page] = c.difference;
  }
  // A concrete / parking schedule's levels are kept in their own group.
  const main = bySchedule.filter((g) => g.material !== "concrete");
  const parking = bySchedule.filter((g) => g.material === "concrete");
  return (
    <Section title="Levels and supported vertical extents">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Each schedule level with the plan evidence linked to it in the same building or area. Equal elevations
        never link anything by themselves; when sources differ, both values are shown.
      </Typography>
      {main.map((group) => (
        <LevelTable key={group.id} group={group} onView={onView} notes={notes} differences={differences} />
      ))}
      {parking.length > 0 && (
        <Accordion disableGutters elevation={0} variant="outlined">
          <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
            <Typography variant="body2" fontWeight={600}>
              Parking / concrete schedule levels · {parking.map((g) => g.name).join(", ")}
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            {parking.map((group) => (
              <LevelTable key={group.id} group={group} onView={onView} notes={notes} differences={differences} />
            ))}
          </AccordionDetails>
        </Accordion>
      )}
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

// The uploaded PDF on the source page, with the mark highlighted when its
// bounding box is known. Reuses the Drawing Review viewer; needs no prediction.
// A target with ``alternatives`` (a column's schedule, plate assignment,
// plate dimensions and plan views) gets tabs to switch between them; the
// row that opened it stays selected and gets focus back on close.
function SourceViewerDialog({ documentId, target, onClose }) {
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("md"));
  if (!target) return null;
  return <SourceViewer key={sourceIdentity(target)} documentId={documentId} target={target}
    onClose={onClose} fullScreen={fullScreen} />;
}

function SourceViewer({ documentId, target, onClose, fullScreen }) {
  const alternatives = target.alternatives?.length > 1 ? target.alternatives : null;
  const [index, setIndex] = useState(() =>
    Math.max(0, (alternatives || []).findIndex((a) => sourceIdentity(a) === sourceIdentity(target))));
  const source = alternatives ? alternatives[index] : target;
  const title = [source.mark, whereLabel({ sheet: source.sheet, page: source.page })]
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
      {alternatives && (
        <Tabs value={index} onChange={(_event, value) => setIndex(value)} variant="scrollable" allowScrollButtonsMobile
          aria-label="Sources for this column" sx={{ px: 1, borderBottom: 1, borderColor: "divider" }}>
          {alternatives.map((a, i) => (
            <Tab key={sourceIdentity(a)} value={i} label={a.tab || whereLabel(a)}
              id={`summary-source-tab-${i}`} aria-controls="summary-source-panel" />
          ))}
        </Tabs>
      )}
      <DialogContent dividers id="summary-source-panel" role={alternatives ? "tabpanel" : undefined}
        aria-labelledby={alternatives ? `summary-source-tab-${index}` : undefined}
        sx={{ p: 0, height: fullScreen ? "100%" : "74vh" }}>
        <SourcePdf documentId={documentId} source={source} selectionKey={sourceIdentity(source)} />
      </DialogContent>
    </Dialog>
  );
}

// Undecoded key parts, in plain words. A masked label defines nothing.
const KEY_PART_TEXT = {
  conflicting: "Two visible labels at its leaders — not decoded",
  hidden_label: "Its label is masked on the sheet — not decoded",
  partially_hidden: "Its label is partly masked — not decoded",
};

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
              : KEY_PART_TEXT[part.status] || "No leader to a visible label — not decoded"}
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

// A plan note giving top of steel as an offset from a surface without saying
// above or below: what is known, what is missing, the note and the level it
// affects. Never turned into an elevation; "deck" stays deck, not slab.
function UnresolvedSteelOffsets({ items, onView }) {
  return (
    <Box>
      <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
        Top of steel: offset stated, direction not stated
      </Typography>
      <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        {items.map((e) => (
          <Box key={`${e.page}-${e.rule}`} sx={{ p: 1.25, border: 1, borderColor: "divider", borderRadius: 1 }}>
            <Box component="dl" sx={{ m: 0, mb: 0.75, display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1.5, rowGap: 0.25 }}>
              {[
                ["Level", `${(e.levels || []).map((l) => shortLevel(l.name)).join(", ") || "Not linked to a schedule level"} · ${e.sheet || `p. ${e.page}`}`],
                ["Known", <><Dim inches={e.offset.inches} strong /> from the {e.relative_to}</>],
                ["Missing", `Whether it is above or below the ${e.relative_to}`],
                ["Note", `“${e.rule}”`],
              ].map(([label, value]) => (
                <Box key={label} sx={{ display: "contents" }}>
                  <Typography component="dt" variant="body2" color="text.secondary">{label}</Typography>
                  <Typography component="dd" variant="body2" sx={{ m: 0, minWidth: 0, wordBreak: "break-word" }}>{value}</Typography>
                </Box>
              ))}
            </Box>
            <ViewPageButton item={{ ...e.source, mark: `top of steel note on ${e.sheet || `p. ${e.page}`}` }}
              label="View plan note" onView={onView} />
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// What an estimator must check before relying on the summary: sources that
// disagree (both values, side by side), items the drawing leaves open, and
// plates whose dimensions could not be linked. Nothing here is resolved.
function NeedsAttention({ conflicts = [], items = [], plateIssues = [], steelOffsets = [], notes = {}, onView, onCompare }) {
  if (!conflicts.length && !items.length && !plateIssues.length && !steelOffsets.length) return null;
  return (
    <Section title="Items needing attention">
      <Stack spacing={1.5}>
        {conflicts.map((c) => (
          <Box key={`${c.level.schedule_id}-${c.level.name}-${c.match.page}`}>
            <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
              {shortLevel(c.level.name)} — {c.level.review ? "elevation requires review" : "sources disagree"}
            </Typography>
            {c.level.review && c.level.review.plan_page === c.match.page
              ? <LevelReview review={c.level.review} onView={onView} onCompare={onCompare} />
              : <ConflictComparison {...c} onView={onView} onCompare={onCompare} />}
            <ModelNote text={notes[`${c.level.schedule_id}|${c.level.name}`]} />
          </Box>
        ))}
        {steelOffsets.length > 0 && <UnresolvedSteelOffsets items={steelOffsets} onView={onView} />}
        {items.length > 0 && (
          <Alert severity="warning" variant="outlined" icon={false} sx={{ py: 0.25 }}>
            <Stack component="ul" sx={{ m: 0, pl: 2.5 }} spacing={0.75}>
              {items.map((u) => (
                <Typography key={u.id} component="li" variant="body2">
                  {u.text}{" "}
                  {!u.sources?.length && (
                    <Typography component="span" variant="caption" color="text.secondary">
                      ({whereLabel(u)})
                    </Typography>
                  )}{" "}
                  {u.sources?.length ? u.sources.map((src, i) => (
                    <ViewPageButton key={i} item={{ ...src, mark: src.label }} label={src.sheet || `p. ${src.page}`}
                      onView={onView} />
                  )) : <ViewPageButton item={{ ...u, page: u.page || u.pages?.[0] }} onView={onView} />}
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

function Section({ title, source, children, id }) {
  return (
    <Box component="section" id={id} sx={{ mb: 2.5, scrollMarginTop: 72 }}>
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

// Printed heading paths -> header rows. A group heading (REINFORCEMENT, TOP)
// spans the columns it heads; a column whose path ends early spans the rows
// below it. Leaf columns never merge, even when their labels match.
function headerRows(paths) {
  const depth = Math.max(1, ...paths.map((p) => p.length));
  const rows = Array.from({ length: depth }, () => []);
  paths.forEach((path, column) => {
    path.forEach((label, r) => {
      const leaf = r === path.length - 1;
      const last = rows[r][rows[r].length - 1];
      const prefix = path.slice(0, r + 1).join("\u0000");
      if (!leaf && last && !last.leaf && last.end === column && paths[last.start].slice(0, r + 1).join("\u0000") === prefix) {
        last.end += 1;
        return;
      }
      rows[r].push({ label, start: column, end: column + 1, leaf, rowSpan: leaf ? depth - r : 1 });
    });
  });
  return rows;
}

// A printed value: a length gets symbols; rebar (#4, 4-#6), notes and
// blanks are shown exactly as printed (a blank stays blank).
function PrintedValue({ text }) {
  if (!text) return null;
  return /\d/.test(text) && /^[\s\d'"′″/-]+$/.test(text) ? <Dim raw={text} /> : text;
}

function SupportingScheduleTable({ schedule, definitions, onView }) {
  const rows = supportingRowsOf(schedule, definitions);
  const paths = (rows.find((r) => r.cells.length)?.cells || []).map((c) => c.path?.length ? c.path : [c.heading]);
  const header = headerRows([["MARK"], ...paths]);
  const unread = rows.filter((r) => r.unread);
  const where = whereLabel(schedule);
  return (
    <Paper variant="outlined" sx={{ mb: 2, overflow: "hidden" }}>
      <Stack direction="row" spacing={1} sx={{ px: 2, py: 1.25, alignItems: "center", flexWrap: "wrap", bgcolor: "action.hover" }} useFlexGap>
        <Typography variant="subtitle1" fontWeight={700}>{titleCase(schedule.title)}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
          {where} ·{" "}
          {printedRowsText(schedule)} · {completenessText([schedule])}
        </Typography>
        <ViewPageButton item={{ ...schedule, mark: schedule.title }} label="View schedule" onView={onView} />
      </Stack>
      {unread.length > 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ px: 2, pt: 1 }}>
          {unread.length} printed row{unread.length === 1 ? " is" : "s are"} not used as takeoff label
          definitions ({unread.map((r) => r.mark).join(", ")}); their cells are read and shown as printed, and
          nothing is inferred for them
          {unread.every((r) => r.reference) ? " — their remarks refer to another source" : ""}.
        </Typography>
      )}
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small" aria-label={titleCase(schedule.title)} sx={{ "& th, & td": { borderRight: 1, borderColor: "divider" } }}>
          <TableHead>
            {header.map((cells, r) => (
              <TableRow key={r}>
                {cells.map((cell) => (
                  <TableCell key={`${r}-${cell.start}`} colSpan={cell.end - cell.start} rowSpan={cell.rowSpan}
                    align={cell.leaf ? "left" : "center"} sx={{ verticalAlign: "bottom" }}>
                    {titleCase(cell.label)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.key} sx={{ "& > td": { verticalAlign: "top" } }}>
                <TableCell>
                  {onView && row.bbox ? (
                    <Button size="small" onClick={() => onView({ page: schedule.page, sheet: schedule.sheet, bbox: row.bbox, mark: row.mark })}
                      aria-label={`View ${row.mark} in ${titleCase(schedule.title)} (${where})`}
                      sx={{ px: 0.5, minWidth: 0, fontFamily: "monospace", fontWeight: 700, fontSize: "0.875rem" }}>
                      {row.mark}
                    </Button>
                  ) : (
                    <Typography variant="body2" fontWeight={700} sx={{ fontFamily: "monospace" }}>{row.mark}</Typography>
                  )}
                  {row.material && (
                    <Typography variant="caption" sx={{ display: "block" }}>{row.material}</Typography>
                  )}
                  {(row.unread || row.reference) && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", whiteSpace: "nowrap" }}>
                      {row.reference ? "Refers to another source" : "Shown as printed"}
                    </Typography>
                  )}
                </TableCell>
                {paths.map((_path, i) => (
                  <TableCell key={i} sx={{ minWidth: row.cells[i]?.text?.length > 40 ? 260 : undefined }}>
                    <PrintedValue text={row.cells[i]?.text} />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    </Paper>
  );
}

// One expandable group of supporting information; its open state lives in
// the panel, so it survives re-renders and other groups opening.
function SupportGroup({ id, title, summary, expanded, onToggle, children }) {
  return (
    <Accordion disableGutters elevation={0} variant="outlined" expanded={Boolean(expanded[id])}
      onChange={(_event, open) => onToggle(id, open)} slotProps={{ transition: { unmountOnExit: true } }}>
      <AccordionSummary expandIcon={<ExpandMoreOutlined />} aria-controls={`summary-support-${id}`} id={`summary-support-${id}-head`}>
        <Typography variant="body2" fontWeight={600}>
          {title}
          {summary && (
            <Typography component="span" variant="body2" color="text.secondary"> · {summary}</Typography>
          )}
        </Typography>
      </AccordionSummary>
      <AccordionDetails id={`summary-support-${id}`}>{children}</AccordionDetails>
    </Accordion>
  );
}

/**
 * "What Estima3D understood about this drawing set" -- renders the
 * deterministic Drawing Intelligence Profile
 * (services/engineering/drawing_intelligence.py), optionally LLM-polished.
 * Nothing here changes a predicted section, candidate or takeoff quantity.
 */
// Focus goes back to the control that opened a dialog when it closes.
function useOpener(setter) {
  const opener = useRef(null);
  const open = (value) => {
    opener.current = typeof document !== "undefined" ? document.activeElement : null;
    setter(value);
  };
  const close = () => {
    setter(null);
    const node = opener.current;
    if (node && typeof node.focus === "function") setTimeout(() => node.isConnected && node.focus(), 0);
  };
  return [open, close];
}

export default function DrawingSummaryPanel({ profile, documentId = null }) {
  const [sourceTarget, setSourceTarget] = useState(null);
  const [comparePair, setComparePair] = useState(null);
  const [locateRequest, setLocateRequest] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [openSource, closeSource] = useOpener(setSourceTarget);
  const [openCompare, closeCompare] = useOpener(setComparePair);
  const [openLocate, closeLocate] = useOpener(setLocateRequest);
  if (!profile) return null;
  const onView = documentId ? openSource : null;
  const onLocate = documentId ? (location, scheduleId) => openLocate({ location, scheduleId }) : null;

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
  const sheetPages = di?.sheet_index?.pages || [];
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

  // Supporting (non-steel) schedules with their coverage, grouped by kind;
  // a definition outside every covered table is listed on its own.
  const coverage = di?.supporting_schedules || [];
  const coverageKey = (page, title) => `${page}|${title}`;
  const covered = new Set(coverage.map((s) => coverageKey(s.page, s.title)));
  const looseSupporting = supportingDefinitions.filter((d) => !covered.has(coverageKey(d.page, d.schedule_title)));
  const supportingGroups = supportingGroupsOf(coverage);
  const directory = directoryRows(di, supportingGroups);
  const goTo = (row) => {
    if (row.group) setExpanded((state) => ({ ...state, [row.group]: true }));
    setTimeout(() => document.getElementById(row.anchor)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };
  // Top-of-steel notes with an offset but no direction (review items).
  const steelOffsets = (levels?.plan_elevations || []).filter((e) => e.status === "unresolved" && e.offset);
  const toggle = (id, open) => setExpanded((state) => ({ ...state, [id]: open }));

  const extractionDetails = narrative && (
    <>
            {sheetPages.length === 0 && (
              <Section title="Structural content">
                <Para muted>{narrative.structural_content}</Para>
              </Section>
            )}

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

    </>
  );

  return (
    <LocationProvider profile={profile}>
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2.5 }, ...SUMMARY_TYPE }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", mb: 0.5, flexWrap: "wrap" }}>
        <Typography variant="subtitle1" component="h2" fontWeight={700}>
          What Estima3D read from this drawing set
        </Typography>
        {method === "llm_enhanced" && (
          <Typography variant="caption" color="text.secondary">overview wording by model, checked against the drawing</Typography>
        )}
        {hasNarrative && (
          <Stack direction="row" spacing={1} sx={{ ml: "auto" }}>
            <Button size="small" startIcon={<PrintOutlined fontSize="small" />} href="/drawing-summary/report?mode=concise">
              Print summary
            </Button>
            <Button size="small" href="/drawing-summary/report?mode=full">Full evidence report</Button>
          </Stack>
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
          {/* A. Project and scope: orientation and the schedule directory */}
          <Section title="Project and scope">
            <Typography variant="body1">{narrative.project_overview}</Typography>
            <ScheduleDirectory rows={directory} onGo={goTo} />
          </Section>

          <SheetIndex index={di.sheet_index} onView={onView} />
          <EngineeringIntelligence data={di.engineering_intelligence} onView={onView} />

          {/* B. Items needing attention */}
          <NeedsAttention
            conflicts={conflicts}
            items={unresolved}
            plateIssues={plateIssues}
            steelOffsets={steelOffsets}
            notes={modelNotes}
            onView={onView}
            onCompare={documentId ? openCompare : null}
          />

          {/* C. Columns, plates and plan locations: every column group, steel first */}
          {columnSchedules.length > 0 && (
            <ColumnSchedules
              data={columnSchedule}
              schedules={[...steelSchedules, ...concreteSchedules]}
              title="Columns, plates and plan locations"
              intro="One row per printed entry — a definition, not an installed column. Locate on plan finds the grid intersection on the plans; a plate mark opens its roles and locations; Details lists every source."
              onView={onView}
              documentId={documentId}
              levelsBySchedule={levelsBySchedule}
              notes={modelNotes}
              onLocate={onLocate}
              searchable
            />
          )}
          {definitions.length > 0 && (
            <MarksAndDefinitions definitions={definitions} notes={modelNotes} onView={onView}
              title="Steel marks and definitions" />
          )}

          {/* D. Levels and supported vertical extents */}
          {hasLevels && (
            <LevelsAndElevations data={levels} onView={onView} schedules={columnSchedules} notes={modelNotes}
              conflicts={conflicts} />
          )}
          {!hasLevels && (levels?.plan_elevations || []).length > 0 && (
            <Section title="Elevations stated on plans" source="Local plan notes, not a building-level list">
              <LevelEvidenceDetails data={levels} onView={onView} />
            </Section>
          )}

          {/* E. Drawing notation and interpretation rules */}
          {(interpretationRules.length > 0 || notations.length > 0 || levels?.location_offsets?.length > 0) && (
            <InterpretationRules
              rules={interpretationRules}
              notes={modelNotes}
              onView={onView}
              title="Drawing notation"
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

          {/* F. Supporting schedules and evidence */}
          {hasEvidence ? (
            <Section title="Supporting schedules and evidence">
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Counts below are rows and entries printed in the drawings — definitions, not quantities.
              </Typography>
              {supportingGroups.map((group) => (
                <SupportGroup key={group.key} id={group.key} title={group.label} expanded={expanded} onToggle={toggle}
                  summary={`${group.schedules.length} schedule${group.schedules.length === 1 ? "" : "s"}${group.rows == null ? "" : ` · ${group.rows} printed row${group.rows === 1 ? "" : "s"}`}`}>
                  {group.schedules.map((schedule) => (
                    <SupportingScheduleTable key={`${schedule.page}-${schedule.title}`} schedule={schedule} onView={onView}
                      definitions={supportingDefinitions.filter((d) => coverageKey(d.page, d.schedule_title) === coverageKey(schedule.page, schedule.title))} />
                  ))}
                </SupportGroup>
              ))}
              {looseSupporting.length > 0 && (
                <SupportGroup id="other" title="Other non-steel definitions" expanded={expanded} onToggle={toggle}
                  summary={`${looseSupporting.length} mark${looseSupporting.length === 1 ? "" : "s"} · coverage not established`}>
                  <MarksAndDefinitions definitions={looseSupporting} notes={modelNotes} onView={onView} title={null}
                    intro="Each printed cell is shown under its own heading. Equal values in two columns are two values." />
                </SupportGroup>
              )}
              {hasLevelDetails && (hasLevels || (levels?.plan_elevations || []).length === 0) && (
                <SupportGroup id="levels" title="Detailed level evidence" expanded={expanded} onToggle={toggle}>
                  <LevelEvidenceDetails data={levels} onView={onView} />
                </SupportGroup>
              )}
              <SupportGroup id="extraction" title="Original notation and extraction details" expanded={expanded} onToggle={toggle}>
                {extractionDetails}
              </SupportGroup>
            </Section>
          ) : extractionDetails}
        </>
      )}
      <SourceViewerDialog
        documentId={documentId}
        target={sourceTarget}
        onClose={closeSource}
      />
      <CompareSourcesDialog documentId={documentId} pair={comparePair} onClose={closeCompare} />
      <LocateDialog documentId={documentId} request={locateRequest} onClose={closeLocate} />
    </Paper>
    </LocationProvider>
  );
}
