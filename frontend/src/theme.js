import { alpha, createTheme } from "@mui/material/styles";

export const getTheme = (mode = "dark") => {
  const dark = mode === "dark";
  const border = dark ? "rgba(190,202,220,0.11)" : "rgba(24,35,52,0.10)";
  const primary = dark ? "#7aa2ff" : "#2563eb";

  return createTheme({
    palette: {
      mode,
      primary: {
        main: primary,
        light: dark ? "#a8c2ff" : "#60a5fa",
        dark: dark ? "#4f74d4" : "#1d4ed8",
      },
      success: { main: dark ? "#34d399" : "#059669" },
      warning: { main: dark ? "#fbbf24" : "#d97706" },
      error: { main: dark ? "#f87171" : "#dc2626" },
      info: { main: dark ? "#38bdf8" : "#0284c7" },
      background: {
        default: dark ? "#0b1220" : "#f3f6fb",
        paper: dark ? "#111827" : "#ffffff",
      },
      divider: border,
      text: {
        primary: dark ? "#eef2ff" : "#0f172a",
        secondary: dark ? "#94a3b8" : "#64748b",
      },
      action: {
        hover: dark ? "rgba(148,163,184,0.08)" : "rgba(15,23,42,0.04)",
        selected: alpha(primary, dark ? 0.16 : 0.1),
      },
    },
    typography: {
      fontFamily:
        '"Segoe UI Variable", "Segoe UI", "Geist", "Helvetica Neue", Arial, sans-serif',
      h4: {
        fontWeight: 700,
        letterSpacing: "-0.03em",
        fontSize: "clamp(1.45rem, 2vw, 1.8rem)",
        lineHeight: 1.2,
      },
      h5: { fontWeight: 700, letterSpacing: "-0.02em", fontSize: "1.2rem" },
      h6: { fontWeight: 680, letterSpacing: "-0.015em", fontSize: "1rem" },
      subtitle1: { fontWeight: 650, fontSize: "0.95rem" },
      subtitle2: { fontWeight: 650, fontSize: "0.84rem" },
      body1: { fontSize: "0.925rem", lineHeight: 1.6 },
      body2: { fontSize: "0.84rem", lineHeight: 1.55 },
      button: {
        textTransform: "none",
        fontWeight: 650,
        letterSpacing: "-0.005em",
        fontSize: "0.82rem",
      },
      caption: {
        fontSize: "0.71rem",
        lineHeight: 1.45,
        letterSpacing: "0.015em",
      },
    },
    shape: { borderRadius: 10 },
    spacing: 8,
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          "*": { boxSizing: "border-box" },
          html: { scrollBehavior: "smooth" },
          body: {
            scrollbarWidth: "thin",
            scrollbarColor: dark ? "#303947 transparent" : "#c7cdd5 transparent",
            fontVariantNumeric: "tabular-nums",
          },
          "::selection": { backgroundColor: alpha(primary, 0.28) },
          code: {
            fontFamily: '"JetBrains Mono", "SFMono-Regular", Consolas, monospace',
          },
          ".icon-surface": {
            width: 40,
            height: 40,
            borderRadius: 10,
            display: "grid",
            placeItems: "center",
            color: primary,
            backgroundColor: alpha(primary, dark ? 0.12 : 0.08),
            border: `1px solid ${alpha(primary, 0.14)}`,
          },
          ".metric-tile": {
            minHeight: 78,
            padding: 16,
            borderRadius: 10,
            background: dark ? "rgba(255,255,255,.025)" : "rgba(24,35,52,.025)",
            border: `1px solid ${border}`,
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            border: `1px solid ${border}`,
            borderRadius: 14,
            backgroundImage: "none",
            boxShadow: dark
              ? "0 1px 1px rgba(0,0,0,.18), 0 10px 30px rgba(2,7,14,.09)"
              : "0 1px 2px rgba(20,31,48,.03), 0 10px 28px rgba(20,31,48,.035)",
            transition:
              "border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease",
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: "none" },
          rounded: { borderRadius: 14 },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundImage: "none",
            backgroundColor: dark ? "rgba(12,16,22,.88)" : "rgba(255,255,255,.88)",
            backdropFilter: "blur(16px) saturate(1.3)",
            borderBottom: `1px solid ${border}`,
            color: dark ? "#edf1f7" : "#17202d",
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true, size: "small" },
        styleOverrides: {
          root: {
            borderRadius: 9,
            minHeight: 36,
            paddingInline: 14,
            transition: "background-color 160ms ease, border-color 160ms ease, transform 120ms ease",
            "&:active": { transform: "translateY(1px)" },
            "&.Mui-focusVisible": {
              outline: `2px solid ${alpha(primary, 0.55)}`,
              outlineOffset: 2,
            },
          },
          contained: {
            boxShadow: dark
              ? "0 4px 14px rgba(58,83,142,.2)"
              : "0 4px 12px rgba(41,75,136,.14)",
            "&:hover": {
              boxShadow: dark
                ? "0 6px 18px rgba(58,83,142,.28)"
                : "0 6px 16px rgba(41,75,136,.2)",
            },
          },
          outlined: { borderColor: border },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: {
            borderRadius: 9,
            transition: "background-color 160ms ease, transform 120ms ease",
            "&:active": { transform: "scale(.96)" },
          },
          sizeSmall: { width: 34, height: 34 },
        },
      },
      MuiDrawer: {
        styleOverrides: {
          paper: {
            borderRight: `1px solid ${border}`,
            backgroundImage: "none",
            backgroundColor: dark ? "#10151d" : "#fbfbfc",
          },
        },
      },
      MuiListSubheader: {
        styleOverrides: {
          root: {
            background: "transparent",
            color: dark ? "#6f7a8a" : "#7b8797",
            fontSize: "0.63rem",
            lineHeight: "28px",
            fontWeight: 700,
            letterSpacing: "0.09em",
            textTransform: "uppercase",
            paddingInline: 12,
            marginTop: 5,
          },
        },
      },
      MuiListItemButton: {
        styleOverrides: {
          root: {
            borderRadius: 9,
            minHeight: 38,
            marginBottom: 2,
            paddingInline: 12,
            color: dark ? "#aeb7c4" : "#536174",
            "& .MuiListItemIcon-root": {
              minWidth: 33,
              color: "inherit",
            },
            "&.Mui-selected": {
              color: dark ? "#dbe5ff" : "#284f92",
              backgroundColor: alpha(primary, dark ? 0.14 : 0.085),
              "&:hover": { backgroundColor: alpha(primary, dark ? 0.18 : 0.12) },
            },
          },
        },
      },
      MuiTableContainer: {
        styleOverrides: {
          root: { scrollbarWidth: "thin" },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderColor: border,
            paddingBlock: 12,
            fontSize: "0.8rem",
          },
          head: {
            fontWeight: 650,
            fontSize: "0.68rem",
            letterSpacing: "0.055em",
            textTransform: "uppercase",
            color: dark ? "#7f8a99" : "#6d7888",
            backgroundColor: dark ? "#141a23" : "#f8f9fa",
            whiteSpace: "nowrap",
          },
        },
      },
      MuiTableRow: {
        styleOverrides: {
          root: {
            transition: "background-color 140ms ease",
            "&.Mui-selected": {
              backgroundColor: `${alpha(primary, dark ? 0.1 : 0.06)} !important`,
            },
          },
        },
      },
      MuiTablePagination: {
        styleOverrides: {
          toolbar: { minHeight: 52, paddingInline: 16 },
          selectLabel: { fontSize: "0.75rem" },
          displayedRows: { fontSize: "0.75rem" },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 7,
            fontWeight: 650,
            letterSpacing: "0.005em",
          },
          sizeSmall: { height: 24, fontSize: "0.68rem" },
        },
      },
      MuiTextField: { defaultProps: { size: "small" } },
      MuiFormControl: { defaultProps: { size: "small" } },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            borderRadius: 9,
            backgroundColor: dark ? "rgba(255,255,255,.018)" : "#fff",
            transition: "box-shadow 160ms ease, background-color 160ms ease",
            "&.Mui-focused": { boxShadow: `0 0 0 3px ${alpha(primary, 0.1)}` },
          },
          notchedOutline: { borderColor: border },
          input: { paddingBlock: 9.5, fontSize: "0.82rem" },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: {
            border: `1px solid ${border}`,
            boxShadow: dark
              ? "0 28px 90px rgba(0,0,0,.48)"
              : "0 28px 90px rgba(24,35,52,.2)",
          },
        },
      },
      MuiAlert: {
        styleOverrides: {
          root: { borderRadius: 10, alignItems: "center" },
          standardError: { border: `1px solid ${alpha(dark ? "#e37479" : "#bd3e46", 0.25)}` },
        },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            backgroundColor: alpha(primary, 0.12),
          },
          bar: { borderRadius: 99, transition: "transform 500ms ease" },
        },
      },
      MuiSkeleton: {
        defaultProps: { animation: "wave" },
        styleOverrides: { rounded: { borderRadius: 14 } },
      },
      MuiTooltip: {
        defaultProps: { arrow: true, enterDelay: 350 },
        styleOverrides: {
          tooltip: { fontSize: "0.7rem", borderRadius: 7 },
        },
      },
    },
  });
};
