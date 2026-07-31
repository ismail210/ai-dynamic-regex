import { Card, CardContent, Typography } from "@mui/material";

export default function SectionCard({ title, action, children, sx, contentSx }) {
  return (
    <Card sx={{ height: "100%", ...sx }}>
      {(title || action) && (
        <CardContent
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            pb: 1.25,
            pt: 2.25,
            px: 2.5,
            "&:last-child": { pb: 1.25 },
          }}
        >
          {title && (
            <Typography variant="subtitle2" fontWeight={700}>
              {title}
            </Typography>
          )}
          {action}
        </CardContent>
      )}
      <CardContent
        sx={{
          pt: title || action ? 0 : 2.25,
          px: 2.5,
          pb: 2.5,
          "&:last-child": { pb: 2.5 },
          ...contentSx,
        }}
      >
        {children}
      </CardContent>
    </Card>
  );
}
