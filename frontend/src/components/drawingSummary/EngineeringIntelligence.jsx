import { useEffect, useState } from "react";
import { Button, Chip, Stack, Typography } from "@mui/material";
import { ExpandLessOutlined, ExpandMoreOutlined } from "@mui/icons-material";
import { ViewPageButton } from "./sources";

const PAGE_SIZE = 12;

const STATUS_COLOR = {
  target_view_found: "default",
  target_sheet_found: "info",
  target_sheet_only: "warning",
  target_missing: "warning",
  ambiguous: "warning",
  conflict: "warning",
  read: "default",
  open: "warning",
};

function referenceSentence(ref) {
  const source = ref.source_sheet || `p. ${ref.source_page}`;
  const text = ref.reference_text;
  if (ref.status === "target_view_found") {
    const kind = {detail: "detail", section: "section", elevation: "elevation"}[ref.target_view_type] || "view";
    return `${source} · ${text} · ${kind} ${ref.target_number} is printed on ${ref.target_sheet}.`;
  }
  if (ref.status === "target_sheet_only") {
    return `${source} · ${text} · ${ref.target_sheet} is in the set. View ${ref.target_number} is not a printed title.`;
  }
  if (ref.status === "target_missing") {
    return `${text} · no sheet with that id.`;
  }
  if (ref.status === "ambiguous" && ref.target_sheet) {
    return `${source} · ${text} · more than one printed view uses ${ref.target_number}.`;
  }
  if (ref.status === "ambiguous") {
    return `${text} · no sheet and no view number.`;
  }
  return `${source} · ${text}`;
}

function statusLabel(status) {
  return String(status || "").replaceAll("_", " ");
}

// A mark is matched to the nearest grid crossing by distance only; even
// "confirmed" never means a member was found there.
const ALLOCATION_LABEL = {
  confirmed: "closest crossing",
  candidate: "proposed",
  review_required: "review required",
  unresolved: "no crossing nearby",
};

function ListWindow({ items, noun, renderItem, note }) {
  const resetKey = `${items.length}:${items[0]?.view_id || ""}:${items[0]?.reference_text || ""}:${items[0]?.source_page || ""}`;
  const [shown, setShown] = useState(PAGE_SIZE);
  useEffect(() => {
    setShown(PAGE_SIZE);
  }, [resetKey]);
  if (items.length === 0) return null;
  const visibleCount = Math.min(shown, items.length);
  const remaining = items.length - visibleCount;
  const next = Math.min(PAGE_SIZE, remaining);
  return (
    <Stack spacing={0.5} sx={{ mt: 1 }}>
      {items.slice(0, visibleCount).map(renderItem)}
      {items.length > PAGE_SIZE && (
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="caption" color="text.secondary">
            {visibleCount < items.length
              ? `Showing ${visibleCount} of ${items.length} ${noun}`
              : `Showing all ${items.length} ${noun}`}
          </Typography>
          {remaining > 0 && (
            <Button
              size="small"
              variant="text"
              startIcon={<ExpandMoreOutlined />}
              onClick={() => setShown((count) => Math.min(items.length, count + PAGE_SIZE))}
              aria-label={`Show ${next} more ${noun}`}
            >
              Show more ({next})
            </Button>
          )}
          {visibleCount > PAGE_SIZE && (
            <Button
              size="small"
              variant="text"
              startIcon={<ExpandLessOutlined />}
              onClick={() => setShown(PAGE_SIZE)}
              aria-label={`Show the first ${PAGE_SIZE} ${noun}`}
            >
              Show less
            </Button>
          )}
          {note && (
            <Typography variant="caption" color="text.secondary">{note}</Typography>
          )}
        </Stack>
      )}
    </Stack>
  );
}

