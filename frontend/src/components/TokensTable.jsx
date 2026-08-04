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
  getFamily,
  getMatchStatus,
  getSection,
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
  const [selected, setSelected] = useState(null);
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
        header: "Corrected OCR",
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
        accessorFn: (row) => getSection(row),
        cell: ({ getValue, row }) => (
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <Typography fontFamily="monospace" fontSize={13}>
              {getValue() || "—"}
            </Typography>
            <TipIconButton
              title="Copy section"
              onClick={(e) => {
                e.stopPropagation();
                copyText(getValue());
              }}
            >
              <ContentCopyOutlined sx={{ fontSize: 14 }} />
            </TipIconButton>
          </Stack>
        ),
      },
      {
        id: "confidence",
        header: "Confidence",
        accessorFn: (row) => getConfidence(row).level || "",
        cell: ({ row }) => {
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
        accessorFn: (row) => matchStatusLabel(getMatchStatus(row), isLegacyPrediction(row)),
        cell: ({ row }) => (
          <MatchStatusBadge
            matchStatus={getMatchStatus(row.original)}
            isLegacy={isLegacyPrediction(row.original)}
          />
        ),
      },
      {
        id: "validation",
        header: "Validation",
        accessorFn: (row) => row.validation?.status || row.review_status || "",
        cell: ({ getValue }) => (
          <Chip
            size="small"
            label={getValue() || "—"}
            color={
              getValue() === "PASS" || getValue() === "auto_accepted"
                ? "success"
                : getValue() === "FAIL"
                  ? "error"
                  : "warning"
            }
          />
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <TipIconButton title="View details" onClick={() => setSelected(row.original)}>
            <VisibilityOutlined fontSize="small" />
          </TipIconButton>
        ),
      },
    ],
    []
  );

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
                  onClick={() => setSelected(row.original)}
                  role="button"
                  tabIndex={0}
                  aria-label={`View prediction details for ${
                    row.original.original_token || row.original.token || "token"
                  }`}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(row.original);
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
      <PredictionDetailModal result={selected} onClose={() => setSelected(null)} />
    </>
  );
}
