// Small, evidence-bound visual pieces of the Drawing Summary: dimensions with
// proper symbols, plain status text, the column → plate evidence chain, a
// schematic level diagram and the side-by-side conflict comparison. Each is
// built only from linked evidence the profile already carries.
import { Box, Button, Stack, Typography, useTheme } from "@mui/material";
import { ArrowForwardRounded, CompareOutlined } from "@mui/icons-material";
import { formatLength, formatPlate, spokenLength } from "../../lib/dimensions";
import { sourceIdentity, ViewPageButton, whereLabel } from "./sources";

export const NUMERIC = { fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" };

/** A printed length / elevation: symbols for the eye, words for a screen reader, the printed text on hover. */
export function Dim({ raw, inches, strong = false }) {
  const value = raw ?? inches;
  if (value === null || value === undefined || value === "") return <span>—</span>;
  const text = formatLength(value);
  return (
    <Box
      component="span"
      aria-label={spokenLength(value)}
      title={raw ? `As printed: ${raw}` : undefined}
      sx={{ ...NUMERIC, fontWeight: strong ? 700 : undefined }}
    >
      {text}
    </Box>
  );
}

export function PlateDims({ dimensions }) {
  const plate = formatPlate(dimensions);
  if (!plate.parts.length) return null;
  return (
    <Box>
      <Typography
        variant="body2"
        component="div"
        fontWeight={600}
        aria-label={plate.spoken}
        sx={NUMERIC}
      >
        {plate.text}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {plate.roles}
      </Typography>
    </Box>
  );
}

/** "Width 12″ · Length 18″ · Thickness ¾″" -- each value with its role, for expanded details. */
export function PlateRoles({ dimensions }) {
  const plate = formatPlate(dimensions);
  return (
    <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", rowGap: 0.5 }}>
      {plate.parts.map((p) => (
        <Typography key={`${p.label}-${p.raw}`} variant="body2" component="span">
          <Box component="span" sx={{ color: "text.secondary" }}>{p.label} </Box>
          <Box component="span" aria-label={`${p.label} ${p.spoken}`} title={`As printed: ${p.raw}`}
            sx={{ ...NUMERIC, fontWeight: 600 }}>
            {p.text}
          </Box>
        </Typography>
      ))}
    </Stack>
  );
}

// Plain statuses: what kind of evidence a value is. "Read from drawing"
// does not mean verified or approved.
const STATUS_TEXT = {
  read: { label: "Read from drawing" },
  linked: { label: "Linked through schedule" },
  calculated: { label: "Calculated from stated values" },
  disagree: { label: "Sources disagree", color: "warning.main" },
  candidate: { label: "Candidate" },
  not_established: { label: "Not established" },
};

export function StatusText({ status, children }) {
  const s = STATUS_TEXT[status];
  if (!s) return null;
  return (
    <Typography variant="caption" color={s.color || "text.secondary"} sx={{ display: "block" }}>
      {s.label}
      {children}
    </Typography>
  );
}

/**
 * Column schedule → plate assignment → plate dimensions (→ plan views once
 * traced), each step opening its own source; the viewer can switch between
 * all of them. Built from the plate's own source trail; a missing step is
 * shown as not established, never filled in.
 */
export function EvidenceChain({ entry, onView, planSources = [] }) {
  const plate = entry.plate || {};
  const via = plate.via || [];
  // Where the column is given its plate: a leader to the plate mark, a location
  // table row or the schedule cell itself.
  const assignment = via.find((v) => ["leader mark", "location table", "schedule cell"].includes(v.kind));
  const dimensions = via.find((v) => v.kind === "plate schedule");
  const steps = [
    {
      key: "schedule", label: "Column schedule", action: "View column schedule",
      item: { page: entry.page, sheet: entry.sheet, bbox: entry.bbox, mark: entry.location_text || entry.mark,
        tab: "Column schedule" },
    },
  ];
  if (assignment) {
    steps.push({ key: "assignment", label: `Plate assignment${plate.printed ? ` · ${plate.printed}` : ""}`,
      action: "View plate assignment",
      item: { ...assignment, mark: `${plate.printed || "plate"} assignment`, tab: "Plate assignment" } });
  } else if (plate.printed && plate.status !== "not_shown") {
    steps.push({ key: "assignment", label: `Plate ${plate.printed} printed in the column schedule`, item: null });
  }
  if (dimensions) {
    steps.push({ key: "dimensions", label: "Plate dimensions", action: "View plate dimensions",
      item: { ...dimensions, mark: `${plate.printed || "plate"} dimensions`, tab: "Plate dimensions" } });
  } else if (plate.printed) {
    steps.push({ key: "dimensions", label: "Plate dimensions not established", item: null, missing: true });
  }
  if (steps.length < 2 && !planSources.length) return null;
  const sources = [...steps.filter((s) => s.item).map((s) => s.item), ...planSources];
  const open = onView && ((item) => onView({ ...item, alternatives: sources }));
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }} mb={0.5}>
        Sources
      </Typography>
      <Stack
        component="ol"
        direction="row"
        sx={{ m: 0, p: 0, listStyle: "none", flexWrap: "wrap", alignItems: "center", gap: 0.75 }}
        aria-label="Evidence chain from the column schedule to the plate dimensions"
      >
        {steps.map((step, i) => (
          <Stack key={step.key} component="li" direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            {i > 0 && <ArrowForwardRounded fontSize="small" color="disabled" aria-hidden />}
            {step.item && open ? (
              <ViewPageButton item={step.item} label={step.action} onView={open} />
            ) : (
              <Typography variant="body2" color={step.missing ? "text.secondary" : "text.primary"}>
                {step.label}
              </Typography>
            )}
          </Stack>
        ))}
        {open && planSources.map((item) => (
          <Stack key={sourceIdentity(item)} component="li" direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <ArrowForwardRounded fontSize="small" color="disabled" aria-hidden />
            <ViewPageButton item={item} label={item.tab} onView={open} />
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

const ROW = 26;

/**
 * The schedule's named levels, top to bottom, and where the selected
 * column's drawn ends sit. Schematic: rows are evenly spaced, not to scale.
 * An end that is not on a level line is drawn open and dashed.
 */
export function LevelDiagram({ levels, extent, scheduleName }) {
  const theme = useTheme();
  const ordered = [...(levels || [])]
    .filter((l) => l.name)
    .sort((a, b) => (b.elevation?.inches ?? -Infinity) - (a.elevation?.inches ?? -Infinity));
  if (!extent || ordered.length < 2) return null;
  const index = (name) => ordered.findIndex((l) => l.name === name);
  const position = (end) => {
    if (!end) return null;
    if (end.position === "at") return { y: index(end.line?.name), exact: true };
    if (end.position === "between") {
      const a = index(end.upper?.name);
      const b = index(end.lower?.name);
      return a >= 0 && b >= 0 ? { y: (a + b) / 2, exact: false } : null;
    }
    if (end.position === "below") return { y: index(end.upper?.name) + 0.5, exact: false };
    if (end.position === "above") return { y: index(end.lower?.name) - 0.5, exact: false };
    return null;
  };
  const top = position(extent.top);
  const bottom = position(extent.bottom);
  const height = ordered.length * ROW + 10;
  const y = (row) => 14 + row * ROW;
  const ink = theme.palette.text.primary;
  const muted = theme.palette.text.secondary;
  const line = theme.palette.divider;
  const stroke = theme.palette.primary.main;
  const describe = (end, p) =>
    !p ? "not on the diagram" : p.exact ? `at ${end.line.name}` : `not on a level line (${end.position})`;
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }} mb={0.5}>
        Levels in {scheduleName} — schematic, not to scale
      </Typography>
      <Box
        component="svg"
        role="img"
        aria-label={`Schematic of ${ordered.length} levels; the column's top end is ${describe(extent.top, top)} and its bottom end is ${describe(extent.bottom, bottom)}.`}
        viewBox={`0 0 340 ${height}`}
        sx={{ width: "100%", maxWidth: 420, height: "auto", display: "block" }}
      >
        {ordered.map((level, i) => (
          <g key={`${level.name}-${i}`}>
            <line x1={150} x2={330} y1={y(i)} y2={y(i)} stroke={line} strokeWidth={1} />
            <text x={0} y={y(i) + 4} fontSize={11} fill={ink}>{level.name.length > 24 ? `${level.name.slice(0, 23)}…` : level.name}</text>
            <text x={326} y={y(i) - 4} fontSize={10} fill={muted} textAnchor="end">
              {level.printed ? formatLength(level.printed) : ""}
            </text>
          </g>
        ))}
        {top && bottom && (
          <>
            <line x1={240} x2={240} y1={y(top.y)} y2={y(bottom.y)} stroke={stroke} strokeWidth={5}
              strokeDasharray={top.exact && bottom.exact ? undefined : "6 4"} />
            {[top, bottom].map((end, i) => (
              end.exact
                ? <rect key={i} x={232} y={y(end.y) - 2} width={16} height={4} fill={stroke} />
                : <circle key={i} cx={240} cy={y(end.y)} r={5} fill="none" stroke={stroke} strokeWidth={2} />
            ))}
          </>
        )}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        Solid ends sit on a level line; an open, dashed end is not established. One logical column line —
        not fabricated pieces.
      </Typography>
    </Box>
  );
}

