import { Link as RouterLink } from "react-router-dom";
import { Card, CardContent, Typography } from "@mui/material";

export default function KpiCard({ label, value, to, accent, hint }) {
  return (
    <Card
      component={to ? RouterLink : "div"}
      to={to}
      sx={{
        textDecoration: "none",
        height: "100%",
        minHeight: 116,
        display: "flex",
        "&:hover": to
          ? {
              borderColor: (theme) =>
                theme.palette.mode === "dark"
                  ? "rgba(139,168,236,.36)"
                  : "rgba(54,95,168,.28)",
              boxShadow: (t) =>
                t.palette.mode === "dark"
                  ? "0 12px 32px rgba(2,7,14,.18)"
                  : "0 12px 28px rgba(24,35,52,.08)",
              transform: "translateY(-1px)",
            }
          : undefined,
      }}
    >
      <CardContent sx={{ width: "100%", p: 2.25, "&:last-child": { pb: 2.25 } }}>
        <Typography variant="caption" color="text.secondary" fontWeight={650}>
          {label}
        </Typography>
        <Typography
          variant="h4"
          noWrap
          title={value == null ? "—" : String(value)}
          sx={{
            mt: 1,
            fontWeight: 720,
            color: accent || "text.primary",
            fontSize: "1.65rem",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {value ?? "—"}
        </Typography>
        {hint && (
          <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
            {hint}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
