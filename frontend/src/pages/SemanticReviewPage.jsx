import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  ButtonGroup,
  CircularProgress,
  Divider,
  Grid,
  Paper,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { DownloadOutlined, PlayArrowOutlined, RefreshOutlined, ScienceOutlined } from "@mui/icons-material";
import {
  acceptAllSemanticCorrections,
  correctedSemanticPdfUrl,
  documentPdfUrl,
  downloadCorrectedSemanticPdf,
  getBenchmarkContext,
  getSemanticDocument,
  processSemanticDocument,
  reviewSemanticAnnotation,
} from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import PdfDocumentViewer from "../components/pdf/PdfDocumentViewer";
import AnnotationInspector from "../components/semantic/AnnotationInspector";
import ReviewQueue from "../components/semantic/ReviewQueue";
import DocumentIntelligencePanel from "../components/semantic/DocumentIntelligencePanel";
import DamageCaseBar from "../components/semantic/DamageCaseBar";
import CorrectionHistoryPanel from "../components/semantic/CorrectionHistoryPanel";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import {
  annotationsForPage,
  getAcceptTargetText,
  getOverlayStyle,
  isReviewOverlayCandidate,
  structuralActionQueue,
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
  const originalPdfUrl = documentPdfUrl(documentId);

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

  const [damageFilter, setDamageFilter] = useState("all");
  const [damageCaseIndex, setDamageCaseIndex] = useState(0);
  const [saveStatus, setSaveStatus] = useState(null); // null | "saving" | "saved" | "error"
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadMessage, setDownloadMessage] = useState(null);
  const [pdfRevision, setPdfRevision] = useState(null);
  const autoProcessedRef = useRef(null);

  const correctedMeta = summary?.corrected_pdf;
  const pdfUrl = useMemo(() => {
    const revision = pdfRevision || correctedMeta?.revision;
    if (correctedMeta?.available && revision && revision !== "none") {
      return correctedSemanticPdfUrl(documentId, revision);
    }
    return originalPdfUrl;
  }, [documentId, originalPdfUrl, correctedMeta?.available, correctedMeta?.revision, pdfRevision]);

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
      const rev = result?.summary?.corrected_pdf;
      setPdfRevision(rev?.available ? rev.revision : null);
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

  useEffect(() => {
    setPdfRevision(null);
  }, [documentId]);

  // When a result arrives, focus a page that actually has annotations.
  // Hard-coded page 5/58 made short controlled-test PDFs render blank/black.
  useEffect(() => {
    if (!semanticDoc?.annotations?.length) return;
    setCurrentPage((prev) => {
      if (annotationsForPage(semanticDoc, prev).length > 0) return prev;
      const actions = structuralActionQueue(semanticDoc);
      const target =
        actions[0]
        || semanticDoc.annotations.find(isReviewOverlayCandidate)
        || semanticDoc.annotations[0];
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
      const rev = result?.summary?.corrected_pdf;
      setPdfRevision(rev?.available ? rev.revision : null);
      setProcessing(false);
      // Corrected PDF may still be warming in the background. Soft-swap when ready
      // without keeping the "Processing…" spinner up.
      if (!rev?.available && (result?.summary?.accepted_correction_count || 0) > 0) {
        for (let i = 0; i < 8; i += 1) {
          await new Promise((r) => setTimeout(r, 1500));
          try {
            const again = await getSemanticDocument(documentId);
            const next = again?.summary?.corrected_pdf;
            if (next?.available) {
              setSummary(again.summary);
              setPdfRevision(next.revision);
              break;
            }
          } catch {
            break;
          }
        }
      }
    } catch (err) {
      setProcessing(false);
      setError(err.friendlyMessage || "Semantic processing failed.");
    }
  };

  // Damage-test PDFs: run Process automatically once so Accept / Reject /
  // Download corrected PDF appear without an extra click.
  useEffect(() => {
    if (loading || processing || semanticDoc) return;
    if (!damageManifest) return;
    if (autoProcessedRef.current === documentId) return;
    autoProcessedRef.current = documentId;
    handleProcess(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per damage doc when empty
  }, [loading, processing, semanticDoc, damageManifest, documentId]);

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

  const applyCorrectedPdfMeta = useCallback((meta, nextSummary) => {
    setSummary((prev) => {
      const base = nextSummary || prev || {};
      return meta ? { ...base, corrected_pdf: meta } : (nextSummary || prev);
    });
    const revision = meta?.revision || nextSummary?.corrected_pdf?.revision || null;
    setPdfRevision(meta?.available && revision && revision !== "none" ? revision : null);
  }, []);

  const handleReview = async (action, editedText, candidateText) => {
    const target = selectedAnnotation || activeDamagePair?.annotation;
    if (!target) return;
    setReviewBusy(true);
    setSaveStatus("saving");
    setError(null);

    // Paint the corrected label on the PDF immediately — do not wait for the
    // corrected-PDF rebuild (that can take seconds on multi-page sheets).
    const priorDoc = semanticDoc;
    let optimisticText = null;
    if (action === "edit" && editedText) {
      optimisticText = editedText;
    } else if (action === "accept") {
      optimisticText = candidateText
        || getAcceptTargetText(target, activeDamageCase)
        || target.effective_text;
    } else if (action === "reject") {
      optimisticText = target.original_text || target.correction?.original || target.primary_label;
    }
    if (priorDoc && optimisticText) {
      const optimisticStatus = action === "reject" ? "human_rejected" : "human_accepted";
      setSemanticDoc({
        ...priorDoc,
        annotations: priorDoc.annotations.map((a) => (
          a.annotation_id === target.annotation_id
            ? {
              ...a,
              effective_text: optimisticText,
              review_status: optimisticStatus,
              correction: {
                ...(a.correction || {}),
                original: a.original_text || a.correction?.original || a.primary_label,
                canonical: optimisticText,
                operation: action === "reject" ? (a.correction?.operation || "keep") : "repair",
              },
            }
            : a
        )),
      });
    }

    try {
      const result = await reviewSemanticAnnotation(
        documentId,
        target.annotation_id,
        action,
        editedText,
        candidateText,
      );
      const updated = result?.annotation;
      if (updated) {
        setSemanticDoc((doc) => {
          const base = doc || priorDoc;
          if (!base) return doc;
          return {
            ...base,
            annotations: base.annotations.map((a) =>
              (a.annotation_id === updated.annotation_id ? updated : a),
            ),
          };
        });
        setSelectedAnnotationId(updated.annotation_id);
      }
      applyCorrectedPdfMeta(result?.corrected_pdf, result?.summary);
      setSaveStatus("saved");
      if (result?.corrected_pdf?.available) {
        setDownloadMessage(`Corrected PDF updated (rev ${result.corrected_pdf.revision})`);
      }
    } catch (err) {
      if (priorDoc) setSemanticDoc(priorDoc);
      setSaveStatus("error");
      setError(err.friendlyMessage || "Could not save the review action.");
    } finally {
      setReviewBusy(false);
    }
  };

  const handleAcceptAll = async () => {
    setReviewBusy(true);
    setSaveStatus("saving");
    setError(null);
    try {
      const result = await acceptAllSemanticCorrections(documentId);
      if (result?.document) setSemanticDoc(result.document);
      applyCorrectedPdfMeta(result?.corrected_pdf, result?.summary);
      setSaveStatus("saved");
      setDownloadMessage(
        `Accepted ${result?.accepted_count ?? 0} correction(s); corrected PDF regenerated.`,
      );
    } catch (err) {
      setSaveStatus("error");
      setError(err.friendlyMessage || "Accept All failed.");
    } finally {
      setReviewBusy(false);
    }
  };

  const handleDownloadCorrectedPdf = async () => {
    setDownloadBusy(true);
    setDownloadMessage("Generating corrected PDF…");
    setError(null);
    try {
      const { filename } = await downloadCorrectedSemanticPdf(documentId);
      setDownloadMessage(`Corrected PDF ready (${filename})`);
    } catch (err) {
      setDownloadMessage(null);
      setError(err.friendlyMessage || "Could not download the corrected PDF.");
    } finally {
      setDownloadBusy(false);
    }
  };

  const acceptedCorrectionCount = summary?.accepted_correction_count ?? 0;

  const pageAnnotations = useMemo(
    () => (semanticDoc ? annotationsForPage(semanticDoc, currentPage) : []),
    [semanticDoc, currentPage],
  );

  const overlays = useMemo(() => {
    // Never paint every token on the sheet — that floods the viewer with
    // orange dots. Damage PDFs: only matched test cases + selection.
    // Ordinary docs: only structural corrections / geometry / incomplete.
    let list;
    if (damageManifest) {
      const damageIds = new Set(
        damagePairs
          .filter(
            (pair) =>
              pair.annotation
              && Number(pair.testCase.source_page) === Number(currentPage),
          )
          .map((pair) => pair.annotation.annotation_id),
      );
      list = pageAnnotations.filter(
        (annotation) =>
          annotation.annotation_id === selectedAnnotationId
          || damageIds.has(annotation.annotation_id),
      );
    } else {
      list = pageAnnotations.filter(isReviewOverlayCandidate);
      if (
        selectedAnnotation
        && Number(selectedAnnotation.page) === Number(currentPage)
        && !list.some((a) => a.annotation_id === selectedAnnotationId)
      ) {
        list = [...list, selectedAnnotation];
      }
    }

    const built = [];
    for (const annotation of list) {
      if (!annotation.semantic_bbox) continue;
      const style = getOverlayStyle(annotation);
      const effective = annotation.effective_text || annotation.primary_label;
      const original = annotation.original_text || annotation.correction?.original;
      const showCorrectedLabel = (
        ["human_accepted", "auto_accepted"].includes(annotation.review_status)
        && Boolean(effective)
        && Boolean(original)
        && String(effective).trim() !== String(original).trim()
      );
      built.push({
        key: annotation.annotation_id,
        pageNumber: annotation.page,
        boundingBox: annotation.semantic_bbox,
        variant: showCorrectedLabel ? "success" : style.colorKey,
        dashed: showCorrectedLabel ? false : style.dashed,
        badge: showCorrectedLabel ? null : style.badge,
        badgeTitle: `${effective} — ${annotation.correction?.operation || "correction"}`,
        labelText: showCorrectedLabel ? effective : null,
        onClick: () => handleSelectAnnotation(annotation),
      });
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
    damageManifest,
    damagePairs,
    selectedAnnotationId,
    selectedAnnotation,
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

  const actionQueue = useMemo(
    () => (semanticDoc ? structuralActionQueue(semanticDoc) : []),
    [semanticDoc],
  );

  const caseTableItems = useMemo(() => {
    if (damageManifest && filteredDamagePairs.length) {
      return filteredDamagePairs.map((pair) => {
        const ann = pair.annotation;
        const testCase = pair.testCase;
        const original = ann?.correction?.original || testCase.test_text || testCase.original_text;
        const proposed = (
          (ann && getAcceptTargetText(ann, testCase))
          || testCase.intended_semantic_result
          || testCase.expected_normalized
          || ann?.correction?.canonical
          || null
        );
        return {
          annotation_id: ann?.annotation_id || testCase.test_case_id,
          row_key: testCase.test_case_id,
          page: testCase.source_page,
          correction: {
            original,
            canonical: proposed && proposed !== original ? proposed : (ann?.correction?.canonical || original),
            operation: ann ? (ann.correction?.operation || "keep") : "keep",
          },
          repair_candidates: ann?.repair_candidates || [],
          geometry_associations: ann?.geometry_associations || [],
          review_status: ann?.review_status || "pending",
          _damagePair: pair,
        };
      });
    }
    return actionQueue;
  }, [damageManifest, filteredDamagePairs, actionQueue]);

  const jumpPages = useMemo(() => {
    if (damageManifest?.changed_pages?.length) {
      return [...damageManifest.changed_pages].sort((a, b) => a - b).slice(0, 8);
    }
    if (!semanticDoc?.annotations?.length) return [1];
    const pages = [...new Set(semanticDoc.annotations.map((a) => Number(a.page)).filter((p) => p >= 1))];
    pages.sort((a, b) => a - b);
    if (pages.length <= 4) return pages;
    const actionPages = [
      ...new Set(actionQueue.map((a) => Number(a.page)).filter((p) => p >= 1)),
    ].sort((a, b) => a - b);
    const pick = new Set([pages[0], pages[pages.length - 1]]);
    if (actionPages[0]) pick.add(actionPages[0]);
    if (actionPages[Math.floor(actionPages.length / 2)]) {
      pick.add(actionPages[Math.floor(actionPages.length / 2)]);
    }
    return [...pick].sort((a, b) => a - b);
  }, [semanticDoc, actionQueue, damageManifest]);

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
      <Box sx={{ flex: 1, minHeight: 0 }}>
        <PdfDocumentViewer
          fileUrl={pdfUrl}
          selection={viewerSelection}
          overlays={overlays}
          pageWindow={1}
          zoomOnSelect={false}
        />
      </Box>
    </Paper>
  );

  return (
    <Stack spacing={2}>
      <PageHeader
        title="Semantic Review"
        subtitle={drawingLabel}
        actions={(
            <Stack direction="row" spacing={1} alignItems="center">
              {saveStatus === "saving" && (
                <Typography variant="caption" color="text.secondary">Saving…</Typography>
              )}
              {saveStatus === "saved" && (
                <Typography variant="caption" color="success.main" data-testid="save-status-saved">
                  ✓ Correction saved
                </Typography>
              )}
              {saveStatus === "error" && (
                <Typography variant="caption" color="warning.main">⚠ Could not save correction</Typography>
              )}
              <Button
                variant="outlined"
                size="small"
                disabled={reviewBusy || !semanticDoc}
                onClick={handleAcceptAll}
                data-testid="accept-all-corrections"
              >
                Accept All
              </Button>
              <Button
                variant="contained"
                size="small"
                startIcon={downloadBusy ? <CircularProgress size={14} color="inherit" /> : <DownloadOutlined />}
                disabled={downloadBusy || acceptedCorrectionCount < 1}
                onClick={handleDownloadCorrectedPdf}
                data-testid="download-corrected-pdf"
                title={
                  !semanticDoc
                    ? "Process the drawing, then Accept corrections to enable download"
                    : acceptedCorrectionCount < 1
                      ? "Accept at least one correction first"
                      : "Download original PDF + all accepted corrections"
                }
              >
                Download corrected PDF
              </Button>
            </Stack>
          )}
      />

      {error && <Alert severity="warning" onClose={() => setError(null)}>{error}</Alert>}

      {damageManifest && (
        <Alert severity="info" icon={<ScienceOutlined fontSize="small" />} data-testid="damage-corpus-banner">
          Controlled damage test PDF ({damageManifest.project}). In-place mutations on real drawing
          callouts — not a customer document. Expected values in the inspector are test metadata only.
          {!semanticDoc && !processing && " Click Process drawing (or wait — damage PDFs auto-start processing)."}
          {processing && " Processing now… Accept / Reject appear when finished."}
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
            title={processing ? "Processing drawing…" : "Process this drawing to unlock review"}
            subtitle={
              processing
                ? "Extracting labels, normalizing, and attaching repair proposals. Accept / Reject / Manual edit and Download corrected PDF appear when this finishes."
                : "Step 1: Process drawing. Step 2: Accept / Reject / Manual edit in the inspector. Step 3: Download corrected PDF. The PDF preview below is the original until you Accept corrections."
            }
            action={
              <Button
                variant="contained"
                startIcon={processing ? <CircularProgress size={16} color="inherit" /> : <PlayArrowOutlined />}
                onClick={() => handleProcess(false)}
                disabled={processing}
                data-testid="process-drawing"
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
          {downloadMessage && (
            <Alert severity="success" onClose={() => setDownloadMessage(null)} data-testid="download-ready">
              {downloadMessage}
            </Alert>
          )}

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
          <Grid container spacing={2} sx={{ height: "70vh", minHeight: 560 }}>
            <Grid size={{ xs: 12, md: 8 }} sx={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%" }}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                <ButtonGroup size="small">
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
                  sx={{ ml: "auto" }}
                >
                  Reprocess
                </Button>
              </Stack>
              {pdfViewer}
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                {correctedMeta?.available
                  ? `Viewing corrected PDF (rev ${correctedMeta.revision}) — ${correctedMeta.correction_count} applied correction(s)`
                  : overlays.length
                    ? `${overlays.length} highlight${overlays.length === 1 ? "" : "s"} on page ${currentPage}`
                    : `Page ${currentPage} — use case navigator or repair queue to focus a label`}
              </Typography>
            </Grid>

            <Grid size={{ xs: 12, md: 4 }} sx={{ minHeight: 0, height: "100%" }}>
              <Paper
                variant="outlined"
                data-testid="annotation-inspector"
                sx={{ p: 1.5, height: "100%", overflowY: "auto" }}
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
            <Tab
              value="review"
              label={damageManifest
                ? `All cases (${caseTableItems.length})`
                : `Repair queue (${actionQueue.length})`}
            />
            <Tab value="history" label="Correction history" />
            <Tab value="intelligence" label="Document intelligence" />
          </Tabs>
          {tab === "review" ? (
            <ReviewQueue
              items={caseTableItems}
              selectedId={selectedAnnotationId || activeDamageCase?.test_case_id}
              onSelect={(item) => {
                if (item._damagePair) {
                  const idx = filteredDamagePairs.findIndex(
                    (p) => p.testCase.test_case_id === item._damagePair.testCase.test_case_id,
                  );
                  if (idx >= 0) setDamageCaseIndex(idx);
                  focusDamageCase(item._damagePair);
                  return;
                }
                handleSelectAnnotation(item);
              }}
            />
          ) : tab === "history" ? (
            <CorrectionHistoryPanel document={semanticDoc} />
          ) : (
            <DocumentIntelligencePanel document={semanticDoc} onViewSource={handleViewSource} />
          )}
        </>
      )}
    </Stack>
  );
}
