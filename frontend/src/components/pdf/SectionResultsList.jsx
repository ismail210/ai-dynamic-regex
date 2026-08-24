import { useMemo, useState } from "react";
import {
  Box,
  Chip,
  InputAdornment,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { PlaceOutlined, SearchOutlined } from "@mui/icons-material";
import MatchStatusBadge from "../ui/MatchStatusBadge";
import {
  getConfidence,
  getFamily,
  getMatchStatus,
  getPredictionLocation,
  getResultKey,
  getSection,
  isInferredLocation,
  isLegacyPrediction,
} from "../../lib/predictionContract";

function rowKey(result, index) {
  return getResultKey(result) || `${getSection(result)}-${result.page_number ?? "p"}-${index}`;
}

export default function SectionResultsList({
  results = [],
  selectedKey = null,
  onSelect,
}) {
  const [filter, setFilter] = useState("");

  const rows = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return (results || []).map((result, index) => {
      const key = rowKey(result, index);
      const location = getPredictionLocation(result);
      const section = getSection(result);
      const family = getFamily(result);
      const confidence = getConfidence(result);
      const haystack = [
        section,
        family,
        result.raw_text,
        result.original_token,
        result.corrected_text,
        result.corrected_token,
        String(location.pageNumber ?? ""),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return {
        key,
        result,
        location,
        section,
        family,
        confidence,
        visible: !query || haystack.includes(query),
      };
    });
  }, [results, filter]);

  const visible = rows.filter((row) => row.visible);

  return (
    <Stack spacing={1.25} sx={{ height: "100%", minHeight: 0 }}>
      <TextField
        size="small"
        fullWidth
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        placeholder="Filter sections…"
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchOutlined fontSize="small" />
              </InputAdornment>
            ),
          },
        }}
      />
      <Typography variant="caption" color="text.secondary">
        {visible.length} of {rows.length} sections
      </Typography>
      <List
        dense
        disablePadding
        sx={{
          flex: 1,
          overflow: "auto",
          border: 1,
          borderColor: "divider",
          borderRadius: 2,
          bgcolor: "background.paper",
        }}
      >
        {visible.map(({ key, result, location, section, family, confidence }) => {
          const selected = key === selectedKey;
          const legacy = isLegacyPrediction(result);
          const inferred = isInferredLocation(result);
          return (
            <ListItemButton
              key={key}
              selected={selected}
              alignItems="flex-start"
              onClick={() => onSelect?.({ key, result, location })}
              sx={{
                borderBottom: 1,
                borderColor: "divider",
                py: 1.1,
                gap: 1,
              }}
            >
              <ListItemText
                primary={
                  <Stack
                    direction="row"
                    spacing={0.75}
                    sx={{ alignItems: "center", flexWrap: "wrap", mb: 0.35 }}
                  >
                    <Typography
                      component="span"
                      fontFamily="monospace"
                      fontWeight={800}
                      fontSize={13.5}
                    >
                      {[family, section].filter(Boolean).join(" · ") || "Unclassified"}
                    </Typography>
                    <Chip
                      size="small"
                      label={confidence.level || "—"}
                      color={
                        confidence.level === "High"
                          ? "success"
                          : confidence.level === "Medium"
                            ? "warning"
                            : "default"
                      }
                      variant="outlined"
                    />
                  </Stack>
                }
                secondary={
                  <Stack spacing={0.55} mt={0.35}>
                    <Typography variant="caption" color="text.secondary" component="span">
                      OCR: {result.raw_text || result.original_token || "—"}
                      {result.corrected_text
                        && result.corrected_text !== (result.raw_text || result.original_token)
                        ? ` → ${result.corrected_text}`
                        : ""}
                    </Typography>
                    <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }}>
                      <MatchStatusBadge
                        matchStatus={getMatchStatus(result)}
                        isLegacy={legacy}
                        size="small"
                      />
                      {location.hasLocation ? (
                        <Chip
                          size="small"
                          icon={<PlaceOutlined />}
                          label={
                            inferred
                              ? `Inferred · Page ${location.pageNumber}`
                              : `Page ${location.pageNumber}`
                          }
                          color={inferred ? "info" : "primary"}
                          variant="outlined"
                        />
                      ) : (
                        <Chip
                          size="small"
                          label="No location on drawing"
                          variant="outlined"
                        />
                      )}
                    </Stack>
                  </Stack>
                }
                slotProps={{ secondary: { component: "div" } }}
              />
            </ListItemButton>
          );
        })}
        {visible.length === 0 && (
          <Box px={2} py={3}>
            <Typography variant="body2" color="text.secondary">
              No sections match this filter.
            </Typography>
          </Box>
        )}
      </List>
    </Stack>
  );
}
