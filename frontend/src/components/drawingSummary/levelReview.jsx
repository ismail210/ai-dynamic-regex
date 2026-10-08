// A level whose sources disagree, with everything else the set prints about
// it: confirmed observations (each opening its own highlighted source), a
// check of printed numbers, and candidate explanations with what the
// evidence says about each. Nothing here chooses a value.
import {
  Box,
  Button,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { CompareOutlined } from "@mui/icons-material";
import { formatLength } from "../../lib/dimensions";
import { ViewPageButton, whereLabel } from "./sources";
import { Dim } from "./visuals";

const ROLE_LABEL = {
  schedule: "Column schedule",
  general_note: "General datum note",
  local_annotation: "Local plan annotation",
  section: "Section",
  section_local: "Section (local condition)",
};

const EXPLANATION_STATUS = {
  supported: { label: "Supported by printed evidence", color: "success.main" },
  not_supported: { label: "Not supported by printed evidence", color: "text.secondary" },
  unresolved: { label: "Unresolved", color: "warning.main" },
  observation: { label: "Observation", color: "text.secondary" },
};

// "S5.25: total depth 5 1/4"; 3.25" concrete on 2" ... deck" from the tag's definition cells.
function tagSummary(tag) {
  const cells = tag?.definition?.cells || [];
  const text = cells.filter((c) => c.text).map((c) => `${(c.path || [c.heading]).slice(-1)[0].toLowerCase()} ${c.text}`);
  return text.join("; ");
}

// Printed feet-inch values in the sentence with proper symbols (55'-2" -> 55′-2″, 2 1/2" -> 2½″).
export const withLengths = (text) => String(text || "")
  .replace(/\d+'\s*-\s*\d+(?:\s+\d+\/\d+)?"|(?<![\d'/.-])\d+\s+\d+\/\d+"/g, (m) => formatLength(m));

// Every printed source of a review in one line, for compact tables:
// "general note 55′-2″ · S122; local annotation 55′-10″ · S122; Section 1 55′-10″ · S421 ...".
export const RELATED_HEADING =
  "The general note's value printed elsewhere (not evidence for this level)";

export function reviewSourcesText(review) {
  return (review?.items || []).filter((i) => i.role !== "schedule").map((i) => {
    const sheet = i.source?.sheet || (i.source?.page ? `p. ${i.source.page}` : "");
    const name = { general_note: "general note", local_annotation: "local annotation" }[i.role]
      || String(i.label || "").split(" · ")[0];
    return `${name} ${formatLength(i.value)} · ${sheet}${i.role === "section_local" ? " (local condition)" : ""}`;
  }).join("; ");
}

export function LevelReview({ review, onView, onCompare }) {
  const general = review.items.find((i) => i.role === "general_note");
  const local = review.items.find((i) => i.role === "local_annotation") || review.items.find((i) => i.role === "section");
  const source = (item) => ({ ...item.source, mark: `${item.label} ${item.value}` });
  return (
    <Box sx={{ p: 1.5, border: 1, borderColor: "warning.main", borderRadius: 1 }}>
      <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>{withLengths(review.headline)}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>Printed observations</Typography>
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small" aria-label={`Printed evidence for ${review.level}`}>
          <TableHead>
            <TableRow>
              <TableCell>Source</TableCell>
              <TableCell>Value</TableCell>
              <TableCell>What it covers</TableCell>
              <TableCell align="right">Source</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {review.items.map((item, i) => (
              <TableRow key={`${item.role}-${i}`} sx={{ "& > td": { verticalAlign: "top" } }}>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}>{ROLE_LABEL[item.role] || item.role}</Typography>
                  <Typography variant="caption" color="text.secondary">{item.label}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}><Dim raw={item.value} /></Typography>
                  {item.name && <Typography variant="caption" color="text.secondary">{item.name}</Typography>}
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{item.scope}</Typography>
                  {item.tag && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                      {item.tag.mark}{item.tag.material ? ` (${item.tag.material})` : ""} per {item.tag.definition?.table?.toLowerCase()}: {withLengths(tagSummary(item.tag))}
                    </Typography>
                  )}
                </TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  <ViewPageButton item={source(item)} label={item.source?.sheet || "View"} onView={onView} />
                  {item.tag?.definition?.page && (
                    <ViewPageButton item={{ ...item.tag.definition, mark: `${item.tag.mark} definition` }}
                      label={`${item.tag.mark}`} onView={onView} />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
      {onCompare && general && local && (
        <Button size="small" startIcon={<CompareOutlined fontSize="small" />} sx={{ mt: 0.5, px: 0.5 }}
          onClick={() => onCompare([source(general), source(local)])}>
          Compare the general note with the {ROLE_LABEL[local.role].toLowerCase()} side by side
        </Button>
      )}
      {review.checks?.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Check of printed numbers (calculated; it does not decide which value governs)
          </Typography>
          {review.checks.map((check) => (
            <Stack key={check.slab} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }} useFlexGap>
              <Typography variant="body2">
                <Dim raw={check.slab} /> − <Dim inches={check.offset_inches} /> = <Dim raw={check.result} strong />
                {check.printed.length > 0
                  ? ` — printed as ${check.printed[0].name} on ${[...new Set(check.printed.map((p) => p.sheet))].join(", ")}`
                  : " — not found among the extracted level markers"}
              </Typography>
              {check.printed.slice(0, 1).map((p) => (
                <ViewPageButton key={`${p.page}`} item={{ ...p, mark: `${p.name} ${formatLength(check.result)}` }}
                  label={p.sheet || "View"} onView={onView} />
              ))}
            </Stack>
          ))}
          {review.checks[0]?.rule_source && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              Offset from the plan note on {whereLabel(review.checks[0].rule_source)}: “{review.checks[0].rule_source.text}”
            </Typography>
          )}
        </Box>
      )}
      {review.related?.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{RELATED_HEADING}</Typography>
          {review.related.map((r) => (
            <Stack key={`${r.source.page}-${r.source.bbox}`} direction="row" spacing={1} useFlexGap
              sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="body2">{withLengths(r.note)}</Typography>
              <ViewPageButton item={{ ...r.source, mark: `${r.value}${r.tag ? ` beside ${r.tag.mark}` : ""}` }}
                label={r.source.sheet || "View"} onView={onView} />
              {r.tag?.definition?.page && (
                <ViewPageButton item={{ ...r.tag.definition, mark: `${r.tag.mark} definition` }} label={r.tag.mark} onView={onView} />
              )}
            </Stack>
          ))}
        </Box>
      )}
      {review.explanations?.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Possible explanations (not confirmed)
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {review.explanations.filter((e) => e.status !== "observation").map((e) => (
              <Typography key={e.id} component="li" variant="body2" sx={{ mb: 0.5 }}>
                {e.label} —{" "}
                <Box component="span" sx={{ color: EXPLANATION_STATUS[e.status]?.color, fontWeight: 600 }}>
                  {EXPLANATION_STATUS[e.status]?.label || e.status}
                </Box>
                <Typography component="span" variant="body2" color="text.secondary">. {withLengths(e.basis)}</Typography>
              </Typography>
            ))}
          </Box>
        </Box>
      )}
    </Box>
  );
}
