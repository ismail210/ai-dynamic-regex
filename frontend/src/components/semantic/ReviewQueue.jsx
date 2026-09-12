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
import { getOperation } from "../../lib/semanticContract";

/**
 * Compact, focused list -- not a giant admin table. Its only job is to
 * show "automation where safe, human review where not" (Section 20/44K).
 */
export default function ReviewQueue({ items, selectedId, onSelect }) {
  if (!items.length) {
    return (
      <Paper variant="outlined" sx={{ p: 2, textAlign: "center" }}>
        <Typography color="text.secondary" variant="body2">
          Nothing needs review right now.
        </Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 260 }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell>Page</TableCell>
            <TableCell>Original</TableCell>
            <TableCell>Proposed</TableCell>
            <TableCell>Operation</TableCell>
            <TableCell>Geometry</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => (
            <TableRow
              key={item.annotation_id}
              hover
              selected={item.annotation_id === selectedId}
              onClick={() => onSelect(item)}
              sx={{ cursor: "pointer" }}
            >
              <TableCell>{item.page}</TableCell>
              <TableCell sx={{ fontFamily: "monospace" }}>{item.correction.original}</TableCell>
              <TableCell sx={{ fontFamily: "monospace" }}>
                {item.correction.canonical !== item.correction.original
                  ? item.correction.canonical
                  : <Box component="span" sx={{ color: "text.disabled" }}>—</Box>}
              </TableCell>
              <TableCell>
                <OperationBadge operation={getOperation(item)} showTooltip={false} />
              </TableCell>
              <TableCell>
                {item.geometry_associations?.length
                  ? `${item.geometry_associations.length} candidate(s)`
                  : "None"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
