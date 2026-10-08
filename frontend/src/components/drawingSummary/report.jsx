// The Drawing Summary as a printable report, built from the profile -- never
// from what happens to be expanded on screen. "concise" lists every steel and
// table-only column entry and summarises the rest; "full" lists every record
// the summary holds. Both end with what was left out.
import { useState } from "react";
import { formatLength, formatPlate, formatPrintedSize } from "../../lib/dimensions";
import { completenessText, directoryRows, plural, printedRowsText, supportingGroupsOf, supportingRowsOf } from "./directory";
import { RELATED_HEADING, reviewSourcesText, withLengths } from "./levelReview";
import { fetchLocation, LOCATE_STATE } from "./locate";

const where = (item) => [item?.sheet, item?.page ? `PDF p. ${item.page}` : null].filter(Boolean).join(" · ");
const titleCase = (text) => String(text || "").toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase());
const shortLevel = (name) => titleCase(String(name || "").replace(/^\s*(?:T\.?\s*O\.?|TOP OF)\s+(?:SLAB\s+|STEEL\s+|DECK\s+)?/i, "")) || name;

const STYLES = `
.dsr { font-family: "Segoe UI", Arial, sans-serif; color: #111; background: #fff; font-size: 10.5pt; line-height: 1.4;
  max-width: 1040px; margin: 0 auto; padding: 24px; }
.dsr h1 { font-size: 17pt; margin: 0 0 4px; }
.dsr h2 { font-size: 13pt; margin: 22px 0 6px; border-bottom: 1.5px solid #333; padding-bottom: 2px; break-after: avoid; }
.dsr h3 { font-size: 11pt; margin: 14px 0 4px; break-after: avoid; }
.dsr p { margin: 4px 0; }
.dsr .muted { color: #555; font-size: 9.5pt; }
.dsr table { border-collapse: collapse; width: 100%; table-layout: fixed; margin: 4px 0 10px; }
.dsr th, .dsr td { border: 1px solid #999; padding: 3px 5px; vertical-align: top; text-align: left;
  overflow-wrap: anywhere; font-size: 9.5pt; }
.dsr th { background: #eef0f3; font-weight: 600; }
.dsr thead { display: table-header-group; }
.dsr tr { break-inside: avoid; }
.dsr .mono { font-family: Consolas, "Courier New", monospace; }
.dsr .num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.dsr .warn { color: #8a4b00; }
.dsr .toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.dsr .toolbar a, .dsr .toolbar button { font: inherit; padding: 4px 10px; border: 1px solid #888; border-radius: 4px;
  background: #fff; color: #111; text-decoration: none; cursor: pointer; }
@media print {
  @page { margin: 12mm; }
  .dsr { padding: 0; max-width: none; }
  .dsr .toolbar { display: none; }
}
`;

function plateText(plate) {
  if (!plate) return "—";
  if (["read", "resolved"].includes(plate.status) && plate.dimensions?.length) return formatPlate(plate.dimensions).text;
  return "—";
}

function plateLabel(plate) {
  if (!plate) return "—";
  if (plate.printed) return plate.printed;
  return { not_shown: "Not shown", blank: "Blank", not_applicable: "N/A" }[plate.status] || "Not established";
}

function sectionText(entry) {
  const material = entry.material?.status === "read" ? entry.material : null;
  if (material) {
    return `${material.material} · ${material.mark}${material.size ? ` · ${formatPrintedSize(material.size.raw)} column section` : ""}`;
  }
  return (entry.sections || []).map((s) => s.designation || s.printed).join(", ") || "—";
}

function levelsText(entry) {
  const ext = entry.extent;
  if (ext && ["top", "bottom"].every((k) => ext[k]?.position === "at")) {
    const diff = entry.level_difference?.status === "computed" ? `; elevation difference ${formatLength(entry.level_difference.inches)} (calculated, not a member length)` : "";
    return `${shortLevel(ext.bottom.line.name)} to ${shortLevel(ext.top.line.name)}${diff}`;
  }
  if (ext) return "Ends not established";
  return entry.extent_note ? "Not given (table only)" : "—";
}

// The grid locations Locate can look for on an entry (one, or each of several).
const locateTargets = (entry) => (entry.key_role === "location"
  ? (entry.locations || []).filter((l) => l.status === "parsed").map((l) => l.raw) : []);
const locateKey = (scope, location) => `${scope || ""}|${location}`;

