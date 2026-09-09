import { Link } from "react-router-dom";
import { Alert, Stack } from "@mui/material";
import { FactCheckOutlined, PictureAsPdfOutlined } from "@mui/icons-material";
import StatsCards from "./StatsCards";
import Charts from "./Charts";
import DownloadButtons from "./DownloadButtons";
import TokensTable from "./TokensTable";
import { TipButton } from "./ui/ActionButtons";

/**
 * The results view — stats, charts, the predictions table, and the forward
 * CTAs. Lifted from the old Results page (minus its PageHeader) so the merged
 * Analysis & Results page can render it in place once analysis completes.
 */
export default function ResultsBody({ data }) {
  return (
    <Stack spacing={2.5}>
      <Stack
        direction="row"
        spacing={1}
        useFlexGap
        sx={{ flexWrap: "wrap", justifyContent: "flex-end" }}
      >
        <DownloadButtons data={data} />
      </Stack>
      <StatsCards data={data} />
      <Charts data={data} />
      {data.context_definitions?.length > 0 && (
        <Alert severity="info" variant="outlined">
          {data.context_definitions.length} steel designation
          {data.context_definitions.length === 1 ? "" : "s"} on legend / general-note
          pages are excluded from the takeoff — they define project notation, not
          members on the structure.
        </Alert>
      )}
      <TokensTable results={data.results} />
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
        <TipButton
          component={Link}
          to="/review-drawing"
          variant="contained"
          startIcon={<PictureAsPdfOutlined />}
        >
          Review on drawing
        </TipButton>
        <TipButton
          component={Link}
          to="/validation"
          variant="outlined"
          startIcon={<FactCheckOutlined />}
        >
          Review validation
        </TipButton>
      </Stack>
    </Stack>
  );
}
