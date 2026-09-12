import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import { LinkOff, LinkOutlined, TimelineOutlined, WarningAmberOutlined } from "@mui/icons-material";
import { geometryForId, hasGeometryConflict } from "../../lib/semanticContract";

const REASON_LABELS = {
  GHX_EXISTING_PAIR: "Existing Grasshopper text/curve pairing",
  PDF_LEADER_INTERSECTION: "PDF leader line intersection",
  ORIENTATION_MATCH: "Orientation compatible",
  PROJECTED_OVERLAP: "Projected overlap",
  NEAREST_STRUCTURAL_CURVE: "Nearest structural curve",
  GHX_PDF_DISAGREEMENT: "Grasshopper and PDF evidence disagree",
  AMBIGUOUS_MULTIPLE_BEAMS: "Multiple equally plausible candidates",
};

/**
 * Four honest states (Section 18): connected / PDF-only / none / conflict.
 * Never implies "Grasshopper verified" -- a Grasshopper-sourced candidate
 * is always labeled "Grasshopper candidate/evidence" (Section 34).
 */
export default function GeometryEvidenceCard({ document, annotation }) {
  const associations = annotation?.geometry_associations || [];
  const conflict = hasGeometryConflict(annotation);

  if (!associations.length) {
    return (
      <Paper variant="outlined" sx={{ p: 1.5 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <LinkOff fontSize="small" color="disabled" />
          <Typography variant="body2" color="text.secondary">
            No geometry evidence for this annotation.
          </Typography>
        </Stack>
      </Paper>
    );
  }

  return (
    <Paper
      variant="outlined"
      sx={{ p: 1.5, borderColor: conflict ? "error.main" : "divider" }}
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        {conflict ? (
          <WarningAmberOutlined fontSize="small" color="error" />
        ) : (
          <LinkOutlined fontSize="small" color="info" />
        )}
        <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
          Geometry evidence
        </Typography>
        {conflict && <Chip size="small" color="error" label="Conflict — needs review" />}
      </Stack>
      <Stack spacing={1}>
        {associations.map((assoc) => {
          const geom = geometryForId(document, assoc.geometry_id);
          return (
            <Box
              key={assoc.geometry_id}
              sx={{ px: 1, py: 0.75, bgcolor: "action.hover", borderRadius: 1 }}
            >
              <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap">
                <Typography sx={{ fontFamily: "monospace", fontWeight: 700, fontSize: 13 }}>
                  {assoc.geometry_id}
                </Typography>
                <Chip
                  size="small"
                  variant="outlined"
                  icon={<TimelineOutlined fontSize="small" />}
                  label={geom?.source === "grasshopper" ? "Grasshopper candidate" : geom?.source || "unknown source"}
                />
                {geom?.source_output && (
                  <Typography variant="caption" color="text.secondary">
                    {geom.source_output}
                  </Typography>
                )}
              </Stack>
              {assoc.association_reason?.length > 0 && (
                <Box component="ul" sx={{ m: "4px 0 0", pl: 2.5 }}>
                  {assoc.association_reason.map((reason) => (
                    <Typography
                      key={reason}
                      component="li"
                      variant="caption"
                      color="text.secondary"
                    >
                      {REASON_LABELS[reason] || reason}
                    </Typography>
                  ))}
                </Box>
              )}
            </Box>
          );
        })}
      </Stack>
    </Paper>
  );
}
