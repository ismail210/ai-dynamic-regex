import { Link, useSearchParams } from "react-router-dom";
import { useAnalysis } from "../context/AnalysisContext";
import { SummaryReport } from "../components/drawingSummary/report";

/**
 * Printable Drawing Summary: rendered outside the application shell from the
 * extracted profile, so the print carries no navigation and every selected
 * record is in the page -- nothing depends on what was expanded on screen.
 */
export default function DrawingSummaryReportPage() {
  const { extraction, document, rehydrating } = useAnalysis();
  const [params] = useSearchParams();
  const mode = params.get("mode") === "full" ? "full" : "concise";
  const di = extraction?.legend_profile?.drawing_intelligence;
  if (!di) {
    return (
      <div style={{ padding: 24, fontFamily: "Segoe UI, Arial, sans-serif" }}>
        {rehydrating ? "Loading the drawing summary…" : (
          <>No drawing summary is loaded. <Link to="/drawing-summary">Open the Drawing Summary</Link> first.</>
        )}
      </div>
    );
  }
  return (
    <>
      <div className="dsr" style={{ paddingBottom: 0 }}>
        <div className="toolbar">
          <Link to="/drawing-summary">← Back to the summary</Link>
          <button type="button" onClick={() => window.print()}>Print / save as PDF</button>
          {mode === "full"
            ? <Link to="/drawing-summary/report?mode=concise">Concise summary</Link>
            : <Link to="/drawing-summary/report?mode=full">Full evidence report</Link>}
        </div>
      </div>
      <SummaryReport di={di} document={document} mode={mode} />
    </>
  );
}
