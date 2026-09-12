import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  ButtonGroup,
  CircularProgress,
  Divider,
  FormControlLabel,
  Grid,
  Paper,
  Stack,
  Switch,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { PlayArrowOutlined, RefreshOutlined } from "@mui/icons-material";
import {
  documentPdfUrl,
  getSemanticDocument,
  processSemanticDocument,
  reviewSemanticAnnotation,
} from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import PdfDocumentViewer from "../components/pdf/PdfDocumentViewer";
import DocumentSummaryBar from "../components/semantic/DocumentSummaryBar";
import AnnotationInspector from "../components/semantic/AnnotationInspector";
import ReviewQueue from "../components/semantic/ReviewQueue";
import DocumentIntelligencePanel from "../components/semantic/DocumentIntelligencePanel";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import {
  annotationsForPage,
  getOverlayStyle,
  needsReviewAnnotations,
} from "../lib/semanticContract";

// Falls back to the precomputed demo drawing when no document is active in
// this session yet (Section 26: reliability over live processing for the
// stakeholder demo) -- this is real, captured pipeline output, not
// invented data; see backend/scripts/generate_demo_semantic_fixture.py.
const DEMO_DOCUMENT_ID = "doc_47dc7ef27f6e5d7e";
const DEFAULT_PAGE = 5;

