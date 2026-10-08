// A compact directory of every schedule the summary read: what it is, where
// it is printed, how many records it prints and how far they are linked.
// Counts are printed records (schedule entries, table rows, marks) -- never
// installed members.
import {
  Box,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

// Supporting (non-steel) schedules, grouped the way an estimator looks for them.
const SUPPORT_GROUPS = [
  { key: "slabs", label: "Slabs and decks", match: (s) => /SLAB|DECK/i.test(s.title) },
  { key: "walls", label: "Concrete walls", match: (s) => s.kind === "wall" },
  { key: "foundations", label: "Piers and foundations", match: (s) => ["pier", "footing", "grade_beam"].includes(s.kind) },
  { key: "beams", label: "Concrete beams", match: (s) => s.kind === "beam" },
  { key: "other-schedules", label: "Concrete columns and other schedules", match: () => true },
];

export function supportingGroupsOf(coverage) {
  const left = [...coverage];
  return SUPPORT_GROUPS.map((g) => {
    const tables = left.filter((s) => g.match(s));
    for (const t of tables) left.splice(left.indexOf(t), 1);
    return { ...g, schedules: tables,
      rows: tables.every((s) => s.printed_rows != null) ? tables.reduce((n, s) => n + s.printed_rows, 0) : null };
  }).filter((g) => g.schedules.length > 0);
}

const MATERIAL = { steel: "Steel", concrete: "Concrete", unclassified: "Not classified" };

// What a supporting group is made of: the materials its rows print (a slab /
// deck schedule mixes grating, roof deck, composite and concrete), else concrete.
function groupSystem(group) {
  const materials = [...new Set(group.schedules.flatMap((s) => Object.keys(s.materials || {})))];
  if (materials.length) return materials.map((m, i) => (i ? m : m[0].toUpperCase() + m.slice(1))).join(", ");
  return group.key === "other-schedules" ? "Concrete / not classified" : "Concrete";
}

// Separate counts, never one "interpreted" figure: rows whose cells were read
// as properties, rows a printed label links to, rows referring elsewhere.
export function completenessText(schedules) {
  const sum = (key) => schedules.reduce((n, s) => n + (s.completeness?.[key] || 0), 0);
  const [read, linked, references] = [sum("properties_read"), sum("linked"), sum("references")];
  return [
    `${plural(read, "row")} with properties read`,
    linked ? `${linked} linked from a printed label` : null,
    references ? `${references} refer${references === 1 ? "s" : ""} to another source (unresolved)` : null,
  ].filter(Boolean).join(" · ");
}

export const printedRowsText = (schedule) => (schedule.printed_rows != null
  ? plural(schedule.printed_rows, "printed row") : "printed total not established");

/** A supporting schedule's printed rows -- definitions and rows shown as printed -- in printed order. */
export function supportingRowsOf(schedule, definitions) {
  return [
    ...definitions.map((d) => ({ key: d.id, mark: d.mark, cells: d.cells || [], bbox: d.bbox, reference: d.reference,
      material: d.material })),
    ...(schedule.unread_rows || []).map((u, i) => ({ key: `u${i}`, mark: u.printed_mark, cells: u.cells || [], bbox: u.bbox,
      reference: u.reference, material: u.material, unread: true })),
  ].sort((a, b) => (a.bbox?.[1] ?? 0) - (b.bbox?.[1] ?? 0));
}

export const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

/** Directory rows from the profile (also used by the printed report). */
export function directoryRows(di, supportingGroups = []) {
  const column = di?.column_schedule || {};
  const schedules = column.schedules || [];
  const nameOf = (id) => schedules.find((s) => s.id === id)?.name || id;
  const rows = schedules.map((s) => {
    const cov = s.coverage || {};
    const own = (column.entries || []).filter((e) => e.schedule_id === s.id);
    // A concrete schedule is described by what its labels are, not by plates.
    const materials = {};
    for (const e of own) {
      if (e.material?.status === "read") {
        const key = `${e.material.material} ${e.material.mark}`;
        materials[key] = (materials[key] || 0) + 1;
      }
    }
    const definitions = own.filter((e) => e.definition).length;
    const linked = (s.material_group === "concrete" ? [
      ...Object.entries(materials).map(([label, n]) => `${n} ${label}`),
      definitions ? `${definitions} linked to a definition` : null,
    ] : [
      cov.plates_linked ? `${cov.plates_linked} plates linked` : null,
      cov.plates_not_shown ? `${cov.plates_not_shown} no plate shown` : null,
      cov.plates_unresolved ? `${cov.plates_unresolved} plate unresolved` : null,
    ]).filter(Boolean).join(" · ") || "—";
    return {
      key: `schedule-${s.id}`, anchor: `summary-schedule-${s.id}`,
      title: s.name,
      kind: s.source === "location_table" ? "Locations only in a table" : s.layout === "graphical" ? "Graphical column schedule" : "Column schedule",
      system: MATERIAL[s.material_group] || s.material_group,
      sheet: (s.sheets || []).filter(Boolean).join(", ") || `p. ${s.page}`,
      printed: plural(s.entry_count ?? 0, "entry", "entries"),
      linked,
    };
  });
  for (const t of column.location_tables || []) {
    rows.push({
      key: `location-${t.page}-${t.title}`, anchor: t.assignment_only_schedule_id ? `summary-schedule-${t.assignment_only_schedule_id}` : null,
      title: t.title, kind: "Location → section / plate table", system: "Steel",
      sheet: t.sheet || `p. ${t.page}`, printed: plural(t.rows, "row"),
      linked: [
        ...Object.entries(t.matched || {}).map(([id, n]) => `${n} in ${nameOf(id)}`),
        t.assignment_only ? `${t.assignment_only} in no column schedule` : null,
      ].filter(Boolean).join(" · "),
    });
  }
  for (const t of column.plate_tables || []) {
    rows.push({
      key: `plates-${t.page}-${t.title}`, anchor: null, title: t.title, kind: "Plate type definitions", system: "Steel",
      sheet: t.sheet || `p. ${t.page}`, printed: plural(t.marks.length, "mark"),
      linked: t.unused_marks?.length ? `${t.unused_marks.join(", ")} not assigned to a listed location` : "All marks assigned",
    });
  }
  for (const g of supportingGroups) {
    rows.push({
      key: `support-${g.key}`, anchor: `summary-support-${g.key}-head`, group: g.key,
      title: g.label, kind: plural(g.schedules.length, "schedule"), system: groupSystem(g),
      sheet: [...new Set(g.schedules.map((s) => s.sheet || `p. ${s.page}`))].join(", "),
      printed: g.rows == null ? "—" : plural(g.rows, "printed row"),
      linked: completenessText(g.schedules),
    });
  }
  return rows;
}

export function ScheduleDirectory({ rows, onGo }) {
  if (!rows.length) return null;
  return (
    <Box sx={{ overflowX: "auto", mt: 1 }}>
      <Table size="small" aria-label="Schedules read from this drawing set">
        <TableHead>
          <TableRow>
            <TableCell>Schedule</TableCell>
            <TableCell>System</TableCell>
            <TableCell>Source</TableCell>
            <TableCell>Printed</TableCell>
            <TableCell>Linked / unresolved</TableCell>
            <TableCell align="right">Go to</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key} sx={{ "& > td": { verticalAlign: "top" } }}>
              <TableCell>
                <Typography variant="body2" fontWeight={600}>{row.title}</Typography>
                <Typography variant="caption" color="text.secondary">{row.kind}</Typography>
              </TableCell>
              <TableCell><Typography variant="body2">{row.system}</Typography></TableCell>
              <TableCell><Typography variant="body2">{row.sheet}</Typography></TableCell>
              <TableCell><Typography variant="body2" sx={{ whiteSpace: "nowrap" }}>{row.printed}</Typography></TableCell>
              <TableCell><Typography variant="body2" color="text.secondary">{row.linked}</Typography></TableCell>
              <TableCell align="right">
                {row.anchor && onGo && (
                  <Button size="small" onClick={() => onGo(row)} aria-label={`Go to ${row.title}`}>Show</Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
