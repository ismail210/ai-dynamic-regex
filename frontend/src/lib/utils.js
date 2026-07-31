export const CHART_COLORS = ["#1e4fd6", "#5b8cff", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed"];

export function downloadFile(content, filename, type = "application/json") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url; link.download = filename; link.click();
  URL.revokeObjectURL(url);
}

export function resultsToCsv(results = []) {
  const fields = [
    "token",
    "family",
    "section",
    "prediction",
    "confidence",
    "confidence_level",
    "regex",
    "database_match",
    "aisc_confirmed",
  ];
  const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return [
    fields.join(","),
    ...results.map((result) => {
      const conf = result.confidence;
      const overall =
        typeof conf === "number"
          ? conf
          : conf?.overall ?? conf?.score ?? conf?.value ?? "";
      const level =
        typeof conf === "object" ? conf?.level : result.confidence_level;
      const section =
        result.section || result.prediction || result.predicted_shape || "";
      return [
        result.token,
        result.family || "",
        section,
        section,
        overall,
        level,
        result.regex?.pattern ?? result.regex,
        result.database_match,
        result.aisc_confirmed ?? result.database_match,
      ]
        .map(escape)
        .join(",");
    }),
  ].join("\n");
}
