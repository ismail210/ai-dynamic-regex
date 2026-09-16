/**
 * Client-side loader for in-repo Semantic Damage Test manifests.
 * Expected values are TEST METADATA only — never feed them into the pipeline.
 */
import indexEntries from "../fixtures/semanticDamage/index.json";
import burrville from "../fixtures/semanticDamage/burrville_SEMANTIC_DAMAGE_TEST.manifest.json";
import st from "../fixtures/semanticDamage/st_SEMANTIC_DAMAGE_TEST.manifest.json";
import structure from "../fixtures/semanticDamage/structure_SEMANTIC_DAMAGE_TEST.manifest.json";

const BY_STEM = {
  burrville_SEMANTIC_DAMAGE_TEST: burrville,
  st_SEMANTIC_DAMAGE_TEST: st,
  structure_SEMANTIC_DAMAGE_TEST: structure,
};

export const DAMAGE_FILTERS = [
  { id: "all", label: "All" },
  { id: "repair", label: "Damaged / Repair" },
  { id: "normalization", label: "Normalization" },
  { id: "incomplete", label: "Incomplete" },
  { id: "clean", label: "Clean" },
  { id: "reviewed", label: "Reviewed" },
];

const REPAIR_CATEGORIES = new Set(["char_corruption", "deletion", "insertion"]);
const NORMALIZATION_CATEGORIES = new Set(["decimal_fraction", "spacing"]);

export function normalizeDamageText(text) {
  return String(text || "")
    .replace(/\s+/g, "")
    .replace(/[×x]/g, "X")
    .toUpperCase();
}

function bboxCenter(bbox) {
  if (!bbox || bbox.length < 4) return null;
  return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
}

function bboxDistance(a, b) {
  const ca = bboxCenter(a);
  const cb = bboxCenter(b);
  if (!ca || !cb) return Number.POSITIVE_INFINITY;
  const dx = ca[0] - cb[0];
  const dy = ca[1] - cb[1];
  return Math.hypot(dx, dy);
}

/** Resolve a damage-test manifest from the active document filename. */
export function resolveDamageManifest(filename) {
  const name = String(filename || "");
  if (!name) return null;
  const lower = name.toLowerCase();
  for (const entry of indexEntries) {
    const hit = (entry.match_filename_substrings || []).some((sub) =>
      lower.includes(String(sub).toLowerCase()),
    );
    if (hit) return BY_STEM[entry.stem] || null;
  }
  return null;
}

export function annotationRawText(annotation) {
  return (
    annotation?.correction?.original
    || annotation?.original_text
    || annotation?.primary_label
    || ""
  );
}

export function annotationActualText(annotation) {
  return (
    annotation?.correction?.canonical
    || annotation?.effective_text
    || annotation?.primary_label
    || annotationRawText(annotation)
  );
}

/**
 * Best-effort link from a manifest case to a live semantic annotation.
 * Prefer page + bbox proximity; fall back to normalized test_text.
 */
export function matchCaseToAnnotation(testCase, annotations) {
  if (!testCase || !annotations?.length) return null;
  const page = Number(testCase.source_page);
  const pageAnns = annotations.filter((a) => Number(a.page) === page);
  if (!pageAnns.length) return null;

  const targetBbox = testCase.modified_bbox || testCase.original_bbox;
  let best = null;
  let bestDist = Number.POSITIVE_INFINITY;
  for (const ann of pageAnns) {
    const dist = bboxDistance(targetBbox, ann.semantic_bbox);
    if (dist < bestDist) {
      best = ann;
      bestDist = dist;
    }
  }
  if (best && bestDist <= 48) return best;

  const targets = new Set([
    normalizeDamageText(testCase.test_text),
    normalizeDamageText(testCase.original_text),
  ]);
  return (
    pageAnns.find((a) => targets.has(normalizeDamageText(annotationRawText(a))))
    || pageAnns.find((a) => targets.has(normalizeDamageText(a.primary_label)))
    || null
  );
}

export function pairCasesWithAnnotations(manifest, semanticDoc) {
  const cases = manifest?.cases || [];
  const annotations = semanticDoc?.annotations || [];
  return cases.map((testCase) => ({
    testCase,
    annotation: matchCaseToAnnotation(testCase, annotations),
  }));
}

