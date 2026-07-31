import { Card, CardContent, Grid, Typography } from "@mui/material";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "../lib/utils";

export default function Charts({ data }) {
  const classes = Object.entries(data?.summary?.class_distribution || {}).map(([name, value]) => ({
    name,
    value,
  }));
  const confidence = Object.entries(data?.summary?.confidence_levels || {}).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 12, md: 7 }}>
        <Card>
          <CardContent>
            <Typography variant="subtitle2" fontWeight={700} mb={1.5}>
              Class distribution
            </Typography>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={classes}>
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#6b9bff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>
      <Grid size={{ xs: 12, md: 5 }}>
        <Card>
          <CardContent>
            <Typography variant="subtitle2" fontWeight={700} mb={1.5}>
              Confidence levels
            </Typography>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={confidence} dataKey="value" nameKey="name" outerRadius={88}>
                  {confidence.map((_, index) => (
                    <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}
