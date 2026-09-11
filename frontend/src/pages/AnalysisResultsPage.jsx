import { Link } from "react-router-dom";
import { Stack, Typography } from "@mui/material";
import { useAnalysis } from "../context/AnalysisContext";
import AnalyzeLauncher from "../components/AnalyzeLauncher";
import ResultsBody from "../components/ResultsBody";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import WorkflowProgress from "../components/ui/WorkflowProgress";
import { TipButton } from "../components/ui/ActionButtons";

/**
 * Merged Analyze + Results. Before analysis the page is the "Analyze Drawing"
 * launcher; once the run completes the same page becomes the explainable
 * results view. Never redirects between the two states.
 */
export default function AnalysisResultsPage() {
  const { document, extraction, data, restoreNotice } = useAnalysis();

  if (!extraction) {
    if (restoreNotice) {
      const isMissingSource = restoreNotice.kind === "missing-source";
      return (
        <EmptyState
          title={
            isMissingSource
              ? "Original file no longer available"
              : "Previous analysis could not be restored"
          }
          subtitle={restoreNotice.message}
          action={
            <TipButton component={Link} to="/upload-extract" variant="contained">
              {isMissingSource ? "Upload the PDF again" : "Start new analysis"}
            </TipButton>
          }
        />
      );
    }
    return (
      <EmptyState
        title="Extraction is required"
        subtitle="Analysis becomes available once the drawing's engineering objects have been extracted."
        action={
          <TipButton component={Link} to="/upload-extract" variant="contained">
            Go to Upload & Extract
          </TipButton>
        }
      />
    );
  }

  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Analysis & Results"
        subtitle="Exact sections selected from text, OCR, geometry, structural graph, and engineering rules — with the evidence behind every pick."
      />
      <WorkflowProgress step="analyze" />

      {!data ? (
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {document?.source_file} is extracted and ready. Run the multimodal
            analysis to predict every steel section and build its explanation.
          </Typography>
          <AnalyzeLauncher />
        </Stack>
      ) : (
        <ResultsBody data={data} />
      )}
    </Stack>
  );
}
