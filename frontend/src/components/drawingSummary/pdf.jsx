import { lazy, Suspense } from "react";
import { Box, CircularProgress } from "@mui/material";
import { documentPdfUrl } from "../../api/client";

// pdf.js only loads when a source page is actually opened.
const PdfDocumentViewer = lazy(() => import("../pdf/PdfDocumentViewer"));

/** One source page of the uploaded PDF with its box highlighted (display space). */
export function SourcePdf({ documentId, source, selectionKey }) {
  return (
    <Suspense
      fallback={(
        <Box sx={{ display: "grid", placeItems: "center", height: "100%" }}>
          <CircularProgress size={28} />
        </Box>
      )}
    >
      <PdfDocumentViewer
        fileUrl={documentPdfUrl(documentId)}
        pageWindow={1}
        selection={{ key: selectionKey, pageNumber: source.page, boundingBox: source.bbox || null }}
      />
    </Suspense>
  );
}