export default function EngineeringIntelligence({ data, onView }) {
  if (!data) return null;
  const views = (data.views || []).filter((view) => view.status === "read");
  const references = data.references || [];
  const warnings = data.warnings || [];
  const conflicts = (data.levels?.building_levels || []).filter((level) => level.status === "conflict");
  if (views.length + references.length + warnings.length + conflicts.length === 0 && !(data.grids || []).length) {
    return null;
  }
  return (
    <section aria-label="Drawing relationships">
      <Typography variant="subtitle1" component="h3" fontWeight={700} sx={{ mt: 1 }}>
        Views, references, and conflicts
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1 }}>
        A reference is resolved only when the target view title is printed. Dimensions are not grids.
        Mark hits are not quantities.
      </Typography>
      {conflicts.map((level) => (
        <Stack key={level.name} direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5, flexWrap: "wrap" }}>
          <Typography variant="body2">
            {level.name}: {level.sources.map((source) => `${source.sheet_id || "plan"} ${source.value}`).join(" · ")}
          </Typography>
          <Chip size="small" color="warning" variant="outlined" label="conflict" />
        </Stack>
      ))}
      {warnings.filter((warning) => warning.type !== "level_conflict").slice(0, 8).map((warning, index) => (
        <Typography key={`${warning.type}-${index}`} variant="body2" sx={{ mb: 0.25 }}>
          {warning.message}
        </Typography>
      ))}
      <ListWindow
        items={views}
        noun="views"
        renderItem={(view) => (
          <Stack key={view.view_id} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Typography variant="body2">
              {view.sheet_id || `p. ${view.pdf_page}`} · {view.view_title}
              {view.view_number ? ` (${view.view_number})` : ""}
              {view.scale ? ` · ${view.scale}` : ""}
            </Typography>
            <ViewPageButton item={{ page: view.pdf_page, bbox: view.bbox, sheet: view.sheet_id, mark: view.view_title }} label="View" onView={onView} />
          </Stack>
        )}
      />
      <ListWindow
        items={references}
        noun="references"
        note={references.some((ref) => ref.status !== "target_view_found") ? "Unresolved targets stay unresolved." : null}
        renderItem={(ref, index) => (
          <Stack key={`${ref.reference_text}-${index}`} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Typography variant="body2">{referenceSentence(ref)}</Typography>
            <Chip size="small" variant="outlined" color={STATUS_COLOR[ref.status] || "default"} label={statusLabel(ref.status)} />
            <ViewPageButton item={{ page: ref.source_page, bbox: ref.bbox, sheet: ref.source_sheet, mark: ref.reference_text }} label="Source" onView={onView} />
            {ref.status === "target_view_found" && ref.target_bbox && (
              <ViewPageButton item={{ page: ref.target_page, bbox: ref.target_bbox, sheet: ref.target_sheet, mark: ref.reference_text }} label="Target" onView={onView} />
            )}
          </Stack>
        )}
      />
      {(data.grids || []).length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          {(data.grid_diagnostics?.confirmed_grid_labels ?? 0) > 0
            ? `${data.grid_diagnostics.confirmed_grid_labels} grid labels sit on a drawn grid line. ${data.grid_diagnostics.grid_intersections} crossings of those lines; a crossing is not a member. Marks matched to the nearest crossing by distance: ${data.grid_diagnostics.objects_allocated} proposed, ${data.grid_diagnostics.objects_ambiguous} held for review, ${data.grid_diagnostics.objects_unresolved} with no crossing nearby. A proposed grid location is not a column, a beam, or a quantity.`
            : `${data.grids.length} plan labels are grid candidates only. A dimension such as 4'-6" is not a grid.`}
        </Typography>
      )}
      {(data.grid_allocations || []).length > 0 && (
        <Stack spacing={0.5} sx={{ mt: 0.5 }}>
          {data.grid_allocations.slice(0, 8).map((item, index) => (
            <Stack key={`${item.mark}-${index}`} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="body2">
                {item.sheet_id || `p. ${item.pdf_page}`} · {item.mark}
                {item.grid_location ? ` · nearest grid crossing ${item.grid_location}` : ""}
              </Typography>
              <Chip size="small" variant="outlined" color={item.allocation_status === "review_required" ? "warning" : "default"} label={ALLOCATION_LABEL[item.allocation_status] || statusLabel(item.allocation_status)} />
              <ViewPageButton item={{ page: item.pdf_page, bbox: item.bbox, sheet: item.sheet_id, mark: item.mark }} label="Source" onView={onView} />
            </Stack>
          ))}
        </Stack>
      )}
    </section>
  );
}
