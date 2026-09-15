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
import { PlayArrowOutlined, RefreshOutlined, ScienceOutlined } from "@mui/icons-material";
import {
  documentPdfUrl,
  getBenchmarkContext,
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
import DamageCaseBar from "../components/semantic/DamageCaseBar";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import {
  annotationsForPage,
  getOverlayStyle,
  needsReviewAnnotations,
} from "../lib/semanticContract";
import {
  caseMatchesFilter,
  damageCorpusSummary,
  pairCasesWithAnnotations,
  resolveDamageManifest,
} from "../lib/semanticDamageManifest";

// Prefer the active analysis document. Demo fallback remains for empty sessions.
const DEMO_DOCUMENT_ID = "doc_47dc7ef27f6e5d7e";

export default function SemanticReviewPage() {
  const { document: activeDocument } = useAnalysis();
  const documentId = activeDocument?.document_id || DEMO_DOCUMENT_ID;
  const pdfUrl = documentPdfUrl(documentId);

  const [semanticDoc, setSemanticDoc] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [benchmarkContext, setBenchmarkContext] = useState(null);

  const [selectedAnnotationId, setSelectedAnnotationId] = useState(null);
  const [viewerOverride, setViewerOverride] = useState(null); // {page, boundingBox} from "View source"
  const [currentPage, setCurrentPage] = useState(1);
  const [tab, setTab] = useState("review");
  const [reviewBusy, setReviewBusy] = useState(false);

  const [showFragments, setShowFragments] = useState(false);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [damageFilter, setDamageFilter] = useState("all");
  const [damageCaseIndex, setDamageCaseIndex] = useState(0);

  const drawingLabel =
    activeDocument?.original_filename ||
    activeDocument?.source_file ||
    documentId;

  const damageManifest = useMemo(
    () => resolveDamageManifest(drawingLabel),
    [drawingLabel],
  );

  const damagePairs = useMemo(
    () => (damageManifest ? pairCasesWithAnnotations(damageManifest, semanticDoc) : []),
    [damageManifest, semanticDoc],
  );

  const filteredDamagePairs = useMemo(
    () => damagePairs.filter((pair) => caseMatchesFilter(pair, damageFilter)),
    [damagePairs, damageFilter],
  );

  const damageSummary = useMemo(
    () => (damagePairs.length ? damageCorpusSummary(damagePairs) : null),
    [damagePairs],
  );

  const activeDamagePair = filteredDamagePairs[damageCaseIndex] || null;
  const activeDamageCase = activeDamagePair?.testCase || null;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getSemanticDocument(documentId);
      // Backend returns 200 + document:null when not processed yet (not 404).
      setSemanticDoc(result?.document ?? null);
      setSummary(result?.summary ?? null);
    } catch (err) {
      // Legacy 404 (older servers) and unknown-document 404 both mean empty.
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

  // When a result arrives, focus a page that actually has annotations.
  // Hard-coded page 5/58 made short controlled-test PDFs render blank/black.
  useEffect(() => {
    if (!semanticDoc?.annotations?.length) return;
    setCurrentPage((prev) => {
      if (annotationsForPage(semanticDoc, prev).length > 0) return prev;
      const needs = needsReviewAnnotations(semanticDoc);
      const target = needs[0] || semanticDoc.annotations[0];
      const page = Number(target?.page);
      return Number.isFinite(page) && page >= 1 ? page : 1;
    });
  }, [semanticDoc]);

  // Keep case index in range when the filter changes.
  useEffect(() => {
    setDamageCaseIndex(0);
  }, [damageFilter, damageManifest?.output_pdf]);

  useEffect(() => {
    if (damageCaseIndex >= filteredDamagePairs.length && filteredDamagePairs.length > 0) {
      setDamageCaseIndex(0);
    }
  }, [filteredDamagePairs.length, damageCaseIndex]);

  // Dev/demo only (Section 34/35): silently no-ops (null) for any ordinary
  // document -- this must never affect or delay normal Semantic Review use.
  useEffect(() => {
    let cancelled = false;
    getBenchmarkContext(documentId)
      .then((context) => {
        if (!cancelled) setBenchmarkContext(context);
      })
      .catch(() => {
        if (!cancelled) setBenchmarkContext(null);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

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
  //
  // No boundingBox on purpose: a page jump means "show me this page", not
  // "zoom into one specific label on it" -- passing a bbox here used to
  // route through PdfDocumentViewer's zoom-to-selection path, which forces
  // a document-wide canvas re-render on every jump (expensive on a
  // real multi-sheet set, and the actual cause of the viewer
  // freezing/oscillating between an unfit and an overzoomed page that was
  // reported and reproduced this session). Passing pageNumber alone
  // navigates and scrolls to that page at whatever width Fit Page/manual
  // zoom already has -- see PdfDocumentViewer's selection effect.
  const handleJumpToPage = useCallback((page) => {
    setCurrentPage(page);
    setViewerOverride({ page, boundingBox: null });
  }, []);

  const focusDamageCase = useCallback((pair) => {
    if (!pair?.testCase) return;
    const { testCase, annotation } = pair;
    const page = Number(testCase.source_page) || 1;
    setCurrentPage(page);
    if (annotation) {
      setSelectedAnnotationId(annotation.annotation_id);
      setViewerOverride(null);
      return;
    }
    setSelectedAnnotationId(null);
    const bbox = testCase.modified_bbox || testCase.original_bbox || null;
    setViewerOverride({ page, boundingBox: bbox });
  }, []);

  const handleDamagePrev = useCallback(() => {
    if (!filteredDamagePairs.length) return;
    const next = (damageCaseIndex - 1 + filteredDamagePairs.length) % filteredDamagePairs.length;
    setDamageCaseIndex(next);
    focusDamageCase(filteredDamagePairs[next]);
  }, [damageCaseIndex, filteredDamagePairs, focusDamageCase]);

  const handleDamageNext = useCallback(() => {
    if (!filteredDamagePairs.length) return;
    const next = (damageCaseIndex + 1) % filteredDamagePairs.length;
    setDamageCaseIndex(next);
    focusDamageCase(filteredDamagePairs[next]);
  }, [damageCaseIndex, filteredDamagePairs, focusDamageCase]);

  // When user picks an overlay annotation, sync the damage case index if it matches.
  useEffect(() => {
    if (!selectedAnnotationId || !filteredDamagePairs.length) return;
    const idx = filteredDamagePairs.findIndex(
      (pair) => pair.annotation?.annotation_id === selectedAnnotationId,
    );
    if (idx >= 0 && idx !== damageCaseIndex) setDamageCaseIndex(idx);
  }, [selectedAnnotationId, filteredDamagePairs, damageCaseIndex]);

  const handleReview = async (action, editedText, candidateText) => {
    if (!selectedAnnotation) return;
    setReviewBusy(true);
    try {
      await reviewSemanticAnnotation(documentId, selectedAnnotation.annotation_id, action, editedText, candidateText);
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
    // Manifest bbox fallback when the controlled case is not yet matched.
    if (
      activeDamageCase
      && !activeDamagePair?.annotation
      && Number(activeDamageCase.source_page) === Number(currentPage)
    ) {
      const bbox = activeDamageCase.modified_bbox || activeDamageCase.original_bbox;
      if (bbox) {
        built.push({
          key: `damage-${activeDamageCase.test_case_id}`,
          pageNumber: activeDamageCase.source_page,
          boundingBox: bbox,
          variant: "warning",
          dashed: true,
          badge: "T",
          badgeTitle: `${activeDamageCase.test_text} (test case)`,
          onClick: () => focusDamageCase(activeDamagePair),
        });
      }
    }
    return built;
  }, [
    pageAnnotations,
    showFragments,
    needsReviewOnly,
    handleSelectAnnotation,
    activeDamageCase,
    activeDamagePair,
    currentPage,
    focusDamageCase,
  ]);

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
    if (activeDamageCase?.modified_bbox || activeDamageCase?.original_bbox) {
      return {
        key: `damage-${activeDamageCase.test_case_id}`,
        pageNumber: activeDamageCase.source_page,
        boundingBox: activeDamageCase.modified_bbox || activeDamageCase.original_bbox,
        variant: "warning",
        ...GENTLE_ZOOM,
      };
    }
    return null;
  }, [viewerOverride, selectedAnnotation, activeDamageCase]);

  const reviewQueue = useMemo(
    () => (semanticDoc ? needsReviewAnnotations(semanticDoc) : []),
    [semanticDoc],
  );

  const jumpPages = useMemo(() => {
    if (damageManifest?.changed_pages?.length) {
      return [...damageManifest.changed_pages].sort((a, b) => a - b).slice(0, 8);
    }
    if (!semanticDoc?.annotations?.length) return [1];
    const pages = [...new Set(semanticDoc.annotations.map((a) => Number(a.page)).filter((p) => p >= 1))];
    pages.sort((a, b) => a - b);
    // Prefer a short strip: first, a mid needs-review page, last.
    if (pages.length <= 4) return pages;
    const needsPages = [
      ...new Set(reviewQueue.map((a) => Number(a.page)).filter((p) => p >= 1)),
    ].sort((a, b) => a - b);
    const pick = new Set([pages[0], pages[pages.length - 1]]);
    if (needsPages[0]) pick.add(needsPages[0]);
    if (needsPages[Math.floor(needsPages.length / 2)]) {
      pick.add(needsPages[Math.floor(needsPages.length / 2)]);
    }
    return [...pick].sort((a, b) => a - b);
  }, [semanticDoc, reviewQueue, damageManifest]);

  const pdfViewer = (
    <Paper
      variant="outlined"
      sx={{
        flex: 1,
        minHeight: 0,
        height: "100%",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        p: 1,
        bgcolor: "background.paper",
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ px: 0.5, pb: 0.75 }}>
        {drawingLabel}
      </Typography>
      <Box sx={{ flex: 1, minHeight: 0 }}>
        <PdfDocumentViewer
          fileUrl={pdfUrl}
          selection={viewerSelection}
          overlays={overlays}
        />
      </Box>
    </Paper>
  );

  return (
    <Stack spacing={2}>
      <PageHeader
        title="Semantic Review"
        subtitle="What this annotation means, why it changed, and what evidence supports it — upstream of the Rhino/Grasshopper takeoff workflow."
      />

      {error && <Alert severity="warning" onClose={() => setError(null)}>{error}</Alert>}

      {damageManifest && (
        <Alert severity="info" icon={<ScienceOutlined fontSize="small" />} data-testid="damage-corpus-banner">
          Controlled damage test PDF ({damageManifest.project}). In-place mutations on real drawing
          callouts — not a customer document. Expected values in the inspector are test metadata only.
        </Alert>
      )}

      {damageSummary && (
        <DamageCaseBar
          summary={damageSummary}
          filterId={damageFilter}
          onFilterChange={setDamageFilter}
          caseIndex={Math.min(damageCaseIndex, Math.max(filteredDamagePairs.length - 1, 0))}
          caseCount={filteredDamagePairs.length}
          currentCase={activeDamageCase}
          onPrev={handleDamagePrev}
          onNext={handleDamageNext}
        />
      )}

      {!loading && !semanticDoc && (
        <Stack spacing={2}>
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
          <Box sx={{ height: "52vh", minHeight: 360, display: "flex", flexDirection: "column" }}>
            {pdfViewer}
          </Box>
        </Stack>
      )}

      {loading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress size={28} />
        </Box>
      )}

      {semanticDoc && (
        <>
          <DocumentSummaryBar summary={summary} />

          {benchmarkContext && (
            <Alert severity="info" icon={<ScienceOutlined fontSize="small" />} data-testid="benchmark-banner">
              <b>Attack Benchmark</b> — controlled corrupted PDF, source: real cleaned project (
              {benchmarkContext.source_pdf}). {benchmarkContext.mutation_count} mutations,{" "}
              {benchmarkContext.clean_control_count} clean controls. Not a customer document.
            </Alert>
          )}

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
                  {jumpPages.map((p) => (
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
              {pdfViewer}
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                Showing annotations for page {currentPage} ({pageAnnotations.length}
                {needsReviewOnly ? " needing review" : ""}). Use the page buttons above,
                case navigator, or click an annotation to change focus.
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
                  annotation={selectedAnnotation || activeDamagePair?.annotation || null}
                  onViewSource={handleViewSource}
                  onReview={handleReview}
                  busy={reviewBusy}
                  documentId={documentId}
                  benchmarkContext={benchmarkContext}
                  damageCase={activeDamageCase}
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
