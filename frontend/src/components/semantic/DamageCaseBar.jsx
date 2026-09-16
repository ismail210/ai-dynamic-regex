import {
  Box,
  Button,
  ButtonGroup,
  Chip,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { ChevronLeft, ChevronRight } from "@mui/icons-material";
import { DAMAGE_FILTERS } from "../../lib/semanticDamageManifest";

export default function DamageCaseBar({
  summary,
  filterId,
  onFilterChange,
  caseIndex,
  caseCount,
  currentCase,
  onPrev,
  onNext,
}) {
  if (!summary || summary.total === 0) return null;

  return (
    <Paper variant="outlined" sx={{ px: 1.5, py: 1 }} data-testid="damage-case-bar">
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={1}
        alignItems={{ md: "center" }}
        useFlexGap
        flexWrap="wrap"
      >
        <Stack direction="row" spacing={0.75} alignItems="center" useFlexGap flexWrap="wrap">
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Test cases
          </Typography>
          <Chip size="small" label={`${summary.total}`} />
          <Typography variant="caption" color="text.secondary">
            {summary.repair} repair · {summary.normalization} norm · {summary.incomplete} incomplete · {summary.clean} clean
          </Typography>
        </Stack>

        <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ flex: 1 }}>
          {DAMAGE_FILTERS.map((f) => (
            <Button
              key={f.id}
              size="small"
              variant={filterId === f.id ? "contained" : "text"}
              onClick={() => onFilterChange(f.id)}
              data-testid={`damage-filter-${f.id}`}
            >
              {f.label}
            </Button>
          ))}
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center" sx={{ ml: { md: "auto" } }}>
          <Typography variant="body2" data-testid="damage-case-position" sx={{ whiteSpace: "nowrap" }}>
            {caseCount ? caseIndex + 1 : 0}/{caseCount}
          </Typography>
          {currentCase && (
            <Typography variant="body2" sx={{ fontFamily: "monospace" }} data-testid="damage-case-text">
              {currentCase.original_text} → {currentCase.test_text}
              <Box component="span" sx={{ color: "text.secondary", ml: 0.75 }}>
                {currentCase.category} · p{currentCase.source_page}
              </Box>
            </Typography>
          )}
          <ButtonGroup size="small">
            <Button onClick={onPrev} disabled={caseCount === 0} data-testid="damage-case-prev">
              <ChevronLeft fontSize="small" />
            </Button>
            <Button onClick={onNext} disabled={caseCount === 0} data-testid="damage-case-next">
              <ChevronRight fontSize="small" />
            </Button>
          </ButtonGroup>
        </Stack>
      </Stack>
    </Paper>
  );
}
