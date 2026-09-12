import { Box } from "@mui/material";

// Semantic-operation variants (see src/lib/semanticContract.js) share this
// component with the two legacy Drawing Review variants ("text"/"inferred")
// below -- restrained to four hues (neutral/info/warning/success) plus
// error reserved for a genuine geometry conflict, never all at once.
const SEMANTIC_COLORS = {
  neutral: { border: "divider", bg: "rgba(100,116,139,0.10)", strong: "text.secondary" },
  info: { border: "info.main", bg: "rgba(2,136,209,0.14)", strong: "info.main" },
  warning: { border: "warning.main", bg: "rgba(237,108,2,0.14)", strong: "warning.main" },
  success: { border: "success.main", bg: "rgba(46,125,50,0.14)", strong: "success.main" },
  error: { border: "error.main", bg: "rgba(211,47,47,0.16)", strong: "error.main" },
};

/**
 * Highlight rectangle in CSS pixels over a rendered PDF page.
 *
 * Bounding boxes are PyMuPDF / pdf.js page points (top-left origin,
 * [x0, y0, x1, y1]). Scale = renderedWidth / pageWidthPts.
 *
 * `variant` is either a legacy Drawing Review value ("text" | "inferred")
 * or a semantic-operation color key from `getOverlayStyle`
 * ("neutral" | "info" | "warning" | "success" | "error"). `dashed` and
 * `badge` are semantic-overlay-only (Section 31/32: operation type must be
 * legible without relying on color alone).
 */
export default function BboxHighlight({
  boundingBox,
  pageWidthPts,
  renderedWidth,
  active = true,
  variant = "text",
  dashed = false,
  badge = null,
  badgeTitle = null,
  onClick = null,
}) {
  if (
    !boundingBox
    || boundingBox.length < 4
    || !pageWidthPts
    || !renderedWidth
  ) {
    return null;
  }

  const [x0, y0, x1, y1] = boundingBox.map(Number);
  if (![x0, y0, x1, y1].every(Number.isFinite) || pageWidthPts <= 0) {
    return null;
  }

  const scale = renderedWidth / pageWidthPts;
  const left = Math.min(x0, x1) * scale;
  const top = Math.min(y0, y1) * scale;
  const width = Math.abs(x1 - x0) * scale;
  const height = Math.abs(y1 - y0) * scale;
  const inferred = variant === "inferred";
  const semantic = SEMANTIC_COLORS[variant];

  const borderColor = semantic
    ? semantic.border
    : inferred
      ? (active ? "info.main" : "info.light")
      : (active ? "error.main" : "warning.main");
  const bgcolor = semantic
    ? semantic.bg
    : inferred
      ? (active ? "rgba(2, 136, 209, 0.16)" : "rgba(2, 136, 209, 0.08)")
      : (active ? "rgba(211, 47, 47, 0.18)" : "rgba(237, 108, 2, 0.12)");
  const borderStyle = semantic ? (dashed ? "dashed" : "solid") : (inferred ? "dashed" : "solid");

  return (
    <Box
      data-bbox-highlight={active ? "active" : "idle"}
      data-bbox-variant={variant}
      onClick={onClick}
      title={badgeTitle || undefined}
      sx={{
        position: "absolute",
        left,
        top,
        width: Math.max(width, 2),
        height: Math.max(height, 2),
        border: active ? 2 : 1.5,
        borderStyle,
        borderColor,
        bgcolor,
        borderRadius: 0.5,
        pointerEvents: onClick ? "auto" : "none",
        cursor: onClick ? "pointer" : undefined,
        boxShadow: active
          ? `0 0 0 2px ${semantic ? "rgba(37,99,235,0.35)" : "rgba(211, 47, 47, 0.35)"}`
          : "none",
        zIndex: active ? 3 : 2,
        "&:hover": onClick ? { boxShadow: "0 0 0 2px rgba(37,99,235,0.45)" } : undefined,
        "&::after": inferred || (semantic && badge)
          ? {
              content: inferred ? '"Inferred"' : `"${badge}"`,
              position: "absolute",
              top: -16,
              left: -1,
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: 0.3,
              color: "#fff",
              bgcolor: semantic ? semantic.strong : "info.main",
              px: 0.5,
              borderRadius: 0.5,
              lineHeight: 1.5,
              whiteSpace: "nowrap",
              display: active ? "block" : "none",
            }
          : undefined,
      }}
    />
  );
}

/**
 * The core "Fit Page" calculation: the largest scale at which BOTH the
 * page's width and height fit inside the available viewport, preserving
 * aspect ratio (never stretching X/Y independently). Using only one
 * dimension -- e.g. fitting width alone -- is what let landscape pages
 * taller-than-the-viewport-at-that-width get cut off vertically by
 * default; this is the fix.
 */
export function computeFitPageScale({
  pageWidthPts,
  pageHeightPts,
  availableWidth,
  availableHeight,
}) {
  if (!pageWidthPts || !pageHeightPts || pageWidthPts <= 0 || pageHeightPts <= 0) {
    return 1;
  }
  const widthRatio = Math.max(availableWidth || 0, 1) / pageWidthPts;
  const heightRatio = Math.max(availableHeight || 0, 1) / pageHeightPts;
  return Math.min(widthRatio, heightRatio);
}

/** Rendered page width (px) that fits the whole page inside the available
 * viewport -- see computeFitPageScale. */
export function computeFitPageWidth({
  pageWidthPts,
  pageHeightPts,
  availableWidth,
  availableHeight,
  minWidth = 280,
}) {
  if (!pageWidthPts || pageWidthPts <= 0) {
    return Math.max(minWidth, availableWidth || minWidth);
  }
  const scale = computeFitPageScale({
    pageWidthPts,
    pageHeightPts,
    availableWidth,
    availableHeight,
  });
  return Math.max(minWidth, pageWidthPts * scale);
}

/**
 * Rendered page width (px) for zooming into a selected bbox: the label
 * should end up clearly, comfortably readable -- not just barely legible --
 * so this targets the bbox filling a real fraction of the available width,
 * the same shape of calculation the locator used before, just floored at
 * Fit Page (never zooms OUT past showing the whole page) and capped
 * relative to Fit Page (so it can't run away to an unusable extreme).
 */
export function pageWidthForBbox({
  boundingBox,
  pageWidthPts,
  pageHeightPts,
  availableWidth,
  availableHeight,
  fillRatio = 0.4,
  maxZoomMultiplier = 4,
}) {
  const fitWidth = computeFitPageWidth({
    pageWidthPts,
    pageHeightPts,
    availableWidth,
    availableHeight,
  });
  if (
    !boundingBox
    || boundingBox.length < 4
    || !pageWidthPts
    || pageWidthPts <= 0
  ) {
    return fitWidth;
  }
  const boxWidthPts = Math.max(Math.abs(boundingBox[2] - boundingBox[0]), 8);
  const target = (Math.max(availableWidth || fitWidth, 1) * fillRatio * pageWidthPts)
    / boxWidthPts;
  return Math.min(fitWidth * maxZoomMultiplier, Math.max(fitWidth, target));
}
