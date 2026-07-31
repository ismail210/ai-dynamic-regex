import { Card, CardContent, Grid, Typography } from "@mui/material";

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
          <Card>
            <CardContent sx={{ py: 1.75, "&:last-child": { pb: 1.75 } }}>
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                {label}
              </Typography>
              <Typography variant="h5" sx={{ mt: 0.5, fontWeight: 700 }}>
                {value}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}
