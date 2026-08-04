import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { analyzeDocument, extractDocument, getDocument } from "../api/client";

const AnalysisContext = createContext(null);

// Only a small, stable identifier — never the PDF binary or the full
// analysis payload — so refreshing the tab can rehydrate from the backend
// (which already caches extraction/analysis artifacts) without ever writing
// large or sensitive data into browser storage.
const STORAGE_KEY = "steelTakeoff.workflow.v1";

function readPersistedWorkflow() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writePersistedWorkflow(value) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable (private browsing, quota) — workflow just won't survive a refresh */
  }
}

// Shown when extract/analyze restoration fails specifically because the
// backend rejected the request with 404 — the manifest still exists, but the
// underlying uploaded PDF no longer does (pruned by upload-store retention).
// Distinct from a generic network/server error so the user gets an accurate
// next step instead of a guess.
const MISSING_SOURCE_MESSAGE =
  "The original uploaded file is no longer available. Upload the PDF again " +
  "and run the analysis to restore provenance.";
const RESTORE_FAILED_MESSAGE =
  "The previous analysis could not be restored. Start a new analysis to continue.";

function isMissingSourceFileError(error) {
  return error?.response?.status === 404;
}

function restoreNoticeFor(error) {
  return isMissingSourceFileError(error)
    ? { kind: "missing-source", message: MISSING_SOURCE_MESSAGE }
    : { kind: "restore-failed", message: RESTORE_FAILED_MESSAGE };
}

export function AnalysisProvider({ children }) {
  const [document, setDocument] = useState(null);
  const [extraction, setExtraction] = useState(null);
  const [data, setData] = useState(null);
  const [rehydrating, setRehydrating] = useState(true);
  const [rehydrationError, setRehydrationError] = useState(null);
  const [restoreNotice, setRestoreNotice] = useState(null);

  const clearData = () => {
    setDocument(null);
    setExtraction(null);
    setData(null);
    setRestoreNotice(null);
    writePersistedWorkflow(null);
  };

  // Explicit, user-triggered reset — distinct from clearData(), which some
  // internal flows (e.g. uploading a new PDF) call without the user having
  // asked to abandon the workflow's persisted identifier.
  const startNewAnalysis = () => {
    clearData();
    setRehydrationError(null);
  };

  useEffect(() => {
    const persisted = readPersistedWorkflow();
    if (!persisted?.documentId) {
      setRehydrating(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const manifest = await getDocument(persisted.documentId);
        if (cancelled) return;
        setDocument(manifest);

        if (["extracted", "analyzing", "analyzed", "failed"].includes(manifest.stage)) {
          try {
            const extractionResult = await extractDocument(persisted.documentId, false);
            if (cancelled) return;
            setExtraction(extractionResult);
          } catch (error) {
            // Extraction artifact may have been pruned since the tab was left
            // open, or the source PDF itself may no longer be in the upload
            // store. Either way, the workflow restarts from this step — but
            // the reason is preserved instead of silently vanishing.
            if (cancelled) return;
            setRestoreNotice(restoreNoticeFor(error));
          }
        }

        if (manifest.stage === "analyzed") {
          try {
            const analysisResult = await analyzeDocument(persisted.documentId, null, undefined, false);
            if (cancelled) return;
            setData(analysisResult);
            setRestoreNotice(null);
          } catch (error) {
            // Same as above — cached analysis artifacts (or the source PDF
            // behind them) may be gone. Surface why instead of leaving the
            // consuming page to show an unexplained blank state.
            if (cancelled) return;
            setRestoreNotice(restoreNoticeFor(error));
          }
        }
      } catch {
        if (!cancelled) {
          setRehydrationError(
            "Could not restore the previous document — it may have expired. Start a new analysis.",
          );
          writePersistedWorkflow(null);
        }
      } finally {
        if (!cancelled) setRehydrating(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // Runs once on mount only — this is a one-time rehydration pass.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!document?.document_id) return;
    writePersistedWorkflow({
      documentId: document.document_id,
      stage: data ? "analyzed" : extraction ? "extracted" : "uploaded",
    });
  }, [document, extraction, data]);

  const value = useMemo(
    () => ({
      document,
      setDocument,
      extraction,
      setExtraction,
      data,
      setData,
      clearData,
      startNewAnalysis,
      rehydrating,
      rehydrationError,
      restoreNotice,
      setRestoreNotice,
      stage: data
        ? "analyzed"
        : extraction
          ? "extracted"
          : document
            ? "uploaded"
            : "empty",
    }),
    [data, document, extraction, rehydrating, rehydrationError, restoreNotice],
  );
  return <AnalysisContext.Provider value={value}>{children}</AnalysisContext.Provider>;
}

export function useAnalysis() {
  const context = useContext(AnalysisContext);
  if (!context) throw new Error("useAnalysis must be used within AnalysisProvider");
  return context;
}
