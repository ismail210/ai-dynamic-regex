import { Chip, Tooltip } from "@mui/material";
import {
  CheckCircleOutlined,
  ErrorOutlined,
  HelpOutlined,
  RemoveCircleOutlined,
  RuleOutlined,
  WarningAmberOutlined,
} from "@mui/icons-material";
import { getOperationMeta } from "../../lib/semanticContract";

const ICONS = {
  info: RuleOutlined,
  warning: WarningAmberOutlined,
  success: CheckCircleOutlined,
  neutral: RemoveCircleOutlined,
  error: ErrorOutlined,
};

/**
 * Compact, icon+text badge for one correction operation. Never relies on
 * color alone (Section 31/32): the label and icon carry the meaning, color
 * is a secondary reinforcement.
 */
export default function OperationBadge({ operation, size = "small", showTooltip = true }) {
  const meta = getOperationMeta(operation);
  const Icon = ICONS[meta.colorKey] || HelpOutlined;
  const chip = (
    <Chip
      size={size}
      icon={<Icon fontSize="small" />}
      label={meta.label}
      color={meta.colorKey === "neutral" ? "default" : meta.colorKey}
      variant={meta.colorKey === "neutral" ? "outlined" : "filled"}
      sx={{ fontWeight: 600, "& .MuiChip-icon": { fontSize: 16 } }}
    />
  );
  if (!showTooltip) return chip;
  return <Tooltip title={meta.explanation}>{chip}</Tooltip>;
}
