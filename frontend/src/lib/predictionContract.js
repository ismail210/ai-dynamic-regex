/** Additive prediction contract helpers (family + section + confidence). */

export function getSection(result = {}) {
  return (
    result.section
    || result.prediction
    || result.predicted_shape
    || result.suggested_shape
    || ""
  );
}

export function getFamily(result = {}) {
  return (
    result.family
    || result.prediction_details?.family?.label
    || result.prediction_details?.family_fallback?.label
    || result.entity?.class
    || ""
  );
}

export function getConfidence(result = {}) {
  const conf = result.confidence;
  if (typeof conf === "number") {
    return { overall: conf, score: conf, level: confidenceLevel(conf) };
  }
  if (conf && typeof conf === "object") {
    const overall = Number(
      conf.overall ?? conf.score ?? conf.value ?? result.overall_confidence ?? 0
    );
    return {
      ...conf,
      overall,
      score: Number(conf.score ?? overall),
      level: conf.level || confidenceLevel(overall),
    };
  }
  const overall = Number(result.overall_confidence ?? 0);
  return {
    overall,
    score: overall,
    level: result.confidence_level || confidenceLevel(overall),
  };
}

export function getExplanation(result = {}) {
  const explanation = result.explanation || result.reasoning || {};
  return {
    ...explanation,
    prediction: explanation.prediction || {
      family: getFamily(result),
      section: getSection(result),
    },
    confidence: explanation.confidence ?? getConfidence(result).overall,
    top_candidate_sections:
      explanation.top_candidate_sections
      || result.top_candidate_sections
      || result.prediction_details?.top_classes?.map((item) => ({
        shape: item.class,
        score: item.probability,
      }))
      || result.alternatives
      || [],
    why_selected: explanation.why_selected || result.why_selected || explanation.reasons || [],
    why_rejected: explanation.why_rejected || result.why_rejected || [],
    text_evidence: explanation.text_evidence || result.text_evidence || {},
    geometry_evidence: explanation.geometry_evidence || result.geometry_evidence || {},
    graph_evidence: explanation.graph_evidence || result.graph_evidence || {},
    engineering_evidence:
      explanation.engineering_evidence || result.engineering_evidence || {},
  };
}

export function confidenceLevel(score) {
  if (score >= 0.8) return "High";
  if (score >= 0.55) return "Medium";
  return "Low";
}
