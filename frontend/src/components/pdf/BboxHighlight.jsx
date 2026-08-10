import { Box } from "@mui/material";

/**
 * Highlight rectangle in CSS pixels over a rendered PDF page.
 *
 * Bounding boxes are PyMuPDF / pdf.js page points (top-left origin,
 * [x0, y0, x1, y1]). Scale = renderedWidth / pageWidthPts.
 */
export default function BboxHighlight({
  boundingBox,
  pageWidthPts,
  renderedWidth,
  active = true,
  variant = "text",
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

  return (
    <Box
      data-bbox-highlight={active ? "active" : "idle"}
      data-bbox-variant={variant}
      sx={{
        position: "absolute",
        left,
        top,
        width: Math.max(width, 2),
        height: Math.max(height, 2),
        border: 2,
        borderStyle: inferred ? "dashed" : "solid",
        borderColor: inferred
          ? (active ? "info.main" : "info.light")
          : (active ? "error.main" : "warning.main"),
        bgcolor: inferred
          ? (active ? "rgba(2, 136, 209, 0.16)" : "rgba(2, 136, 209, 0.08)")
          : (active ? "rgba(211, 47, 47, 0.18)" : "rgba(237, 108, 2, 0.12)"),
        borderRadius: 0.5,
        pointerEvents: "none",
        boxShadow: active && !inferred
          ? "0 0 0 2px rgba(211, 47, 47, 0.35)"
          : active && inferred
            ? "0 0 0 2px rgba(2, 136, 209, 0.3)"
            : "none",
        zIndex: 2,
        "&::after": inferred
          ? {
              content: '"Inferred"',
              position: "absolute",
              top: -18,
              left: 0,
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0.3,
              color: "info.main",
              bgcolor: "background.paper",
              px: 0.5,
              borderRadius: 0.5,
              lineHeight: 1.4,
            }
          : undefined,
      }}
    />
  );
}

/** Compute CSS page width so the bbox fills ~half the pane (clamped). */
export function pageWidthForBbox({
  boundingBox,
  pageWidthPts,
  containerWidth,
  fillRatio = 0.5,
  minWidth,
  maxWidth,
}) {
  const fallback = Math.max(320, containerWidth || 640);
  const minW = minWidth ?? Math.max(280, fallback * 0.85);
  const maxW = maxWidth ?? Math.max(minW, fallback * 4);
  if (
    !boundingBox
    || boundingBox.length < 4
    || !pageWidthPts
    || pageWidthPts <= 0
  ) {
    return Math.min(maxW, Math.max(minW, fallback));
  }
  const boxWidthPts = Math.max(Math.abs(boundingBox[2] - boundingBox[0]), 8);
  const target = ((containerWidth || fallback) * fillRatio * pageWidthPts)
    / boxWidthPts;
  return Math.min(maxW, Math.max(minW, target));
}
