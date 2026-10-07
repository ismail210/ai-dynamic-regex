import { Chip, Stack, Typography } from "@mui/material";
import { ViewPageButton } from "./sources";

const STATUS_COLOR = {
  target_view_found: "success",
  target_sheet_found: "info",
  target_sheet_only: "warning",
  target_missing: "warning",
  ambiguous: "warning",
  conflict: "warning",
  read: "default",
  open: "warning",
};

function statusLabel(status) {
  return String(status || "").replaceAll("_", " ");
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
      {views.length > 0 && (
        <Stack spacing={0.5} sx={{ mt: 1 }}>
          {views.slice(0, 12).map((view) => (
            <Stack key={view.view_id} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="body2">
                {view.sheet_id || `p. ${view.pdf_page}`} · {view.view_title}
                {view.view_number ? ` (${view.view_number})` : ""}
                {view.scale ? ` · ${view.scale}` : ""}
              </Typography>
              <ViewPageButton item={{ page: view.pdf_page, bbox: view.bbox, sheet: view.sheet_id, mark: view.view_title }} label="View" onView={onView} />
            </Stack>
          ))}
        </Stack>
      )}
      {references.length > 0 && (
        <Stack spacing={0.5} sx={{ mt: 1 }}>
          {references.slice(0, 12).map((ref, index) => (
            <Stack key={`${ref.reference_text}-${index}`} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="body2">
                {ref.source_sheet || `p. ${ref.source_page}`} · {ref.reference_text}
                {ref.target_sheet ? ` → ${ref.target_sheet}` : ""}
                {ref.target_number ? ` / ${ref.target_number}` : ""}
              </Typography>
              <Chip size="small" variant="outlined" color={STATUS_COLOR[ref.status] || "default"} label={statusLabel(ref.status)} />
              <ViewPageButton item={{ page: ref.source_page, bbox: ref.bbox, sheet: ref.source_sheet, mark: ref.reference_text }} label="Source" onView={onView} />
            </Stack>
          ))}
          {(data.reference_count || references.length) > 12 && (
            <Typography variant="caption" color="text.secondary">
              {data.reference_count || references.length} references. Unresolved targets stay unresolved.
            </Typography>
          )}
        </Stack>
      )}
      {(data.grids || []).length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          {(data.grid_diagnostics?.confirmed_grid_labels ?? 0) > 0
            ? `${data.grid_diagnostics.confirmed_grid_labels} grid labels are aligned with a drawn line. ${data.grid_diagnostics.grid_intersections} intersections. ${data.grid_diagnostics.objects_allocated} marks allocated, ${data.grid_diagnostics.objects_ambiguous} ambiguous, ${data.grid_diagnostics.objects_unresolved} unresolved.`
            : `${data.grids.length} plan labels are grid candidates only. A dimension such as 4'-6" is not a grid.`}
        </Typography>
      )}
      {(data.grid_allocations || []).length > 0 && (
        <Stack spacing={0.5} sx={{ mt: 0.5 }}>
          {data.grid_allocations.slice(0, 8).map((item, index) => (
            <Stack key={`${item.mark}-${index}`} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="body2">
                {item.sheet_id || `p. ${item.pdf_page}`} · {item.mark} → {item.grid_location || "unresolved"}
              </Typography>
              <Chip size="small" variant="outlined" color={item.allocation_status === "confirmed" ? "success" : "warning"} label={statusLabel(item.allocation_status)} />
              <ViewPageButton item={{ page: item.pdf_page, bbox: item.bbox, sheet: item.sheet_id, mark: item.mark }} label="Source" onView={onView} />
            </Stack>
          ))}
        </Stack>
      )}
    </section>
  );
}
