import axios from "axios";

/**
 * Single API entry point.
 *
 * An empty `VITE_API_BASE` keeps requests same-origin so the Vite dev proxy
 * handles them. Never hardcode a host or port in a component.
 */
const baseURL = import.meta.env.VITE_API_BASE || "";

const client = axios.create({
  baseURL,
  withCredentials: false,
  // Analysis of a full drawing set can legitimately run for minutes.
  timeout: 15 * 60 * 1000,
});

function describeError(error, label) {
  const status = error.response?.status;
  const detail = error.response?.data?.detail;
  if (detail) return typeof detail === "string" ? detail : JSON.stringify(detail);
  if (status) return `${label} failed with HTTP ${status}.`;
  if (error.code === "ECONNABORTED") {
    return `${label} timed out before the server replied.`;
  }
  return (
    `${label} could not reach the API. Confirm the backend is running and ` +
    `that the dev server proxy is active.`
  );
}

/**
 * The one multipart implementation. Every upload path uses this so progress
 * reporting, logging, and error handling stay identical.
 */
async function postMultipart(path, fields, { onUploadProgress, label } = {}) {
  const name = label || path;
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value) form.append(key, value);
  }

  console.info(`[upload] ${name}: uploading…`, {
    path,
    files: Object.entries(fields)
      .filter(([, value]) => value)
      .map(([key, value]) => `${key}=${value.name} (${value.size} bytes)`),
  });
  const startedAt = performance.now();
  try {
    // Content-Type is intentionally left to the browser so the multipart
    // boundary is generated correctly.
    const { data } = await client.post(path, form, {
      onUploadProgress: (event) => {
        if (event.total) {
          const percent = Math.round((event.loaded * 100) / event.total);
          if (percent === 100) console.info(`[upload] ${name}: transfer complete`);
        }
        onUploadProgress?.(event);
      },
    });
    console.info(
      `[upload] ${name}: completed in ${Math.round(performance.now() - startedAt)}ms`,
    );
    return data;
  } catch (error) {
    const message = describeError(error, name);
    console.error(`[upload] ${name}: failed — ${message}`, error);
    error.friendlyMessage = message;
    throw error;
  }
}

export async function uploadPdf(file, onUploadProgress) {
  return postMultipart(
    "/api/documents",
    { file },
    { onUploadProgress, label: "Drawing upload" },
  );
}

export async function getDocument(documentId) {
  const { data } = await client.get(
    `/api/documents/${encodeURIComponent(documentId)}`,
  );
  return data;
}

/** Same-origin URL for the registered drawing PDF (proxied in Vite). */
export function documentPdfUrl(documentId) {
  return `${baseURL}/api/documents/${encodeURIComponent(documentId)}/pdf`;
}

/** Time a stage request so a slow drawing is visible instead of silent. */
async function timedRequest(label, request) {
  console.info(`[stage] ${label}: started`);
  const startedAt = performance.now();
  try {
    const data = await request();
    console.info(
      `[stage] ${label}: completed in ${Math.round(performance.now() - startedAt)}ms`,
    );
    return data;
  } catch (error) {
    const message = describeError(error, label);
    console.error(`[stage] ${label}: failed — ${message}`, error);
    error.friendlyMessage = message;
    throw error;
  }
}

export async function extractDocument(documentId, force = false) {
  return timedRequest("Extraction", async () => {
    const { data } = await client.post(
      `/api/documents/${encodeURIComponent(documentId)}/extract`,
      null,
      { params: force ? { force: true } : undefined },
    );
    return data;
  });
}

function normalizeAnalysis(data) {
  const results = (data.predictions || []).map((prediction) => ({
    ...prediction,
    token: prediction.raw_text || prediction.original_token,
    validation: {
      status:
        (data.validation?.tokens || []).find(
          (item) => item.component_id === prediction.component_id,
        )?.status || "WARNING",
    },
  }));
  const confidenceLevels = { High: 0, Medium: 0, Low: 0 };
  const classDistribution = {};
  for (const result of results) {
    const level = result.confidence?.level || "Low";
    confidenceLevels[level] = (confidenceLevels[level] || 0) + 1;
    const section = result.section || result.predicted_shape;
    if (section) classDistribution[section] = (classDistribution[section] || 0) + 1;
  }
  return {
    ...data,
    filename: data.source_file,
    pages: data.summary?.pages,
    token_count: results.length,
    results,
    summary: {
      ...data.summary,
      confidence_levels: confidenceLevels,
      class_distribution: classDistribution,
      database_matches: results.filter((item) => item.database_match).length,
    },
    multimodal: {
      document_id: data.document_id,
      performance: data.performance,
      validation: data.validation?.summary,
      extraction_quality: data.extraction?.quality,
    },
  };
}

