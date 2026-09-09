import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import { DownloadOutlined, TableViewOutlined } from "@mui/icons-material";
import {
  generateTakeoff,
  takeoffDownloadUrl,
} from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import EmptyState from "../components/ui/EmptyState";
import PageHeader from "../components/ui/PageHeader";
import { TipButton } from "../components/ui/ActionButtons";


function quantityMethodLabel(method) {
  if (method === "labeled_callout") return "Labeled callout";
  if (method === "schedule_cell") return "Schedule cell";
  if (method === "elevation_callout") return "Elevation callout";
  if (method === "insufficient") return "Insufficient";
  return method || "—";
}

export default function TakeoffPage() {
  const { document, data } = useAnalysis();
  const [takeoff, setTakeoff] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    if (!document?.document_id || !data) return;
    setLoading(true);
    setError("");
    try {
      setTakeoff(await generateTakeoff(document.document_id));
    } catch (err) {
      setError(
        err.friendlyMessage ||
          err.response?.data?.detail ||
          "Takeoff generation failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (!data) {
    return (
      <EmptyState
        title="Analysis is required"
        subtitle="Takeoff generation consumes the completed multimodal predictions. It never re-extracts the PDF."
        action={
          <TipButton component={Link} to="/analyze" variant="contained">
            Go to analysis
          </TipButton>
        }
      />
    );
  }

  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Structural steel takeoff"
        subtitle="Labeled-callout quantity estimate. Section precision is scored separately from quantity error."
        actions={
          <TipButton
            variant="contained"
            startIcon={<TableViewOutlined />}
            onClick={generate}
            loading={loading}
          >
            Generate takeoff
          </TipButton>
        }
      />
      {error && <Alert severity="error">{error}</Alert>}
      {takeoff && (
        <>
          <Alert
            severity="success"
            action={
              <Button
                component="a"
                href={takeoffDownloadUrl(takeoff.filename)}
                startIcon={<DownloadOutlined />}
              >
                Download Excel
              </Button>
            }
          >
            {takeoff.total_quantity} labeled-callout members across {takeoff.row_count}{" "}
            section rows. Not true physical quantity.
          </Alert>
          {takeoff.scoreboards && (
            <Alert severity="info">
              Section recognition
              {takeoff.scoreboards.section_recognition
                ? ` P ${Math.round((takeoff.scoreboards.section_recognition.precision || 0) * 100)}% / R ${Math.round((takeoff.scoreboards.section_recognition.recall || 0) * 100)}%`
                : " unavailable until Analyze with Excel"}
              . Quantity MAE {takeoff.scoreboards.quantity?.mae ?? "—"}, bias{" "}
              {takeoff.scoreboards.quantity?.mean_signed_error ?? "—"}. These are
              separate gates.
            </Alert>
          )}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Section</TableCell>
                  <TableCell>Family</TableCell>
                  <TableCell>Entity</TableCell>
                  <TableCell align="right">Quantity</TableCell>
                  <TableCell>Quantity method</TableCell>
                  <TableCell align="right">Confidence</TableCell>
                  <TableCell>Verification</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(takeoff.rows || []).map((row) => (
                  <TableRow key={row.Section}>
                    <TableCell>{row.Section}</TableCell>
                    <TableCell>{row.Family}</TableCell>
                    <TableCell>{row.Entity}</TableCell>
                    <TableCell align="right">{row.Quantity}</TableCell>
                    <TableCell>
                      {quantityMethodLabel(row["Quantity Method"])}
                    </TableCell>
                    <TableCell align="right">
                      {row["Avg Confidence"] == null
                        ? "—"
                        : `${Math.round(row["Avg Confidence"] * 100)}%`}
                    </TableCell>
                    <TableCell>
                      {row["Database Match"] ? "AISC verified" : "AI prediction"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </Stack>
  );
}
