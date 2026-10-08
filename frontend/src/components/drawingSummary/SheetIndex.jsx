import { Box, Chip, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { ViewPageButton } from "./sources";

const GROUPS = [
  ["general_notes", "General notes"],
  ["loading", "Loading"],
  ["foundation_plan", "Foundation"],
  ["framing_plan", "Plans"],
  ["roof_plan", "Roof"],
  ["elevation", "Elevations"],
  ["section", "Sections"],
  ["foundation_details", "Foundation details"],
  ["concrete_details", "Concrete details"],
  ["steel_details", "Steel details"],
  ["masonry_details", "Masonry details"],
  ["detail", "Details"],
  ["schedule", "Schedules"],
];

function revisionText(page) {
  const rows = page.revision?.rows || [];
  if (rows.length === 0) return page.revision?.status === "not_shown" ? "None printed" : "—";
  return rows
    .map((row) => [row.number, row.description, row.date].filter(Boolean).join(" "))
    .join("; ");
}

function scaleText(page) {
  if (page.scale) return page.scale;
  if (page.scale_status === "not_shown") return "Not shown";
  if (page.scale_status === "ambiguous") return "Ambiguous";
  return "—";
}

function SheetRow({ page, showIssue, onView }) {
  const review = page.classification_status && page.classification_status !== "read";
  const sheet = page.sheet_id_status === "read" ? page.sheet_id : "Not read";
  return (
    <TableRow>
      <TableCell sx={{ whiteSpace: "nowrap", fontFamily: "monospace" }}>{sheet}</TableCell>
      <TableCell>
        {page.sheet_title || "—"}
        {page.title_status === "read_unlabeled" && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Title is printed; the block does not label it
          </Typography>
        )}
      </TableCell>
      <TableCell>
        <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
          <span>{page.sheet_role_label || "Unknown"}</span>
          {review && (
            <Chip
              size="small"
              color="warning"
              variant="outlined"
              label={page.classification_status === "unresolved" ? "Unresolved" : "Review"}
              title={page.classification_evidence || ""}
            />
          )}
        </Stack>
      </TableCell>
      {showIssue && <TableCell>{page.issue || "—"}</TableCell>}
      <TableCell sx={{ whiteSpace: "nowrap" }}>{page.issue_date || "—"}</TableCell>
      <TableCell sx={{ whiteSpace: "nowrap" }}>{scaleText(page)}</TableCell>
      <TableCell>{revisionText(page)}</TableCell>
      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
        {page.page}
        <ViewPageButton
          item={{ page: page.page, bbox: page.source_bbox, sheet, mark: sheet }}
          label="View"
          onView={onView}
        />
      </TableCell>
    </TableRow>
  );
}

export default function SheetIndex({ index, onView }) {
  const pages = index?.pages || [];
  if (pages.length === 0) return null;
  const issues = [...new Set(pages.map((page) => page.issue).filter(Boolean))];
  const dates = [...new Set(pages.map((page) => page.issue_date).filter(Boolean))];
  const showIssue = issues.length > 1;
  const byRole = new Map(GROUPS.map(([key]) => [key, []]));
  const review = [];
  for (const page of pages) {
    if (page.classification_status === "read" && byRole.has(page.sheet_role)) {
      byRole.get(page.sheet_role).push(page);
    } else {
      review.push(page);
    }
  }
  const groups = GROUPS.filter(([key]) => byRole.get(key).length > 0)
    .map(([key, label]) => ({ key, label, pages: byRole.get(key) }));
  if (review.length > 0) groups.push({ key: "review", label: "Review", pages: review });

  return (
    <Box component="section" sx={{ mb: 2.5 }} aria-label="Sheet index">
      <Typography variant="subtitle1" component="h3" fontWeight={700}>
        Sheet index
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1 }}>
        {pages.length} sheet{pages.length === 1 ? "" : "s"}
        {issues.length === 1 ? ` · Issue: ${issues[0]}` : ""}
        {dates.length === 1 ? ` · ${dates[0]}` : ""}
        . The role is the printed sheet title. A title that names more than one type stays under Review.
      </Typography>
      {groups.map((group) => (
        <Box key={group.key} sx={{ mb: 1.5 }}>
          <Typography variant="body2" fontWeight={700} sx={{ mb: 0.5 }}>
            {group.label} · {group.pages.length}
          </Typography>
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small" aria-label={`${group.label} sheets`}>
              <TableHead>
                <TableRow>
                  <TableCell>Sheet</TableCell>
                  <TableCell>Title</TableCell>
                  <TableCell>Role</TableCell>
                  {showIssue && <TableCell>Issue</TableCell>}
                  <TableCell>Date</TableCell>
                  <TableCell>Scale</TableCell>
                  <TableCell>Revisions</TableCell>
                  <TableCell align="right">Page</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {group.pages.map((page) => (
                  <SheetRow key={page.page} page={page} showIssue={showIssue} onView={onView} />
                ))}
              </TableBody>
            </Table>
          </Box>
        </Box>
      ))}
    </Box>
  );
}
