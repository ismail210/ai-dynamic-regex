import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Box, CircularProgress, Stack, Typography } from "@mui/material";
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

  // Zoom so the selected bbox fills ~half the pane, then scroll into view.
  useEffect(() => {
    if (!selection?.pageNumber || !selection?.boundingBox) return undefined;
    const pageNumber = Number(selection.pageNumber);
    const size = pageSizes[pageNumber];
    if (!size?.width) return undefined;

    const nextWidth = pageWidthForBbox({
      boundingBox: selection.boundingBox,
      pageWidthPts: size.width,
      containerWidth,
    });
    setPageWidth(nextWidth);

    const timer = window.setTimeout(() => {
      const pageNode = pageRefs.current[pageNumber];
      if (!pageNode) return;
      pageNode.scrollIntoView({ behavior: "smooth", block: "center" });
      const highlight = pageNode.querySelector('[data-bbox-highlight="active"]');
      highlight?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [
    selection?.key,
    selection?.pageNumber,
    selection?.boundingBox,
    pageSizes,
    containerWidth,
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
          <Stack alignItems="center" py={6} spacing={1.5}>
            <CircularProgress size={28} />
            <Typography variant="body2" color="text.secondary">
              Loading drawing…
            </Typography>
          </Stack>
        }
        onLoadSuccess={onDocumentLoadSuccess}
        onLoadError={(error) => {
          setLoadError(error?.message || "Could not load the drawing PDF.");
        }}
      >
        <Stack spacing={2} alignItems="center">
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
        </Stack>
      </Document>
    </Box>
  );
}
