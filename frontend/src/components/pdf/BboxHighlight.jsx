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
 * Rendered page width (px) for viewing a selected bbox: fits the whole
 * page (Fit Page) UNLESS the bbox would render too small to read at that
 * scale, in which case it zooms in only as far as needed for legibility --
 * capped well below "fill half the viewport" so the reviewer keeps
 * surrounding drawing context instead of the label filling the screen.
 */
export function pageWidthForBbox({
  boundingBox,
  pageWidthPts,
  pageHeightPts,
  availableWidth,
  availableHeight,
  minLegibleHeightPx = 26,
  maxZoomMultiplier = 2.5,
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
  const fitScale = fitWidth / pageWidthPts;
  const boxHeightPts = Math.max(Math.abs(boundingBox[3] - boundingBox[1]), 1);
  const renderedAtFit = boxHeightPts * fitScale;
  if (renderedAtFit >= minLegibleHeightPx) {
    // Already readable with the whole page visible -- no extra zoom.
    return fitWidth;
  }
  const neededScale = minLegibleHeightPx / boxHeightPts;
  const zoomedWidth = pageWidthPts * neededScale;
  return Math.min(zoomedWidth, fitWidth * maxZoomMultiplier);
}
