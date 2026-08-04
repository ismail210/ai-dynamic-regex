import { Box, Stack, Typography } from "@mui/material";

export default function PageHeader({ title, subtitle, actions }) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={2}
      sx={{
        justifyContent: "space-between",
        alignItems: { sm: "flex-end" },
        mb: { xs: 2.5, md: 3.25 },
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h4">{title}</Typography>
        {subtitle && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.6, maxWidth: 680, textWrap: "pretty" }}
          >
            {subtitle}
          </Typography>
        )}
      </Box>
      {actions && (
        <Stack
          direction="row"
          spacing={1}
          useFlexGap
          sx={{ flexWrap: "wrap", flexShrink: 0 }}
        >
          {actions}
        </Stack>
      )}
    </Stack>
  );
}
