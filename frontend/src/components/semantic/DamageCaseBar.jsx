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
    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="damage-case-bar">
      <Stack spacing={1.25}>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Controlled damage corpus
          </Typography>
          <Chip size="small" label={`${summary.total} cases`} />
          <Chip size="small" variant="outlined" label={`${summary.repair} repairs`} />
          <Chip size="small" variant="outlined" label={`${summary.normalization} norms`} />
          <Chip size="small" variant="outlined" label={`${summary.incomplete} incomplete`} />
          <Chip size="small" variant="outlined" label={`${summary.clean} clean`} />
          <Chip size="small" color="warning" variant="outlined" label={`${summary.needs_review} need review`} />
        </Stack>

        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
          {DAMAGE_FILTERS.map((f) => (
            <Button
              key={f.id}
              size="small"
              variant={filterId === f.id ? "contained" : "outlined"}
              onClick={() => onFilterChange(f.id)}
              data-testid={`damage-filter-${f.id}`}
            >
              {f.label}
            </Button>
          ))}
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="body2" data-testid="damage-case-position">
            Case {caseCount ? caseIndex + 1 : 0} / {caseCount}
          </Typography>
          {currentCase && (
            <Typography variant="body2" sx={{ fontFamily: "monospace" }} data-testid="damage-case-text">
              {currentCase.original_text} → {currentCase.test_text}
              <Box component="span" sx={{ color: "text.secondary", ml: 1 }}>
                ({currentCase.category} · p{currentCase.source_page})
              </Box>
            </Typography>
          )}
          <ButtonGroup size="small" sx={{ ml: "auto" }}>
            <Button
              startIcon={<ChevronLeft fontSize="small" />}
              onClick={onPrev}
              disabled={caseCount === 0}
              data-testid="damage-case-prev"
            >
              Previous
            </Button>
            <Button
              endIcon={<ChevronRight fontSize="small" />}
              onClick={onNext}
              disabled={caseCount === 0}
              data-testid="damage-case-next"
            >
              Next
            </Button>
          </ButtonGroup>
        </Stack>
      </Stack>
    </Paper>
  );
}