// A looked-up location in a few words; nothing looked up is never "not found".
function planText(found) {
  if (!found) return "Not yet looked up";
  if (found.status === "pending") return "Looking up…";
  if (found.status === "error") return "Lookup failed — retry";
  const result = found.result;
  if (result.status === "plan_not_found") return `Not found: ${result.note || "no plan prints both grid labels"}`;
  if (result.status === "not_a_grid_location") return "Not a grid location";
  const view = (result.views || [])[0];
  return view ? `${view.sheet || `p. ${view.page}`} — ${LOCATE_STATE[view.state] || view.state}` : "Not found";
}

function PlanCell({ entry, scope, plans }) {
  const targets = locateTargets(entry);
  if (!targets.length) return "—";
  if (targets.length === 1) return planText(plans[locateKey(scope, targets[0])]);
  return targets.map((t) => <div key={t}><span className="mono">{t}</span>: {planText(plans[locateKey(scope, t)])}</div>);
}

// Where the row's values were printed: the section by its schedule, the plate
// through the location table and the plate type schedule that define it.
const sheetPage = (item) => [item?.sheet, item?.page ? `p. ${item.page}` : null].filter(Boolean).join(" ");

function SourceCell({ entry }) {
  const plate = [...new Set((entry.plate?.via || []).map(sheetPage))];
  if (!plate.length) return where(entry);
  return (
    <>
      <div>Section: {sheetPage(entry)}</div>
      <div className="muted">Plate: {plate.join("; ")}</div>
    </>
  );
}

