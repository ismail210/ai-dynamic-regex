import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  AppBar,
  Box,
  Divider,
  Drawer,
  IconButton,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  Brightness4,
  Brightness7,
  DashboardOutlined,
  DatasetOutlined,
  FactCheckOutlined,
  InsightsOutlined,
  ModelTrainingOutlined,
  RateReviewOutlined,
  RestartAltOutlined,
  SettingsOutlined,
  TableRowsOutlined,
  UploadFileOutlined,
  HubOutlined,
  ManageSearchOutlined,
  ViewListOutlined,
} from "@mui/icons-material";
import { useThemeMode } from "../context/ThemeContext";
import { useAnalysis } from "../context/AnalysisContext";

const DRAWER_WIDTH = 260;

const WORKFLOW_ITEMS = [
  { to: "/upload", label: "Upload", icon: UploadFileOutlined },
  { to: "/extract", label: "Extract", icon: ManageSearchOutlined },
  { to: "/analyze", label: "Analyze", icon: HubOutlined },
  { to: "/results", label: "Results", icon: TableRowsOutlined },
  { to: "/validation", label: "Validation", icon: FactCheckOutlined },
  { to: "/review", label: "Corrections", icon: RateReviewOutlined },
  { to: "/takeoff", label: "Takeoff", icon: ViewListOutlined },
];

const OPERATIONS_ITEMS = [
  { to: "/", label: "Dashboard", icon: DashboardOutlined },
  { to: "/dataset", label: "Dataset", icon: DatasetOutlined },
  { to: "/training", label: "Training", icon: ModelTrainingOutlined },
  { to: "/analytics", label: "Analytics", icon: InsightsOutlined },
  { to: "/settings", label: "Settings", icon: SettingsOutlined },
];
const NAV_ITEMS = [...WORKFLOW_ITEMS, ...OPERATIONS_ITEMS];

export default function AppLayout() {
  const { mode, toggleMode } = useThemeMode();
  const location = useLocation();
  const navigate = useNavigate();
  const { stage, rehydrating, rehydrationError, startNewAnalysis } = useAnalysis();
  const title =
    NAV_ITEMS.find((item) => item.to === location.pathname)?.label ||
    "Steel Takeoff";

  const drawer = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Box
        sx={{
          px: 2.5,
          py: 2.25,
          display: "flex",
          alignItems: "center",
          gap: 1.35,
          borderBottom: 1,
          borderColor: "divider",
        }}
      >
        <Box
          sx={{
            width: 38,
            height: 38,
            borderRadius: 2,
            bgcolor: "primary.main",
            display: "grid",
            placeItems: "center",
            color: mode === "dark" ? "#0b1220" : "#fff",
            boxShadow: "0 8px 20px rgba(37,99,235,.28)",
          }}
        >
          <HubOutlined sx={{ fontSize: 20 }} />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            fontWeight={760}
            fontSize={14.5}
            letterSpacing="-0.03em"
            sx={{ lineHeight: 1.15 }}
          >
            Steel Takeoff AI
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Structural validation platform
          </Typography>
        </Box>
      </Box>

      <Box component="nav" sx={{ flex: 1, overflowY: "auto", py: 1.5, px: 1.25 }}>
        <List dense disablePadding>
          <ListSubheader disableSticky>Workflow</ListSubheader>
          {WORKFLOW_ITEMS.map(({ to, label, icon: Icon }) => (
            <ListItemButton
              key={to}
              component={NavLink}
              to={to}
              end={to === "/"}
              selected={location.pathname === to}
            >
              <ListItemIcon>
                <Icon sx={{ fontSize: 19 }} />
              </ListItemIcon>
              <ListItemText
                primary={label}
                slotProps={{ primary: { fontSize: 13.5, fontWeight: 600 } }}
              />
            </ListItemButton>
          ))}
          <ListSubheader disableSticky sx={{ mt: 1 }}>Operations</ListSubheader>
          {OPERATIONS_ITEMS.map(({ to, label, icon: Icon }) => (
            <ListItemButton
              key={to}
              component={NavLink}
              to={to}
              end={to === "/"}
              selected={location.pathname === to}
            >
              <ListItemIcon>
                <Icon sx={{ fontSize: 19 }} />
              </ListItemIcon>
              <ListItemText
                primary={label}
                slotProps={{ primary: { fontSize: 13.5, fontWeight: 600 } }}
              />
            </ListItemButton>
          ))}
        </List>
      </Box>

      <Divider />
      <Box sx={{ px: 2.5, py: 1.75 }}>
        <Typography variant="caption" color="text.secondary" display="block">
          v6 · Staged multimodal workflow
        </Typography>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100dvh", bgcolor: "background.default" }}>
      {/* Permanent left sidebar — no hamburger menu */}
      <Drawer
        variant="permanent"
        open
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
          },
        }}
      >
        {drawer}
      </Drawer>

      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{
          width: `calc(100% - ${DRAWER_WIDTH}px)`,
          ml: `${DRAWER_WIDTH}px`,
        }}
      >
        <Toolbar sx={{ minHeight: "56px !important", px: { xs: 2, md: 3.5 } }}>
          <Typography variant="subtitle1" sx={{ flex: 1 }}>
            {title}
          </Typography>
          {stage !== "empty" && (
            <Tooltip title="Start new analysis (clears the active document)">
              <IconButton
                onClick={() => {
                  startNewAnalysis();
                  navigate("/upload");
                }}
                size="small"
                aria-label="Start new analysis"
              >
                <RestartAltOutlined fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title={mode === "dark" ? "Light mode" : "Dark mode"}>
            <IconButton onClick={toggleMode} size="small" aria-label="Toggle color mode">
              {mode === "dark" ? <Brightness7 fontSize="small" /> : <Brightness4 fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Toolbar>
        {rehydrating && <LinearProgress />}
      </AppBar>

      <Box
        component="main"
        id="main-content"
        sx={{
          flexGrow: 1,
          minWidth: 0,
          mt: "56px",
          minHeight: "calc(100dvh - 56px)",
        }}
      >
        <Box
          sx={{
            width: "100%",
            maxWidth: 1440,
            mx: "auto",
            px: { xs: 2, sm: 2.75, lg: 3.5 },
            py: { xs: 2.25, sm: 3, lg: 3.5 },
          }}
        >
          {rehydrationError && (
            <Alert severity="warning" variant="outlined" sx={{ mb: 2 }}>
              {rehydrationError}
            </Alert>
          )}
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