export async function restoreDocument(documentId) {
  const encoded = encodeURIComponent(documentId);
  const { data: document } = await client.get(`/api/documents/${encoded}`);
  let extraction = null;
  let analysis = null;
  if (["extracted", "analyzing", "analyzed"].includes(document.stage)) {
    extraction = (
      await client.get(`/api/documents/${encoded}/extraction`)
    ).data;
  }
  if (document.stage === "analyzed") {
    analysis = normalizeAnalysis(
      (await client.get(`/api/documents/${encoded}/analysis`)).data,
    );
  }
  return { document, extraction, analysis };
}

export async function analyzeDocument(
  documentId,
  excelFile = null,
  onUploadProgress,
  force = false,
) {
  const data = await postMultipart(
    `/api/documents/${encodeURIComponent(documentId)}/analyze${
      force ? "?force=true" : ""
    }`,
    { excel: excelFile },
    { onUploadProgress, label: "Multimodal analysis" },
  );
  return normalizeAnalysis(data);
}

export async function getUnknownTokens(status = "pending") {
  const { data } = await client.get("/api/unknown-tokens", { params: { status } });
  return data;
}

export async function approveToken(id, reviewedClass, notes = "", reviewedCategory = null) {
  const { data } = await client.post("/api/approve-token", {
    id,
    reviewed_class: reviewedClass || null,
    reviewed_category: reviewedCategory || null,
    notes,
  });
  return data;
}

export async function rejectToken(id, notes = "") {
  const { data } = await client.post("/api/reject-token", { id, notes });
  return data;
}

export async function reviewBatch(ids, action, reviewedClass = null, reviewedCategory = null) {
  const { data } = await client.post("/api/review-batch", {
    ids,
    action,
    reviewed_class: reviewedClass,
    reviewed_category: reviewedCategory,
  });
  return data;
}

export async function startRetrain() {
  const { data } = await client.post("/api/retrain/start");
  return data;
}

export async function getRetrainStatus() {
  const { data } = await client.get("/api/retrain/status");
  return data;
}

export async function getContinuousLearningStatus() {
  const { data } = await client.get("/api/continuous-learning/status");
  return data;
}

export async function getDynamicRegex(category) {
  const { data } = await client.get("/api/dynamic-regex", {
    params: category ? { category } : undefined,
  });
  return data;
}

export async function getStatistics() {
  const { data } = await client.get("/api/statistics");
  return data;
}

export async function getHistory(limit = 100) {
  const { data } = await client.get("/api/history", { params: { limit } });
  return data;
}

export async function buildPairedDataset(pairIds = null) {
  const { data } = await client.post("/api/takeoff/dataset/build", {
    pair_ids: pairIds,
  });
  return data;
}

export async function getPairedDatasetSummary() {
  const { data } = await client.get("/api/takeoff/dataset/summary");
  return data;
}

export async function generateTakeoff(documentId) {
  const { data } = await client.post("/api/takeoff/generate", {
    document_id: documentId,
  });
  return data;
}

export function takeoffDownloadUrl(filename) {
  return `${baseURL}/api/takeoff/exports/${encodeURIComponent(filename)}`;
}

export async function approveValidationCorrection({
  documentId,
  objectId,
  correctLabel,
  prediction = {},
  features = {},
  notes = "",
  correctGeometry = null,
  semanticType = "",
  userDecision = "approve",
}) {
  const { data } = await client.post("/api/engineering/corrections", {
    document_id: documentId || null,
    object_id: objectId || null,
    correct_label: correctLabel,
    prediction,
    features,
    correct_geometry: correctGeometry,
    user_decision: userDecision,
    notes,
    semantic_type: semanticType || null,
  });
  return data;
}

export async function getDataQuality() {
  const { data } = await client.get("/api/data-quality");
  return data;
}
