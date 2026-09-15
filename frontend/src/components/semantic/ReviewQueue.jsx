import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import OperationBadge from "./OperationBadge";
import { getAcceptTargetText, getOperation } from "../../lib/semanticContract";

function proposedFor(item) {
  const original = item.correction?.original;
  const canonical = item.correction?.canonical;
  if (canonical && canonical !== original) return canonical;
  const target = getAcceptTargetText(item);
  if (target && target !== original) return target;
  return null;
}

/**
 * Full case / repair list. Intentionally tall enough to show every row with
 * scroll — truncated “first few only” lists hide the corpus under test.
 */
export default function ReviewQueue({ items, selectedId, onSelect }) {
  if (!items.length) {
    return (
      <Paper variant="outlined" sx={{ p: 2, textAlign: "center" }}>
        <Typography color="text.secondary" variant="body2">
          No cases in this filter.
        </Typography>
      </Paper>
    );
  }

  return (
    <TableContainer
      component={Paper}
      variant="outlined"
      data-testid="review-queue-table"
      sx={{ maxHeight: Math.min(560, 48 + items.length * 44), minHeight: 160 }}
    >
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell>Page</TableCell>
            <TableCell>Original</TableCell>
            <TableCell>Proposed</TableCell>
            <TableCell>Operation</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Geometry</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => {
            const proposed = proposedFor(item);
            return (
              <TableRow
                key={item.row_key || item.annotation_id}
                hover
                selected={item.annotation_id === selectedId || item._damagePair?.testCase?.test_case_id === selectedId}
                onClick={() => onSelect(item)}
                sx={{ cursor: "pointer" }}
                data-testid={`review-queue-row-${item.row_key || item.annotation_id}`}
              >
                <TableCell>{item.page}</TableCell>
                <TableCell sx={{ fontFamily: "monospace" }}>{item.correction.original}</TableCell>
                <TableCell sx={{ fontFamily: "monospace" }}>
                  {proposed
                    ? proposed
                    : <Box component="span" sx={{ color: "text.disabled" }}>—</Box>}
                </TableCell>
                <TableCell>
                  <OperationBadge operation={getOperation(item)} showTooltip={false} />
                </TableCell>
                <TableCell>
                  <Typography variant="caption">
                    {(item.review_status || "pending").replace(/_/g, " ")}
                  </Typography>
                </TableCell>
                <TableCell>
                  {item.geometry_associations?.length
                    ? `${item.geometry_associations.length} candidate(s)`
                    : "None"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
