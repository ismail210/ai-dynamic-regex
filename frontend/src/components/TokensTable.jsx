import { useMemo, useState } from "react";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  flexRender,
} from "@tanstack/react-table";
import {
  Box,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import {
  ContentCopyOutlined,
  VisibilityOutlined,
} from "@mui/icons-material";
import PredictionDetailModal from "./PredictionDetailModal";
import EmptyState from "./ui/EmptyState";
import MatchStatusBadge, { matchStatusLabel } from "./ui/MatchStatusBadge";
import { TipIconButton } from "./ui/ActionButtons";
import {
  getConfidence,
  getDisplaySection,
  getFamily,
  getMatchStatus,
  isHumanReviewed,
  isLegacyPrediction,
} from "../lib/predictionContract";

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || "");
  } catch {
    /* ignore */
  }
}

export default function TokensTable({ results = [] }) {
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [sorting, setSorting] = useState([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(15);

  const columns = useMemo(
    () => [
      {
        id: "original",
        header: "Original OCR",
        accessorFn: (row) => row.original_token || row.token || "",
        cell: ({ getValue }) => (
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <Typography fontFamily="monospace" fontSize={13} fontWeight={700}>
              {getValue()}
            </Typography>
            <TipIconButton title="Copy token" onClick={(e) => { e.stopPropagation(); copyText(getValue()); }}>
              <ContentCopyOutlined sx={{ fontSize: 14 }} />
            </TipIconButton>
          </Stack>
        ),
      },
      {
        id: "corrected",
        header: "Normalized / Corrected",
        accessorFn: (row) =>
          row.corrected_token || row.original_token || row.token || "",
        cell: ({ getValue }) => (
          <Typography fontFamily="monospace" fontSize={13}>
            {getValue() || "—"}
          </Typography>
        ),
      },
      {
        id: "family",
        header: "Family",
        accessorFn: (row) => getFamily(row),
        cell: ({ getValue }) => (
          <Typography fontFamily="monospace" fontSize={13}>
            {getValue() || "—"}
          </Typography>
        ),
      },
      {
        id: "section",
        header: "Section",
        accessorFn: (row) => getDisplaySection(row).value,
        cell: ({ row }) => {
          const display = getDisplaySection(row.original);
          if (display.reviewRequired) {
            if (display.hasCandidates) {
              const count = (row.original.candidate_sections || []).length;
              return (
                <Chip
                  size="small"
                  color="warning"
                  variant="outlined"
                  label={`Select section (${count} options)`}
                />
              );
            }
            // No candidate list to pick from (e.g. source text isn't a
            // catalog-valid designation at all) — still never show the
            // low-confidence guess as if it were resolved.
            return (
              <Chip size="small" color="warning" variant="outlined" label="Review required" />
            );
          }
          return (
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
              <Typography fontFamily="monospace" fontSize={13}>
                {display.value || "—"}
              </Typography>
              <TipIconButton
                title="Copy section"
                onClick={(e) => {
                  e.stopPropagation();
                  copyText(display.value);
                }}
              >
                <ContentCopyOutlined sx={{ fontSize: 14 }} />
              </TipIconButton>
            </Stack>
          );
        },
      },
      {
        id: "confidence",
        header: "Confidence",
        accessorFn: (row) => (isHumanReviewed(row) ? "" : getConfidence(row).level || ""),
        cell: ({ row }) => {
          // A model confidence/score describes the ORIGINAL prediction, not
          // the human decision that replaced it — showing it next to a
          // human-reviewed section would misrepresent whose judgment the
          // final answer reflects. The original value is preserved on the
          // record (and in Prediction details) for audit; only this
          // presentation is suppressed.
          if (isHumanReviewed(row.original)) {
            return <Typography color="text.secondary">—</Typography>;
          }
          const level = getConfidence(row.original).level || "Unknown";
          return (
            <Chip
              size="small"
              label={level}
              color={
                level === "High" ? "success" : level === "Medium" ? "warning" : "default"
              }
            />
          );
        },
      },
      {
        id: "match_status",
        header: "Match",
        accessorFn: (row) =>
          isHumanReviewed(row)
            ? ""
            : matchStatusLabel(getMatchStatus(row), isLegacyPrediction(row)),
        cell: ({ row }) =>
          isHumanReviewed(row.original) ? (
            <Typography color="text.secondary">—</Typography>
          ) : (
            <MatchStatusBadge
              matchStatus={getMatchStatus(row.original)}
              isLegacy={isLegacyPrediction(row.original)}
            />
          ),
      },
      {
        id: "validation",
        header: "Validation",
        accessorFn: (row) =>
          isHumanReviewed(row)
            ? "Human Reviewed"
            : row.validation?.status || row.review_status || "",
        cell: ({ row, getValue }) => {
          if (isHumanReviewed(row.original)) {
            return <Chip size="small" label="Human Reviewed" color="info" />;
          }
          const value = getValue();
          return (
            <Chip
              size="small"
              label={value || "—"}
              color={
                value === "PASS" || value === "auto_accepted"
                  ? "success"
                  : value === "FAIL"
                    ? "error"
                    : "warning"
              }
            />
          );
        },
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <TipIconButton
            title="View details"
            onClick={() => setSelectedId(row.original.object_id || row.original.component_id)}
          >
            <VisibilityOutlined fontSize="small" />
          </TipIconButton>
        ),
      },
    ],
    []
  );

  // Re-derived from `results` (not held as a stale object reference) so a
  // human-review selection saved while the modal is open — which patches
  // `results` via AnalysisContext.setData — is reflected immediately, both
  // in this table's Section cell and in the still-open modal.
  const selected = selectedId
    ? results.find((row) => (row.object_id || row.component_id) === selectedId) || null
    : null;

  const table = useReactTable({
    data: results,
    columns,
    state: {
      globalFilter: filter,
      sorting,
      pagination: { pageIndex, pageSize },
    },
    onGlobalFilterChange: setFilter,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  if (!results.length) {
    return (
      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        <EmptyState
          title="No token results yet"
          subtitle="Upload a PDF to inspect extracted tokens."
        />
      </Paper>
    );
  }

  return (
    <>
      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
          <TextField
            size="small"
            placeholder="Search tokens…"
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setPageIndex(0);
            }}
            fullWidth
          />
        </Box>
        <TableContainer sx={{ maxHeight: "60vh", overflowX: "auto" }}>
          <Table size="medium" stickyHeader>
            <TableHead>
              <TableRow>
                {table.getFlatHeaders().map((header) => (
                  <TableCell
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler?.()}
                    sx={{ cursor: header.column.getCanSort?.() ? "pointer" : "default" }}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {{
                      asc: " ↑",
                      desc: " ↓",
                    }[header.column.getIsSorted()] || null}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow
                  hover
                  key={row.id}
                  onClick={() => setSelectedId(row.original.object_id || row.original.component_id)}
                  role="button"
                  tabIndex={0}
                  aria-label={`View prediction details for ${
                    row.original.original_token || row.original.token || "token"
                  }`}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(row.original.object_id || row.original.component_id);
                    }
                  }}
                  sx={{ cursor: "pointer", height: 56 }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={table.getFilteredRowModel().rows.length}
          page={pageIndex}
          onPageChange={(_, p) => setPageIndex(p)}
          rowsPerPage={pageSize}
          onRowsPerPageChange={(e) => {
            setPageSize(parseInt(e.target.value, 10));
            setPageIndex(0);
          }}
          rowsPerPageOptions={[10, 15, 25, 50]}
        />
      </Paper>
      <PredictionDetailModal result={selected} onClose={() => setSelectedId(null)} />
    </>
  );
}
