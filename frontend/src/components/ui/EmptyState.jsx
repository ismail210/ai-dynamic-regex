import { Box, Typography } from "@mui/material";
import { InboxOutlined } from "@mui/icons-material";

export default function EmptyState({
  title = "Nothing to show",
  subtitle = "",
  icon: Icon = InboxOutlined,
  action,
  sx,
}) {
  return (
    <Box
      sx={{
        py: 6,
        px: 2,
        textAlign: "center",
        ...sx,
      }}
    >
      <Box
        className="icon-surface"
        sx={{
          width: "44px !important",
          height: "44px !important",
          mx: "auto",
          mb: 1.5,
        }}
      >
        <Icon sx={{ fontSize: 22 }} />
      </Box>
      <Typography fontWeight={650}>{title}</Typography>
      {subtitle ? (
        <Typography variant="body2" color="text.secondary" mt={0.5}>
          {subtitle}
        </Typography>
      ) : null}
      {action ? <Box mt={2}>{action}</Box> : null}
    </Box>
  );
}