export function caseMatchesFilter(pair, filterId) {
  const { testCase, annotation } = pair;
  const cat = testCase.category;
  switch (filterId) {
    case "repair":
      return REPAIR_CATEGORIES.has(cat);
    case "normalization":
      return NORMALIZATION_CATEGORIES.has(cat);
    case "incomplete":
      return cat === "incomplete";
    case "clean":
      return cat === "clean_control";
    case "reviewed":
      return ["human_accepted", "human_rejected", "auto_accepted"].includes(
        annotation?.review_status,
      );
    case "all":
    default:
      return true;
  }
}

export function damageCorpusSummary(pairs) {
  const counts = {
    total: pairs.length,
    repair: 0,
    normalization: 0,
    incomplete: 0,
    clean: 0,
    needs_review: 0,
    matched: 0,
  };
  for (const pair of pairs) {
    if (pair.annotation) counts.matched += 1;
    if (REPAIR_CATEGORIES.has(pair.testCase.category)) counts.repair += 1;
    if (NORMALIZATION_CATEGORIES.has(pair.testCase.category)) counts.normalization += 1;
    if (pair.testCase.category === "incomplete") counts.incomplete += 1;
    if (pair.testCase.category === "clean_control") counts.clean += 1;
    if (pair.annotation?.review_status === "needs_review") counts.needs_review += 1;
  }
  return counts;
}

/**
 * Compare TEST EXPECTED metadata to ACTUAL backend annotation output.
 * Does not invent scores or rewrite actual fields.
 */
export function compareExpectedVsActual(testCase, annotation) {
  if (!testCase) {
    return { status: "n/a", expected: null, actual: null, detail: "No test case" };
  }
  const expected = {
    normalized: testCase.expected_normalized ?? null,
    operation: testCase.expected_operation ?? null,
    status: testCase.expected_status ?? null,
    abstention: Boolean(testCase.expected_abstention),
    intended: testCase.intended_semantic_result ?? null,
  };
  if (!annotation) {
    return {
      status: "UNMATCHED",
      expected,
      actual: null,
      detail: "No semantic annotation matched this case yet (process the drawing first).",
    };
  }
  const actual = {
    raw: annotationRawText(annotation),
    normalized: annotationActualText(annotation),
    operation: annotation?.correction?.operation || "keep",
    review_status: annotation.review_status,
    family: annotation?.structural_parse?.family || null,
    takeoff_eligible: annotation?.takeoff_eligible,
    completion_status: annotation?.completion_status || annotation?.structural_parse?.grammar || null,
  };

  const expectedNorm = normalizeDamageText(expected.normalized || expected.intended);
  const actualNorm = normalizeDamageText(actual.normalized);
  const op = String(actual.operation || "").toLowerCase();

  if (testCase.category === "clean_control") {
    const rawEq = normalizeDamageText(actual.raw) === normalizeDamageText(testCase.test_text);
    const unchanged = op === "keep" || normalizeDamageText(actual.raw) === actualNorm;
    return {
      status: rawEq && unchanged ? "PASS" : "REVIEW",
      expected,
      actual,
      detail: unchanged
        ? "Clean control left equivalent (no unnecessary rewrite)."
        : "Clean control was rewritten — investigate.",
    };
  }

  if (testCase.expected_abstention || testCase.category === "incomplete") {
    const abstained =
      Boolean(annotation?.abstained)
      || actual.completion_status === "incomplete"
      || actual.completion_status === "missing_thickness"
      || annotation?.structural_parse?.grammar === "incomplete"
      || actual.takeoff_eligible === false;
    return {
      status: abstained ? "PASS" : "REVIEW",
      expected,
      actual,
      detail: abstained
        ? "Incomplete case abstained / not takeoff-eligible as expected."
        : "Incomplete case did not abstain — do not treat as a silent pass.",
    };
  }

  if (NORMALIZATION_CATEGORIES.has(testCase.category)) {
    const ok = expectedNorm && actualNorm === expectedNorm && (op === "normalization" || op === "keep");
    return {
      status: ok ? "PASS" : "REVIEW",
      expected,
      actual,
      detail: ok
        ? "Normalization matched expected canonical form."
        : "Normalization outcome differs from test expectation (measure, do not force).",
    };
  }

  if (REPAIR_CATEGORIES.has(testCase.category)) {
    const repaired = expectedNorm && actualNorm === expectedNorm;
    return {
      status: repaired ? "PASS" : "REVIEW",
      expected,
      actual,
      detail: repaired
        ? "Actual canonical matches expected repair target."
        : "Repair target not reached (or still needs human review) — expected for hard cases.",
    };
  }

  return {
    status: expectedNorm && actualNorm === expectedNorm ? "PASS" : "REVIEW",
    expected,
    actual,
    detail: "Compared expected metadata to actual backend fields only.",
  };
}
