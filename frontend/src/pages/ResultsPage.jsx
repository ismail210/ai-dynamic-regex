import { Link } from "react-router-dom";
import { Stack } from "@mui/material";
import { FactCheckOutlined, RateReviewOutlined } from "@mui/icons-material";
import StatsCards from "../components/StatsCards";
import Charts from "../components/Charts";
import DownloadButtons from "../components/DownloadButtons";
import TokensTable from "../components/TokensTable";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import { TipButton } from "../components/ui/ActionButtons";
import { useAnalysis } from "../context/AnalysisContext";


export default function ResultsPage() {
  const { data, restoreNotice } = useAnalysis();
  if (!data) {
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
            <TipButton component={Link} to="/upload" variant="contained">
              {isMissingSource ? "Upload the PDF again" : "Start new analysis"}
            </TipButton>
          }
        />
      );
    }
    return (
      <EmptyState
        title="No analysis results"
        subtitle="Upload, extract, and analyze a drawing before opening results."
        action={
          <TipButton component={Link} to="/upload" variant="contained">
            Start workflow
          </TipButton>
        }
      />
    );
  }

  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Explainable predictions"
        subtitle="Exact sections selected from text, OCR, geometry, graph, and engineering evidence."
        actions={<DownloadButtons data={data} />}
      />
      <StatsCards data={data} />
      <Charts data={data} />
      <TokensTable results={data.results} />
      <Stack direction="row" spacing={1}>
        <TipButton
          component={Link}
          to="/validation"
          variant="contained"
          startIcon={<FactCheckOutlined />}
        >
          Review validation
        </TipButton>
        <TipButton
          component={Link}
          to="/review"
          variant="outlined"
          startIcon={<RateReviewOutlined />}
        >
          Review queue
        </TipButton>
      </Stack>
    </Stack>
  );
}
