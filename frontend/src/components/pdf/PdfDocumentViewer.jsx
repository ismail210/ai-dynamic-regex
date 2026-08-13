import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Box, CircularProgress, Typography } from "@mui/material";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import BboxHighlight, { pageWidthForBbox } from "./BboxHighlight";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

/**
 * Multi-page PDF viewer with bbox highlight and zoom-to-selection.
 *
 * `selection` shape: `{ pageNumber, boundingBox, key }`
 * pageNumber is 1-based (matches backend / pdf.js).
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
  const [containerWidth, setContainerWidth] = useState(720);
  const [pageWidth, setPageWidth] = useState(720);
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

  useEffect(() => {
    const node = containerRef.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width;
      if (width && Number.isFinite(width)) {
        setContainerWidth(Math.max(280, Math.floor(width - 8)));
      }
    });
    observer.observe(node);
    setContainerWidth(Math.max(280, Math.floor(node.clientWidth - 8)));
    return () => observer.disconnect();
  }, []);

  // Default fit-to-pane width when nothing is selected.
  useEffect(() => {
    if (!selection?.boundingBox) {
      setPageWidth(Math.max(320, containerWidth));
    }
  }, [containerWidth, selection?.key, selection?.boundingBox]);

  // Scrolls the page + highlight into view. Only safe to call once
  // react-pdf's canvas has actually finished (re)rendering at `pageWidth`
  // -- see the race this fixes, below.
  const scrollToSelection = useCallback((pageNumber) => {
    const pageNode = pageRefs.current[pageNumber];
    if (!pageNode) return;
    pageNode.scrollIntoView({ behavior: "smooth", block: "center" });
    const highlight = pageNode.querySelector('[data-bbox-highlight="active"]');
    highlight?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
  }, []);

  // Zoom so the selected bbox fills ~half the pane, then scroll into view.
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
  useEffect(() => {
    if (!selection?.pageNumber || !selection?.boundingBox) {
      pendingScrollRef.current = null;
      return undefined;
    }
    const pageNumber = Number(selection.pageNumber);
    const size = pageSizes[pageNumber];
    if (!size?.width) return undefined;

    const nextWidth = pageWidthForBbox({
      boundingBox: selection.boundingBox,
      pageWidthPts: size.width,
      containerWidth,
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
  }, [
    selection?.key,
    selection?.pageNumber,
    selection?.boundingBox,
    pageSizes,
    containerWidth,
    scrollToSelection,
  ]);

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
      ref={containerRef}
      sx={{
        height: "100%",
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
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
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
  );
}
