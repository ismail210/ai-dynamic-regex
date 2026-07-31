import { Button, Stack } from "@mui/material";
import { Download } from "@mui/icons-material";
import { downloadFile, resultsToCsv } from "../lib/utils";

export default function DownloadButtons({ data }) {
  const results = data?.results || [];
  return <Stack direction="row" spacing={1}><Button size="small" startIcon={<Download />} onClick={() => downloadFile(JSON.stringify(data, null, 2), "takeoff-analysis.json")}>JSON</Button>
    <Button size="small" startIcon={<Download />} onClick={() => downloadFile(resultsToCsv(results), "takeoff-analysis.csv", "text/csv")}>CSV</Button></Stack>;
}
