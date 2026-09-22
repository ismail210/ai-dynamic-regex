import { Grid } from "@mui/material";
import KpiCard from "./ui/KpiCard";

export default function StatsCards({ data }) {
  const results = data?.results || [];
  const levels = data?.summary?.confidence_levels || {};
  const aiscConfirmed =
    data?.summary?.database_matches
    ?? results.filter((r) => r.database_match || r.aisc_confirmed).length;
  const items = [
    ["Pages", data?.pages ?? 0],
    ["Tokens", data?.token_count ?? results.length],
    ["AI predicted", results.filter((r) => r.section || r.prediction).length],
    ["AISC confirmed", aiscConfirmed],
    ["High conf.", levels.High ?? results.filter((r) => r.confidence?.level === "High").length],
  ];

  return (
    <Grid container spacing={1.5}>
      {items.map(([label, value]) => (
        <Grid size={{ xs: 6, sm: 4, md: 2.4 }} key={label}>
          <KpiCard label={label} value={value} />
        </Grid>
      ))}
    </Grid>
  );
}
