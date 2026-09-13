import { Box, Stack, Typography } from "@mui/material";
import {
  CheckCircleOutlined,
  ErrorOutlined,
  RadioButtonUncheckedOutlined,
  WarningAmberOutlined,
} from "@mui/icons-material";
import { getProcessSteps } from "../../lib/semanticContract";

const ICONS = {
  done: CheckCircleOutlined,
  warning: WarningAmberOutlined,
  error: ErrorOutlined,
  pending: RadioButtonUncheckedOutlined,
};

const COLORS = {
  done: "success.main",
  warning: "warning.main",
  error: "error.main",
  pending: "text.disabled",
};

/**
 * Compact vertical stepper (Section 15): every step comes from a real field
 * on the annotation (extraction source, structural_parse, repair_candidates,
 * review status) -- never a hand-written narrative. Deliberately small: this
 * is meant to be readable in seconds, not a full workflow diagram.
 */
export default function ProcessTimeline({ annotation }) {
  const steps = getProcessSteps(annotation);
  if (!steps.length) return null;

  return (
    <Stack spacing={0} data-testid="process-timeline">
      {steps.map((step, i) => {
        const Icon = ICONS[step.status] || RadioButtonUncheckedOutlined;
        const color = COLORS[step.status] || "text.disabled";
        const isLast = i === steps.length - 1;
        return (
          <Stack direction="row" spacing={1} key={step.key} sx={{ position: "relative" }}>
            <Stack alignItems="center" sx={{ pt: 0.25 }}>
              <Icon fontSize="small" sx={{ color }} />
              {!isLast && (
                <Box sx={{ width: "2px", flex: 1, minHeight: 14, bgcolor: "divider", my: 0.25 }} />
              )}
            </Stack>
            <Box sx={{ pb: isLast ? 0 : 1 }}>
              <Typography variant="body2" sx={{ fontWeight: step.status === "warning" || step.status === "error" ? 600 : 400 }}>
                {step.label}
              </Typography>
              {step.detail && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontFamily: "monospace" }}>
                  {step.detail}
                </Typography>
              )}
            </Box>
          </Stack>
        );
      })}
    </Stack>
  );
}
