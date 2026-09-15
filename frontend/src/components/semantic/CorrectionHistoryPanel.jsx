import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

/**
 * Append-only correction history across the semantic document.
 * Current accepted values live on each annotation; this panel only lists events.
 */
export default function CorrectionHistoryPanel({ document }) {
  const rows = [];
  for (const ann of document?.annotations || []) {
    const history = ann.review?.history || [];
    for (const event of history) {
      rows.push({
        key: `${ann.annotation_id}-${event.at || rows.length}-${event.action}`,
        page: event.page ?? ann.page,
        from: event.from_text ?? ann.original_text,
        to: event.to_text ?? event.edited_text ?? event.candidate_text ?? "—",
        action: event.action,
        status: ann.review_status,
        at: event.at,
      });
    }
  }
  rows.sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));

  if (!rows.length) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }} data-testid="correction-history-empty">
        <Typography variant="body2" color="text.secondary">
          No Accept / Reject / Manual Edit events yet.
        </Typography>
      </Paper>
    );
  }

  return (
    <TableContainer
      component={Paper}
      variant="outlined"
      sx={{ maxHeight: 280 }}
      data-testid="correction-history"
    >
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell>Page</TableCell>
            <TableCell>From</TableCell>
            <TableCell>To</TableCell>
            <TableCell>Action</TableCell>
            <TableCell>Time</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell>{row.page ?? "—"}</TableCell>
              <TableCell sx={{ fontFamily: "monospace" }}>{row.from}</TableCell>
              <TableCell sx={{ fontFamily: "monospace" }}>{row.to}</TableCell>
              <TableCell>{row.action}</TableCell>
              <TableCell>
                {row.at
                  ? new Date(row.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                  : "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