function ColumnTable({ entries, concrete, scope, plans }) {
  return (
    <table>
      <colgroup>
        <col style={{ width: concrete ? "12%" : "14%" }} />
        <col style={{ width: concrete ? "24%" : "12%" }} />
        {!concrete && <col style={{ width: "8%" }} />}
        {!concrete && <col style={{ width: "15%" }} />}
        <col style={{ width: concrete ? "20%" : "13%" }} />
        <col style={{ width: concrete ? "28%" : "20%" }} />
        <col style={{ width: concrete ? "16%" : "18%" }} />
      </colgroup>
      <thead>
        <tr>
          <th>Location</th>
          <th>{concrete ? "Section / label" : "Section"}</th>
          {!concrete && <th>Base plate</th>}
          {!concrete && <th>Plate W × L × T</th>}
          <th>{concrete ? "Linked definition" : "Levels (schedule)"}</th>
          <th>Plan location</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={e.id}>
            <td className="mono">{e.location_text || e.mark}</td>
            <td>{sectionText(e)}</td>
            {!concrete && <td className="mono">{plateLabel(e.plate)}</td>}
            {!concrete && <td className="num">{plateText(e.plate)}</td>}
            <td>
              {concrete
                ? (e.definition ? `${e.definition.mark}: ${(e.definition.cells || []).filter((c) => c.text).map((c) => c.text).join(", ")}` : "—")
                : levelsText(e)}
              {(e.supports || []).map((s) => (
                <div key={s.printed} className={s.definition?.sizes === "differ" ? "warn" : "muted"}>
                  Printed below: {s.printed}
                  {s.definition ? ` — ${s.definition.mark} in ${titleCase(s.definition.schedule_title)}` + (s.definition.sizes === "differ" ? " (sizes differ; both kept)" : "") : ""}
                </div>
              ))}
            </td>
            <td><PlanCell entry={e} scope={scope} plans={plans} /></td>
            <td><SourceCell entry={e} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LevelReviewBlock({ review }) {
  return (
    <div>
      <p><strong>{withLengths(review.headline)}</strong></p>
      <table>
        <colgroup><col style={{ width: "26%" }} /><col style={{ width: "14%" }} /><col style={{ width: "40%" }} /><col style={{ width: "20%" }} /></colgroup>
        <thead><tr><th>Source</th><th>Value</th><th>What it covers</th><th>Sheet / page</th></tr></thead>
        <tbody>
          {review.items.map((i, n) => (
            <tr key={n}>
              <td>{i.label}</td>
              <td className="num">{formatLength(i.value)}</td>
              <td>{i.scope}{i.tag?.material ? ` — ${i.tag.material}` : ""}</td>
              <td>{where(i.source)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(review.checks || []).map((c) => (
        <p key={c.slab} className="muted">
          Check of printed numbers: {formatLength(c.slab)} − {formatLength(c.offset_inches)} = {formatLength(c.result)}
          {c.printed.length ? `, printed as ${c.printed[0].name} on ${[...new Set(c.printed.map((p) => p.sheet))].join(", ")}` : ", not found among the extracted level markers"}.
        </p>
      ))}
      <p className="muted">Possible explanations (not confirmed):</p>
      <ul>
        {(review.explanations || []).filter((e) => e.status !== "observation").map((e) => (
          <li key={e.id}>{e.label} — {e.status.replace("_", " ")}. <span className="muted">{withLengths(e.basis)}</span></li>
        ))}
      </ul>
      {(review.related || []).length > 0 && (
        <>
          <p className="muted">{RELATED_HEADING}:</p>
          <ul>
            {review.related.map((r) => (
              <li key={`${r.source.page}-${r.source.bbox}`}>
                {withLengths(r.note)} <span className="muted">({where(r.source)}{r.tag?.definition ? `; ${r.tag.mark}: ${where(r.tag.definition)}` : ""})</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function SupportingTable({ table, definitions }) {
  const rows = supportingRowsOf(table, definitions);
  return (
    <table>
      <colgroup><col style={{ width: "18%" }} /><col style={{ width: "82%" }} /></colgroup>
      <thead><tr><th>Mark (as printed)</th><th>Printed cells (heading: value; blank cells omitted)</th></tr></thead>
      <tbody>
        {rows.map((r, n) => (
          <tr key={n}>
            <td className="mono">{r.mark}{r.material ? <div>{r.material}</div> : null}
              {r.reference ? <div className="muted">refers to another source</div> : r.unread ? <div className="muted">shown as printed</div> : null}</td>
            <td>{r.cells.filter((c) => c.text).map((c) => `${(c.path || [c.heading]).map(titleCase).join(" › ")}: ${c.text}`).join(" · ") || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SummaryReport({ di, document, mode }) {
  const full = mode === "full";
  const [plans, setPlans] = useState({});
  const [locateCache] = useState(() => new Map());
  const column = di.column_schedule || {};
  const schedules = column.schedules || [];
  const entries = column.entries || [];
  const coverage = di.supporting_schedules || [];
  const groups = supportingGroupsOf(coverage);
  const directory = directoryRows(di, groups);
  const levels = di.levels || {};
  const reviews = di.level_reviews || [];
  const omitted = [];
  const scopeOf = (s) => s.scope_schedule_id || s.id;
  const listedSchedules = schedules.filter((s) => full || s.material_group !== "concrete");
  const targets = listedSchedules.flatMap((s) => entries.filter((e) => e.schedule_id === s.id)
    .flatMap((e) => locateTargets(e).map((location) => ({ scope: scopeOf(s), location }))));
  const statusOf = (t) => plans[locateKey(t.scope, t.location)]?.status;
  const pending = targets.filter((t) => !["done", "pending"].includes(statusOf(t)));
  const inFlight = targets.filter((t) => statusOf(t) === "pending").length;
  const notDone = targets.filter((t) => statusOf(t) !== "done").length;
  if (notDone) {
    omitted.push(`Plan locations of ${plural(notDone, "listed location")} (not yet looked up; Locate runs on demand)`);
  }
  // Locate runs on demand only, one location at a time (each plan page is read once on the server).
  const lookUp = async () => {
    setPlans((p) => ({ ...p, ...Object.fromEntries(pending.map((t) => [locateKey(t.scope, t.location), { status: "pending" }])) }));
    for (const { scope, location } of pending) {
      const key = locateKey(scope, location);
      try {
        const result = await fetchLocation(document?.document_id, location, scope, locateCache);
        setPlans((p) => ({ ...p, [key]: { status: "done", result } }));
      } catch {
        setPlans((p) => ({ ...p, [key]: { status: "error" } }));
      }
    }
  };
  if (!full && coverage.length) {
    omitted.push(`The individual rows of ${coverage.length} supporting schedules (counted here; listed in the full evidence report)`);
  }
  return (
    <div className="dsr">
      <style>{STYLES}</style>
      <h1>Drawing Summary — {document?.source_file || "drawing set"}</h1>
      <p className="muted">
        {full ? "Full evidence report" : "Concise summary"} · {document?.document_id} · generated {new Date().toLocaleString()}.
        Informational only: schedule entries are definitions, not installed quantities; an elevation difference is
        not a member length; values are printed as read, not verified.
      </p>

      <h2>Project and scope</h2>
      <p>{di.narrative?.project_overview}</p>
      <table>
        <colgroup><col style={{ width: "30%" }} /><col style={{ width: "12%" }} /><col style={{ width: "12%" }} /><col style={{ width: "14%" }} /><col style={{ width: "32%" }} /></colgroup>
        <thead><tr><th>Schedule</th><th>System</th><th>Source</th><th>Printed</th><th>Linked / unresolved</th></tr></thead>
        <tbody>
          {directory.map((r) => (
            <tr key={r.key}><td>{r.title}<div className="muted">{r.kind}</div></td><td>{r.system}</td><td>{r.sheet}</td><td>{r.printed}</td><td>{r.linked}</td></tr>
          ))}
        </tbody>
      </table>

      <h2>Items needing attention</h2>
      {reviews.map((r) => <LevelReviewBlock key={`${r.schedule_id}-${r.level}`} review={r} />)}
      {(levels.plan_elevations || []).filter((e) => e.status === "unresolved" && e.offset).map((e, n) => (
        <p key={`o${n}`}>
          Top of steel on {e.sheet}: {formatLength(e.offset.inches)} from the {e.relative_to}; whether above or below is not
          stated. Note: “{e.rule}” ({where(e)}).
        </p>
      ))}
      {(di.unresolved || []).map((u) => (
        <p key={u.id}>{u.text} <span className="muted">({(u.sources || [u]).map(where).join("; ")})</span></p>
      ))}
      {!reviews.length && !(di.unresolved || []).length && <p className="muted">None.</p>}

      <h2>Columns, plates and plan locations</h2>
      <div className="toolbar">
        <button type="button" onClick={lookUp} disabled={!pending.length || inFlight > 0 || !document?.document_id}>
          {inFlight ? `Looking up plan locations (${targets.length - notDone} of ${targets.length})…`
            : pending.length ? `Look up plan locations (${pending.length})` : "Plan locations looked up"}
        </button>
        <span className="muted">Sections are as printed in each column schedule; each plate&apos;s source shows the
          location table and plate type schedule it comes through.</span>
      </div>
      {schedules.map((s) => {
        const own = entries.filter((e) => e.schedule_id === s.id);
        const concrete = s.material_group === "concrete";
        const listed = full || !concrete ? own : [];
        if (!listed.length) {
          const labels = {};
          for (const e of own) {
            const label = sectionText(e);
            labels[label] = (labels[label] || 0) + 1;
          }
          omitted.push(`${own.length} entries of ${s.name} are summarised by label, not listed`);
          return (
            <div key={s.id}>
              <h3>{s.name} <span className="muted">({where(s)} · {plural(own.length, "printed entry", "printed entries")})</span></h3>
              <p>{Object.entries(labels).map(([label, n]) => `${label} (${n})`).join("; ")}.</p>
              <p className="muted">Listed in full in the full evidence report.</p>
            </div>
          );
        }
        return (
          <div key={s.id}>
            <h3>{s.name} <span className="muted">({where(s)} · {plural(own.length, "printed entry", "printed entries")})</span></h3>
            {s.source === "location_table" && (
              <p className="muted">Listed only in this table, which assigns a section and a base plate and gives no levels.</p>
            )}
            {s.notes?.map((n) => <p key={n} className="muted">{n}</p>)}
            <ColumnTable entries={listed} concrete={concrete} scope={scopeOf(s)} plans={plans} />
          </div>
        );
      })}
      {(column.plate_tables || []).map((t) => (
        <div key={`${t.page}-${t.title}`}>
          <h3>{t.title} <span className="muted">({where(t)})</span></h3>
          <table>
            <colgroup><col style={{ width: "20%" }} /><col style={{ width: "40%" }} /><col style={{ width: "40%" }} /></colgroup>
            <thead><tr><th>Plate mark</th><th>Width × Length × Thickness</th><th>Assigned</th></tr></thead>
            <tbody>
              {(t.rows || []).map((r) => (
                <tr key={r.mark}>
                  <td className="mono">{r.mark}</td>
                  <td className="num">{r.dimensions?.length ? formatPlate(r.dimensions).text : "—"}</td>
                  <td>{(t.unused_marks || []).includes(r.mark) ? "Not assigned to a listed location" : plural(entries.filter((e) => e.plate?.printed === r.mark).length, "listed entry", "listed entries")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <h2>Levels and surfaces</h2>
      {[...new Set((levels.schedule_levels || []).map((l) => l.schedule_id))].map((sid) => {
        const own = (levels.schedule_levels || []).filter((l) => l.schedule_id === sid);
        return (
          <div key={sid}>
            <h3>Levels in {own[0].schedule}</h3>
            <table>
              <colgroup><col style={{ width: "22%" }} /><col style={{ width: "14%" }} /><col style={{ width: "34%" }} /><col style={{ width: "14%" }} /><col style={{ width: "16%" }} /></colgroup>
              <thead><tr><th>Level</th><th>Schedule elevation</th><th>Linked plan evidence</th><th>Comparison</th><th>Source</th></tr></thead>
              <tbody>
                {own.map((l) => (
                  <tr key={l.name}>
                    <td>{shortLevel(l.name)}<div className="muted">{l.name}</div></td>
                    <td className="num">{l.printed ? formatLength(l.printed) : "—"}</td>
                    <td>{l.review ? `${reviewSourcesText(l.review)} (see Items needing attention)` : (l.plan_matches || []).map((m) => {
                      const v = (m.values || []).find((x) => x.compared) || (m.values || [])[0];
                      return `${m.comparison === "differs" && v ? formatLength(v.raw || v.display) : titleCase(v?.name || m.plan)} · ${m.sheet}`;
                    }).join("; ") || "No linked plan evidence yet"}</td>
                    <td>{(l.plan_matches || []).map((m) => (m.comparison === "differs" ? "Sources disagree" : m.comparison === "agrees" ? "Agrees" : "Not compared")).join("; ") || "—"}</td>
                    <td>{where(l)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}

      <h2>Supporting schedules</h2>
      {groups.map((g) => (
        <div key={g.key}>
          <h3>{g.label} <span className="muted">({plural(g.schedules.length, "schedule")}{g.rows != null ? ` · ${plural(g.rows, "printed row")}` : ""})</span></h3>
          {g.schedules.map((t) => {
            const defs = (di.definitions || []).filter((d) => d.page === t.page && d.schedule_title === t.title);
            if (!full) {
              return (
                <p key={`${t.page}-${t.title}`}>
                  {titleCase(t.title)} ({where(t)}): {printedRowsText(t)}; {completenessText([t])}
                  {t.materials ? ` · ${Object.entries(t.materials).map(([m, n]) => `${m} (${n})`).join(", ")}` : ""}.
                </p>
              );
            }
            return (
              <div key={`${t.page}-${t.title}`}>
                <p><strong>{titleCase(t.title)}</strong> <span className="muted">({where(t)} · {printedRowsText(t)} · {completenessText([t])})</span></p>
                <SupportingTable table={t} definitions={defs} />
              </div>
            );
          })}
        </div>
      ))}

      {full && (
        <>
          <h2>Drawing notation and rules</h2>
          {(di.interpretation_rules || []).map((r) => (
            <p key={r.id}>{r.kind === "framing_key" ? `Framing key: ${r.source_text} — ${(r.parts || []).map((p) => `${p.token} = ${p.meaning || "not decoded"}`).join("; ")}` : r.text} <span className="muted">({where(r)})</span></p>
          ))}
          {(levels.notations || []).map((n, i) => (
            <p key={`n${i}`}>{n.sample} on a plan means {n.meaning}{n.relative_to ? `, measured from the ${n.relative_to}` : ""} <span className="muted">({n.sheet})</span></p>
          ))}
          {(levels.location_offsets || []).map((o, i) => (
            <p key={`g${i}`}><span className="mono">{o.location}</span> — grid {o.grid} offset {formatLength(o.offset.raw)} (a location, not an elevation; direction not stated) <span className="muted">({o.sheet})</span></p>
          ))}
        </>
      )}

      <h2>What this report leaves out</h2>
      <p className="muted">“Properties read” counts rows whose printed cells were read as heading: value — a concrete
        definition carries its dimensions without an AISC section. “Linked” counts rows a printed label in the set refers
        to; rows that refer to another source stay unresolved here.</p>
      {full ? (
        <>
          <p>Every record the summary holds is listed. Printed tables the reader does not read (such as development-length
            tables) and anything the extraction did not read are not shown; the directory above lists the schedules read.</p>
          {omitted.length > 0 && <ul>{[...new Set(omitted)].map((o) => <li key={o}>{o}</li>)}</ul>}
        </>
      ) : (
        <ul>
          {[...new Set(omitted)].map((o) => <li key={o}>{o}</li>)}
          <li>Drawing notation, rules and detailed level evidence (in the full evidence report).</li>
        </ul>
      )}
    </div>
  );
}
