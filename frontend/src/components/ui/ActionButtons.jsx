import { Button, CircularProgress, IconButton, Tooltip } from "@mui/material";

export function TipIconButton({ title, children, ...props }) {
  return (
    <Tooltip title={title}>
      <span>
        <IconButton size="small" {...props}>
          {children}
        </IconButton>
      </span>
    </Tooltip>
  );
}

export function TipButton({ title, loading, startIcon, children, ...props }) {
  return (
    <Tooltip title={title || ""} disableHoverListener={!title}>
      <span>
        <Button
          startIcon={
            loading ? <CircularProgress size={14} color="inherit" /> : startIcon
          }
          disabled={loading || props.disabled}
          {...props}
        >
          {children}
        </Button>
      </span>
    </Tooltip>
  );
}