export default function SemanticReviewPage() {
  const { document: activeDocument } = useAnalysis();
  const documentId = activeDocument?.document_id || DEMO_DOCUMENT_ID;
  const pdfUrl = documentPdfUrl(documentId);

  const [semanticDoc, setSemanticDoc] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState(null);

  const [selectedAnnotationId, setSelectedAnnotationId] = useState(null);
  const [viewerOverride, setViewerOverride] = useState(null); // {page, boundingBox} from "View source"
  const [currentPage, setCurrentPage] = useState(DEFAULT_PAGE);
  const [tab, setTab] = useState("review");
  const [reviewBusy, setReviewBusy] = useState(false);

  const [showFragments, setShowFragments] = useState(false);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getSemanticDocument(documentId);
      setSemanticDoc(result.document);
      setSummary(result.summary);
    } catch (err) {
      if (err.response?.status === 404) {
        setSemanticDoc(null);
        setSummary(null);
      } else {
        setError(err.friendlyMessage || "Could not load the semantic result.");
      }
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleProcess = async (force = false) => {
    setProcessing(true);
    setError(null);
    try {
      const result = await processSemanticDocument(documentId, force);
      setSemanticDoc(result.document);
      setSummary(result.summary);
    } catch (err) {
      setError(err.friendlyMessage || "Semantic processing failed.");
    } finally {
      setProcessing(false);
    }
  };

  const selectedAnnotation = useMemo(
    () => semanticDoc?.annotations?.find((a) => a.annotation_id === selectedAnnotationId) || null,
    [semanticDoc, selectedAnnotationId],
  );

  const handleSelectAnnotation = useCallback((annotation) => {
    setSelectedAnnotationId(annotation.annotation_id);
    setViewerOverride(null);
    setCurrentPage(annotation.page);
  }, []);

  const handleViewSource = useCallback((page, bbox) => {
    setViewerOverride({ page, boundingBox: bbox });
    setCurrentPage(page);
  }, []);

  // The quick page-jump buttons must actually scroll the viewer there, not
  // just change which page's overlays are filtered in -- otherwise a
  // presenter opening the page fresh has to manually scroll past dozens of
  // sheets to reach the demo page (found during this session's browser QA).
  // Reuses the same anchor a real annotation click would target: the first
  // annotation on that page.
  const handleJumpToPage = useCallback((page) => {
    setCurrentPage(page);
    const target = semanticDoc?.annotations?.find((a) => a.page === page && a.semantic_bbox);
    setViewerOverride(target ? { page, boundingBox: target.semantic_bbox } : null);
  }, [semanticDoc]);

  const handleReview = async (action, editedText) => {
    if (!selectedAnnotation) return;
    setReviewBusy(true);
    try {
      await reviewSemanticAnnotation(documentId, selectedAnnotation.annotation_id, action, editedText);
      await load();
    } catch (err) {
      setError(err.friendlyMessage || "Could not save the review action.");
    } finally {
      setReviewBusy(false);
    }
  };

  const pageAnnotations = useMemo(
    () => (semanticDoc ? annotationsForPage(semanticDoc, currentPage) : []),
    [semanticDoc, currentPage],
  );

  const overlays = useMemo(() => {
    const list = needsReviewOnly
      ? pageAnnotations.filter((a) => a.review_status === "needs_review")
      : pageAnnotations;
    const built = [];
    for (const annotation of list) {
      if (!annotation.semantic_bbox) continue;
      const style = getOverlayStyle(annotation);
      built.push({
        key: annotation.annotation_id,
        pageNumber: annotation.page,
        boundingBox: annotation.semantic_bbox,
        variant: style.colorKey,
        dashed: style.dashed,
        badge: style.badge,
        badgeTitle: `${annotation.primary_label} — ${annotation.correction.operation}`,
        onClick: () => handleSelectAnnotation(annotation),
      });
      if (showFragments) {
        for (const fragment of annotation.source_fragments || []) {
          built.push({
            key: `${annotation.annotation_id}-frag-${fragment.primitive_id}`,
            pageNumber: annotation.page,
            boundingBox: fragment.bbox,
            variant: "neutral",
            dashed: true,
            badge: null,
            badgeTitle: fragment.text,
            onClick: () => handleSelectAnnotation(annotation),
          });
        }
      }
    }
    return built;
  }, [pageAnnotations, showFragments, needsReviewOnly, handleSelectAnnotation]);

  // This document is dozens of full-size sheets mounted at once (see
  // PdfDocumentViewer's own note on `zoomFillRatio`/`zoomMaxMultiplier`) --
  // a gentle zoom keeps every cross-page jump (View source, page-jump
  // buttons) responsive instead of forcing an expensive simultaneous
  // re-render of every page's canvas at a large magnification (reproduced
  // and fixed during this session's browser QA).
  const GENTLE_ZOOM = { zoomFillRatio: 0.15, zoomMaxMultiplier: 1.4 };

  const viewerSelection = useMemo(() => {
    if (viewerOverride) {
      return {
        key: `source-${viewerOverride.page}-${viewerOverride.boundingBox?.join(",")}`,
        pageNumber: viewerOverride.page,
        boundingBox: viewerOverride.boundingBox,
        variant: "success",
        ...GENTLE_ZOOM,
      };
    }
    if (selectedAnnotation?.semantic_bbox) {
      return {
        key: selectedAnnotation.annotation_id,
        pageNumber: selectedAnnotation.page,
        boundingBox: selectedAnnotation.semantic_bbox,
        variant: getOverlayStyle(selectedAnnotation).colorKey,
        ...GENTLE_ZOOM,
      };
    }
    return null;
  }, [viewerOverride, selectedAnnotation]);

  const reviewQueue = useMemo(
    () => (semanticDoc ? needsReviewAnnotations(semanticDoc) : []),
    [semanticDoc],
  );

  return (
    <Stack spacing={2}>
      <PageHeader
        title="Semantic Review"
        subtitle="What this annotation means, why it changed, and what evidence supports it — upstream of the Rhino/Grasshopper takeoff workflow."
      />

      {error && <Alert severity="warning" onClose={() => setError(null)}>{error}</Alert>}

      {!loading && !semanticDoc && (
        <EmptyState
          icon={PlayArrowOutlined}
          title="No semantic result yet"
          subtitle="Run the semantic preprocessor against this drawing to extract, group, normalize, repair, and complete its structural labels."
          action={
            <Button
              variant="contained"
              startIcon={processing ? <CircularProgress size={16} color="inherit" /> : <PlayArrowOutlined />}
              onClick={() => handleProcess(false)}
              disabled={processing}
            >
              {processing ? "Processing…" : "Process drawing"}
            </Button>
          }
        />
      )}

      {loading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress size={28} />
        </Box>
      )}

      {semanticDoc && (
        <>
          <DocumentSummaryBar summary={summary} />

          {/* A bounded height here is load-bearing, not cosmetic: the PDF
              viewer's own "fit page" sizing measures its scroll container's
              clientHeight via ResizeObserver, and this GCDC drawing's real
              sheets are large native-point sizes. Without an explicit cap,
              an unconstrained flex ancestor lets the container grow to fit
              all rendered pages, which the viewer then reads back as
              "available height" -- ballooning the canvas further in a
              feedback loop (reproduced during this session's demo QA). See
              DrawingReviewPage's identical `calc(100vh - Npx)` pattern. */}
          <Grid container spacing={2} sx={{ height: "68vh", minHeight: 560 }}>
            {/* minHeight: 0 is load-bearing, not redundant with the inner
                Box's own minHeight: 0 -- this Grid item is itself a flex
                item of the (height-bounded) Grid container above, and a
                flex item's default `min-height: auto` lets its OWN box grow
                to fit its content's natural size, overriding the stretched
                cross-axis height the container tried to give it. Without
                this, the PDF viewer (and everything below it on the page)
                inherits the full un-clipped height of all 81 rendered
                sheets -- reproduced and root-caused during this session's
                browser QA (see PdfDocumentViewer's own zoomFillRatio note
                for the matching render-cost half of this problem). */}
            <Grid size={{ xs: 12, md: 8 }} sx={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%" }}>
              <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" sx={{ mb: 1 }}>
                <FormControlLabel
                  control={<Switch size="small" checked={showFragments} onChange={(e) => setShowFragments(e.target.checked)} />}
                  label={<Typography variant="body2">Source fragments</Typography>}
                />
                <FormControlLabel
                  control={<Switch size="small" checked={needsReviewOnly} onChange={(e) => setNeedsReviewOnly(e.target.checked)} />}
                  label={<Typography variant="body2">Needs review only</Typography>}
                />
                <ButtonGroup size="small" sx={{ ml: "auto" }}>
                  {[DEFAULT_PAGE, 58].map((p) => (
                    <Button
                      key={p}
                      variant={currentPage === p ? "contained" : "outlined"}
                      onClick={() => handleJumpToPage(p)}
                    >
                      Page {p}
                    </Button>
                  ))}
                </ButtonGroup>
                <Button
                  size="small"
                  startIcon={<RefreshOutlined fontSize="small" />}
                  onClick={() => handleProcess(true)}
                  disabled={processing}
                >
                  Reprocess
                </Button>
              </Stack>
              <Box sx={{ flex: 1, minHeight: 0 }}>
                <PdfDocumentViewer
                  fileUrl={pdfUrl}
                  selection={viewerSelection}
                  overlays={overlays}
                />
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                Showing annotations for page {currentPage} ({pageAnnotations.length}
                {needsReviewOnly ? " needing review" : ""}). Use the page buttons above,
                or click an annotation, to change focus.
              </Typography>
            </Grid>

            <Grid size={{ xs: 12, md: 4 }}>
              <Paper
                variant="outlined"
                data-testid="annotation-inspector"
                sx={{ p: 2, height: "100%", overflowY: "auto" }}
              >
                <AnnotationInspector
                  document={semanticDoc}
                  annotation={selectedAnnotation}
                  onViewSource={handleViewSource}
                  onReview={handleReview}
                  busy={reviewBusy}
                />
              </Paper>
            </Grid>
          </Grid>

          <Divider />

          <Tabs value={tab} onChange={(_, value) => setTab(value)}>
            <Tab value="review" label={`Needs review (${reviewQueue.length})`} />
            <Tab value="intelligence" label="Document intelligence" />
          </Tabs>
          {tab === "review" ? (
            <ReviewQueue
              items={reviewQueue}
              selectedId={selectedAnnotationId}
              onSelect={handleSelectAnnotation}
            />
          ) : (
            <DocumentIntelligencePanel document={semanticDoc} onViewSource={handleViewSource} />
          )}
        </>
      )}
    </Stack>
  );
}
