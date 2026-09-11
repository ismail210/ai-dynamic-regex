import { Link } from "react-router-dom";
import { Alert, Box, Stack } from "@mui/material";
import { ArrowForwardRounded } from "@mui/icons-material";
import { useAnalysis } from "../context/AnalysisContext";
import DrawingSummaryPanel from "../components/DrawingSummaryPanel";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import WorkflowProgress from "../components/ui/WorkflowProgress";
import { TipButton } from "../components/ui/ActionButtons";

/**
 * What Estima3D understood about the drawing set before it predicts anything —
 * the project's drawing language, conventions, steel families, notes, and
 * uncertainties. Reads the legend/project-context profile the extraction stage
 * already produced (`extraction.legend_profile`).
 */
export default function DrawingSummaryPage() {
  const { document, extraction, data } = useAnalysis();

  if (!extraction) {
    return (
      <EmptyState
        title="Extract a drawing first"
        subtitle="The drawing summary is built from the extracted legend, general-note, and specification pages."
        action={
          <TipButton component={Link} to="/upload-extract" variant="contained">
            Go to Upload & Extract
          </TipButton>
        }
      />
    );
  }

  const profile = extraction.legend_profile;
  const hasProfile =
    profile && (profile.status || Object.keys(profile).length > 0);

  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Drawing Summary"
        subtitle="The project overview, drawing conventions, and steel families Estima3D read from this set. Informational — it does not change any prediction."
      />
      <WorkflowProgress step="summary" />

      {hasProfile ? (
        <DrawingSummaryPanel profile={profile} extraction={extraction} data={data} />
      ) : (
        <Alert severity="info" variant="outlined">
          No legend, general-note, or specification pages were identified in this
          drawing set, so there is no project-language summary to show. You can
          still continue to analysis.
        </Alert>
      )}

      <Box>
        <TipButton
          component={Link}
          to="/analysis"
          variant="contained"
          endIcon={<ArrowForwardRounded />}
        >
          Analyze Steel Takeoff
        </TipButton>
      </Box>
    </Stack>
  );
}