/**
 * Schedule value | Plan value | Difference, each with its own source. Both
 * values stand: nothing is chosen, averaged or resolved.
 */
export function ConflictComparison({ level, match, value, difference, onView, onCompare }) {
  const scheduleSource = { page: level.page, sheet: level.sheet, bbox: level.bbox, mark: `${level.name} in the schedule` };
  const planSource = { ...value.source, mark: `${level.name} on ${match.sheet || `p. ${match.page}`}` };
  return (
    <Box
      sx={{
        display: "grid",
        // Fits its container: three columns when there is room, stacked otherwise.
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 1.5,
        p: 1.5,
        border: 1,
        borderColor: "warning.main",
        borderRadius: 1,
      }}
    >
      <Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>Schedule · {whereLabel(scheduleSource)}</Typography>
        <Typography variant="h6" component="div"><Dim raw={level.printed} strong /></Typography>
        <ViewPageButton item={scheduleSource} label="View column schedule" onView={onView} />
      </Box>
      <Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          Plan note · {whereLabel(value.source)}
        </Typography>
        <Typography variant="h6" component="div"><Dim raw={value.raw || value.display} strong /></Typography>
        <ViewPageButton item={planSource} label="View plan note" onView={onView} />
      </Box>
      <Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>Difference</Typography>
        <Typography variant="h6" component="div"><Dim inches={difference} strong /></Typography>
        <StatusText status="calculated" />
        {onCompare && (
          <Button size="small" startIcon={<CompareOutlined fontSize="small" />} sx={{ mt: 0.5, px: 0.5 }}
            onClick={() => onCompare([scheduleSource, planSource])}>
            Compare side by side
          </Button>
        )}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ gridColumn: "1 / -1" }}>
        Sources disagree. Both values are kept; the drawing does not say which governs.
      </Typography>
    </Box>
  );
}
