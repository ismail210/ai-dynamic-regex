import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { ZoomIn, ZoomOut } from "@mui/icons-material";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import BboxHighlight, { computeFitPageWidth, pageWidthForBbox } from "./BboxHighlight";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const MIN_PAGE_WIDTH = 240;
const ZOOM_STEP = 1.5;

/**
 * Multi-page PDF viewer with bbox highlight and zoom-to-selection.
 *
 * `selection` shape: `{ pageNumber, boundingBox, key }`
 * pageNumber is 1-based (matches backend / pdf.js).
 *
 * Deliberately small state model -- exactly one mode owns `pageWidth` at a
 * time, and `currentPage` is tracked explicitly rather than derived, so
 * zooming can never accidentally change which page is being viewed:
 *
 * - "fit-page" (default): whole page visible, aspect ratio preserved.
 * - "manual-zoom": user-controlled via the zoom in/out buttons, same page.
 * - "selection-zoom": zoomed in on the selected label, driven by
 *   pageWidthForBbox.
 */
export default function PdfDocumentViewer({
  fileUrl,
  selection = null,
}) {
  const containerRef = useRef(null);
  const pageRefs = useRef({});
  const [numPages, setNumPages] = useState(0);
  const [loadError, setLoadError] = useState(null);
  const [pageSizes, setPageSizes] = useState({});
  const [containerSize, setContainerSize] = useState({ width: 720, height: 540 });
  const [pageWidth, setPageWidth] = useState(720);
  const [mode, setMode] = useState("fit-page");
  // The page being viewed. Set on mount and whenever a NEW selection lands
  // on a different page -- and ONLY there. Zooming (in/out or back to Fit
  // Page) must never touch this.
  const [currentPage, setCurrentPage] = useState(1);
  // { key, pageNumber, width } for a selection whose scroll-into-view is
  // waiting on react-pdf to finish (re)rendering the target page's canvas
  // at the new zoomed width -- see the onRenderSuccess handler below.
  const pendingScrollRef = useRef(null);
  // { [pageNumber]: width } the width each page has ACTUALLY finished
  // rendering its canvas at, per onRenderSuccess -- deliberately separate
  // from the `pageWidth` state (the REQUESTED width). `pageWidth` updates
  // the instant setPageWidth is called, well before react-pdf has painted
  // anything at that size, so comparing against it (instead of this ref)
  // would make the effect below think "already rendered" immediately after
  // requesting a new zoom -- reproducing the exact premature-scroll race
  // this whole mechanism exists to avoid.
  const renderedWidthsRef = useRef({});
  // Which selection.key has already been acted on, so a new selection
  // triggers zoom-to-label exactly once, not every time unrelated state
  // (e.g. another page finishing its own load) re-runs this effect.
  const lastHandledSelectionKeyRef = useRef(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;
    const measure = () =>
      setContainerSize({
        width: Math.max(280, Math.floor(node.clientWidth - 8)),
        height: Math.max(200, Math.floor(node.clientHeight - 8)),
      });
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    measure();
    return () => observer.disconnect();
  }, []);

  const currentPageSize = pageSizes[currentPage];

  // The one effect that computes Fit Page's width -- only while that mode
  // is active, only for currentPage. Never fires as a side effect of
  // zooming or selecting; those are separate, explicit actions below.
  useEffect(() => {
    if (mode !== "fit-page") return;
    setPageWidth(
      computeFitPageWidth({
        pageWidthPts: currentPageSize?.width,
        pageHeightPts: currentPageSize?.height,
        availableWidth: containerSize.width,
        availableHeight: containerSize.height,
        minWidth: MIN_PAGE_WIDTH,
      }),
    );
  }, [mode, containerSize, currentPageSize?.width, currentPageSize?.height]);

  // Scrolls the highlight into view. Only safe to call once react-pdf's
  // canvas has actually finished (re)rendering at `pageWidth` -- see the
  // race this fixes, below.
  //
  // Centers the highlight but CLAMPS to the container's real scroll range,
  // which is why this computes offsets itself instead of using
  // scrollIntoView({block:"center"}): a label near a page edge has no scroll
  // offset that puts it in the middle, so the centered request resolved to
  // nothing usable and members along the sheet border could never be
  // located. Scrolling the container directly also keeps the movement inside
  // the viewer -- scrollIntoView walks every scrollable ancestor, dragging
  // the surrounding review layout with it.
  const scrollToSelection = useCallback((pageNumber) => {
    const container = containerRef.current;
    const pageNode = pageRefs.current[pageNumber];
    if (!container || !pageNode) return;
    const target =
      pageNode.querySelector('[data-bbox-highlight="active"]') || pageNode;
    const containerBox = container.getBoundingClientRect();
    const targetBox = target.getBoundingClientRect();

    const centered = (offset, targetStart, containerStart, viewport, size) =>
      offset + (targetStart - containerStart) - (viewport - size) / 2;
    const clamp = (value, max) => Math.max(0, Math.min(value, Math.max(0, max)));

    const left = clamp(
      centered(
        container.scrollLeft,
        targetBox.left,
        containerBox.left,
        container.clientWidth,
        targetBox.width,
      ),
      container.scrollWidth - container.clientWidth,
    );
    const top = clamp(
      centered(
        container.scrollTop,
        targetBox.top,
        containerBox.top,
        container.clientHeight,
        targetBox.height,
      ),
      container.scrollHeight - container.clientHeight,
    );

    if (typeof container.scrollTo === "function") {
      container.scrollTo({ left, top, behavior: "smooth" });
      return;
    }
    container.scrollLeft = left;
    container.scrollTop = top;
  }, []);

  // A NEW selection takes over the view: navigate to its page, switch to
  // "selection-zoom", and zoom in enough to read the label clearly
  // (pageWidthForBbox floors at Fit Page and scales up from there -- see
  // BboxHighlight.jsx), then scroll it into view once rendered.
  //
  // The scroll must not fire until react-pdf's <Page> has actually finished
  // repainting its canvas at the NEW zoomed width: the scrollable
  // container's scrollWidth/scrollHeight only grow once that repaint
  // completes, so scrolling any earlier computes the target against the
  // page's OLD (smaller) extents and clamps short -- the highlight ends up
  // correctly positioned in the DOM but outside the viewport, which is
  // exactly what made "locating" a label look like it silently failed. A
  // fixed setTimeout delay used to paper over this, but a dense page (lots
  // of text/geometry) can take longer to rasterize than a simple one, so a
  // constant delay is inherently unreliable. Waiting for the real
  // onRenderSuccess signal (below) instead of guessing a delay fixes it for
  // every page, not just fast-rendering ones.
  //
  // This effect depends on `pageSizes`, which is shared across every page
  // in the document (all ~30 pages of a real drawing set mount and load
  // concurrently) -- so it keeps re-running for a while after a selection
  // as OTHER, unrelated pages finish loading, well after this selection's
  // own zoom was already applied. The lastHandledSelectionKeyRef guard
  // below is what stops each of those re-runs from recomputing the SAME
  // zoom and silently overwriting a reviewer's very next Fit Page/zoom
  // click a moment later.
  useEffect(() => {
    if (!selection?.pageNumber || !selection?.boundingBox) {
      pendingScrollRef.current = null;
      lastHandledSelectionKeyRef.current = null;
      return undefined;
    }
    if (lastHandledSelectionKeyRef.current === selection.key) {
      return undefined;
    }
    const pageNumber = Number(selection.pageNumber);
    const size = pageSizes[pageNumber];
    if (!size?.width) return undefined; // not loaded yet; retry when pageSizes updates

    lastHandledSelectionKeyRef.current = selection.key;
    setCurrentPage(pageNumber);
    setMode("selection-zoom");

    const nextWidth = pageWidthForBbox({
      boundingBox: selection.boundingBox,
      pageWidthPts: size.width,
      pageHeightPts: size.height,
      availableWidth: containerSize.width,
      availableHeight: containerSize.height,
    });

    if (Math.abs(nextWidth - (renderedWidthsRef.current[pageNumber] ?? -1)) < 0.5) {
      // This exact page has ALREADY finished rendering at (approximately)
      // the target width -- e.g. selecting a different label on the same
      // page/zoom level -- so no new onRenderSuccess will fire to trigger
      // the scroll. Defer one frame so the (unchanged) highlight has
      // committed to the DOM first.
      pendingScrollRef.current = null;
      const raf = window.requestAnimationFrame(() => scrollToSelection(pageNumber));
      return () => window.cancelAnimationFrame(raf);
    }

    pendingScrollRef.current = {
      key: selection.key,
      pageNumber,
      width: nextWidth,
    };
    setPageWidth(nextWidth);
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- containerSize
    // intentionally omitted: a resize while a selection is active should
    // not re-trigger this effect's zoom math (see the Fit Page effect's own
    // comment on the same tradeoff).
  }, [selection?.key, selection?.pageNumber, selection?.boundingBox, pageSizes, scrollToSelection]);

  // Manual zoom: same page, no mode fighting -- just scales pageWidth from
  // wherever it currently is, and does a best-effort job of keeping the
  // same point roughly centered (PDF viewers don't jump to a corner on
  // zoom). Never touches currentPage or selection.
  const zoomBy = useCallback((factor) => {
    const node = containerRef.current;
    const before = node && node.scrollWidth > 0 && node.scrollHeight > 0
      ? {
          xFrac: (node.scrollLeft + node.clientWidth / 2) / node.scrollWidth,
          yFrac: (node.scrollTop + node.clientHeight / 2) / node.scrollHeight,
        }
      : null;

    setMode("manual-zoom");
    setPageWidth((prev) => {
      const nativeWidth = currentPageSize?.width || prev;
      const maxWidth = nativeWidth * 6;
      return Math.min(maxWidth, Math.max(MIN_PAGE_WIDTH, prev * factor));
    });

    if (node && before) {
      // Two frames: one for React to commit the new width prop, one for
      // the browser to reflow the (still-old-canvas) layout before we read
      // scrollWidth/Height again. Approximate on purpose -- "reasonably
      // centered", not pixel-perfect (that's what selection-zoom + the
      // onRenderSuccess sync above is for).
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          node.scrollLeft = before.xFrac * node.scrollWidth - node.clientWidth / 2;
          node.scrollTop = before.yFrac * node.scrollHeight - node.clientHeight / 2;
        });
      });
    }
  }, [currentPageSize?.width]);

  const onDocumentLoadSuccess = useCallback(({ numPages: next }) => {
    setNumPages(next);
    setLoadError(null);
  }, []);

  const pages = useMemo(
    () => Array.from({ length: numPages }, (_, index) => index + 1),
    [numPages],
  );

  if (!fileUrl) {
    return (
      <Alert severity="info" variant="outlined">
        No drawing PDF is available for this document.
      </Alert>
    );
  }

  return (
    <Box
      data-testid="pdf-viewer-root"
      data-current-page={currentPage}
      data-view-mode={mode}
      sx={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}
    >
      <Stack
        direction="row"
        spacing={0.5}
        sx={{ justifyContent: "flex-end", alignItems: "center", pb: 0.75 }}
      >
        <Tooltip title="Show the entire sheet">
          <Button
            size="small"
            variant={mode === "fit-page" ? "contained" : "outlined"}
            onClick={() => setMode("fit-page")}
          >
            Fit page
          </Button>
        </Tooltip>
        <Tooltip title="Zoom in">
          <IconButton size="small" onClick={() => zoomBy(ZOOM_STEP)}>
            <ZoomIn fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Zoom out">
          <IconButton size="small" onClick={() => zoomBy(1 / ZOOM_STEP)}>
            <ZoomOut fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
      <Box
        ref={containerRef}
        data-testid="pdf-scroll-container"
        sx={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
          bgcolor: "action.hover",
          borderRadius: 2,
          border: 1,
          borderColor: "divider",
          p: 1.5,
        }}
      >
        {loadError && (
          <Alert severity="error" sx={{ mb: 1.5 }}>
            {loadError}
          </Alert>
        )}
        <Document
          file={fileUrl}
          loading={
            // react-pdf clones/wraps this element internally (via its Message
            // component) rather than rendering it as an ordinary child, which
            // dropped MUI's Stack-specific prop handling and forwarded
            // `alignItems` straight through to a DOM node. sx-based styling
            // compiles to CSS at build time, so there is no component prop
            // left for that wrapping to strip.
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                py: 6,
                gap: 1.5,
              }}
            >
              <CircularProgress size={28} />
              <Typography variant="body2" color="text.secondary">
                Loading drawing…
              </Typography>
            </Box>
          }
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={(error) => {
            setLoadError(error?.message || "Could not load the drawing PDF.");
          }}
        >
          {/* react-pdf's <Document> wraps its children in its own internal
              container rather than rendering them as ordinary React children,
              which drops MUI Stack's component-level prop handling and
              forwards `alignItems` straight through to a DOM node (same root
              cause as the `loading` prop above) — sx-based flex styling sidesteps
              it entirely. */}
          {/* width:max-content is what makes zoomed-in pages fully
              scrollable. A centered flex item that is WIDER than its flex
              container overflows equally on both sides, and the left overflow
              sits at a negative offset that scrollLeft can never reach -- so
              once a sheet was zoomed past the panel width, labels near its
              left edge were clipped away with no way to scroll back to them.
              Sizing this wrapper to its widest page means the page never
              overflows the wrapper (centering stays safe for pages narrower
              than the panel, via minWidth), and the wrapper itself starts at
              scroll offset 0, so the entire sheet is reachable. */}
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              width: "max-content",
              minWidth: "100%",
            }}
          >
            {pages.map((pageNumber) => {
              const isSelectedPage =
                selection?.pageNumber != null
                && Number(selection.pageNumber) === pageNumber;
              const size = pageSizes[pageNumber];
              return (
                <Box
                  key={pageNumber}
                  ref={(node) => {
                    pageRefs.current[pageNumber] = node;
                  }}
                  data-pdf-page={pageNumber}
                  sx={{
                    position: "relative",
                    boxShadow: isSelectedPage ? 4 : 1,
                    bgcolor: "background.paper",
                    outline: isSelectedPage ? "2px solid" : "none",
                    outlineColor: "primary.main",
                  }}
                >
                  <Page
                    pageNumber={pageNumber}
                    width={pageWidth}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    onLoadSuccess={(page) => {
                      const viewport = page.getViewport({ scale: 1 });
                      setPageSizes((prev) => ({
                        ...prev,
                        [pageNumber]: {
                          width: viewport.width,
                          height: viewport.height,
                        },
                      }));
                    }}
                    onRenderSuccess={() => {
                      renderedWidthsRef.current[pageNumber] = pageWidth;
                      const pending = pendingScrollRef.current;
                      if (
                        pending
                        && pending.pageNumber === pageNumber
                        && Math.abs(pending.width - pageWidth) < 0.5
                      ) {
                        pendingScrollRef.current = null;
                        scrollToSelection(pageNumber);
                      }
                    }}
                  />
                  {isSelectedPage && selection?.boundingBox && size?.width ? (
                    <BboxHighlight
                      boundingBox={selection.boundingBox}
                      pageWidthPts={size.width}
                      renderedWidth={pageWidth}
                      active
                      variant={selection.variant || "text"}
                    />
                  ) : null}
                  <Typography
                    variant="caption"
                    sx={{
                      position: "absolute",
                      top: 6,
                      left: 8,
                      px: 0.75,
                      py: 0.15,
                      borderRadius: 1,
                      bgcolor: "rgba(15,23,42,0.72)",
                      color: "#fff",
                      zIndex: 3,
                    }}
                  >
                    Page {pageNumber}
                  </Typography>
                </Box>
              );
            })}
          </Box>
        </Document>
      </Box>
    </Box>
  );
}
