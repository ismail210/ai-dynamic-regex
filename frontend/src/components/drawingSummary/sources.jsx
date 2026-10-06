import { Button } from "@mui/material";
import { FindInPageOutlined } from "@mui/icons-material";

// One sheet can contain several sources with the same label.
export const sourceIdentity = (source) => JSON.stringify([
  source.page, source.bbox || null, source.id || source.mark || "", source.location || "",
]);

export function pagesLabel(pages) {
  if (!pages || pages.length === 0) return "";
  const shown = pages.slice(0, 8).join(", ");
  return pages.length > 8 ? `pp. ${shown}, +${pages.length - 8}` : `p. ${shown}`;
}

// "S002 · PDF p. 2" -- sheet only when the extraction read one confidently.
export function whereLabel(item) {
  const pages = item.pages?.length ? item.pages : item.page ? [item.page] : [];
  const shown = pages.slice(0, 6).join(", ") + (pages.length > 6 ? ", …" : "");
  const pdf = pages.length ? `PDF ${pages.length > 1 ? "pp." : "p."} ${shown}` : "";
  return item.sheet ? `${item.sheet} · ${pdf}` : pdf;
}

// One button per source: opens the uploaded PDF on that page (1-based).
export function ViewPageButton({ item, label, onView }) {
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
