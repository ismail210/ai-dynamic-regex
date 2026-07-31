import { Chip, alpha, useTheme } from "@mui/material";

const ENTITY_STYLES = {
  structural_section: { label: "Steel Section", key: "primary" },
  material: { label: "Material", key: "success" },
  bolt: { label: "Bolt", key: "warning" },
  plate: { label: "Plate", key: "secondary" },
  pipe: { label: "Pipe", key: "info" },
  miscellaneous: { label: "Other", key: "default" },
};

export function entityBadgePalette(theme, entityType) {
  const dark = theme.palette.mode === "dark";
  const map = {
    structural_section: {
      bg: alpha(theme.palette.primary.main, dark ? 0.18 : 0.12),
      color: dark ? "#b7c9f5" : "#2f5699",
      border: alpha(theme.palette.primary.main, 0.28),
    },
    material: {
      bg: alpha(theme.palette.success.main, dark ? 0.18 : 0.12),
      color: dark ? "#8fd9b8" : "#176b4a",
      border: alpha(theme.palette.success.main, 0.28),
    },
    bolt: {
      bg: alpha(theme.palette.warning.main, dark ? 0.18 : 0.12),
      color: dark ? "#e0b574" : "#8a5710",
      border: alpha(theme.palette.warning.main, 0.28),
    },
    plate: {
      bg: dark ? "rgba(167,139,250,0.18)" : "rgba(124,58,237,0.1)",
      color: dark ? "#c4b5fd" : "#6d28d9",
      border: dark ? "rgba(167,139,250,0.32)" : "rgba(124,58,237,0.22)",
    },
    pipe: {
      bg: alpha(theme.palette.info.main, dark ? 0.18 : 0.12),
      color: dark ? "#8ec5df" : "#1f6f93",
      border: alpha(theme.palette.info.main, 0.28),
    },
    miscellaneous: {
      bg: dark ? "rgba(148,163,184,0.14)" : "rgba(100,116,139,0.1)",
      color: dark ? "#cbd5e1" : "#475569",
      border: dark ? "rgba(148,163,184,0.28)" : "rgba(100,116,139,0.2)",
    },
  };
  return map[entityType] || map.miscellaneous;
}

export default function EntityTypeChip({
  entityType,
  label,
  size = "small",
  sx,
}) {
  const theme = useTheme();
  const meta = ENTITY_STYLES[entityType] || ENTITY_STYLES.miscellaneous;
  const colors = entityBadgePalette(theme, entityType);
  return (
    <Chip
      size={size}
      label={label || meta.label}
      sx={{
        bgcolor: colors.bg,
        color: colors.color,
        border: `1px solid ${colors.border}`,
        fontWeight: 650,
        ...sx,
      }}
    />
  );
}
