// "Locate on plan": where one printed grid location is on the plans. The
// backend reads the literal grid axes (C.1-5.1 is where the axis labelled
// C.1 crosses the axis labelled 5.1), looks for a column symbol there and
// places a printed offset only at a validated scale. This module shows
// the result: a default plan, a selector for the other plans / views, the
// result state in plain words and a small preview around the location.
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Tab,
  Tabs,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { CloseOutlined, PlaceOutlined } from "@mui/icons-material";
import { locateOnPlan, fetchPageCrop } from "../../api/client";
import { SourcePdf } from "./pdf";

// One request per document / location / scope, shared by the preview and the dialog.
const LocationCache = createContext(null);

export function LocationProvider({ profile, children }) {
  // A fresh extraction replaces the profile even when the document id stays the same.
  const scope = useMemo(() => ({ profile, requests: new Map() }), [profile]);
  return <LocationCache.Provider value={scope.requests}>{children}</LocationCache.Provider>;
}

export function fetchLocation(documentId, location, scheduleId, cache = new Map()) {
  const key = `${documentId}|${scheduleId || ""}|${location}`;
  if (!cache.has(key)) {
    cache.set(key, locateOnPlan(documentId, location, scheduleId).catch((error) => {
      cache.delete(key);
      throw error;
    }));
  }
  return cache.get(key);
}

export function useLocation(documentId, location, scheduleId, enabled = true) {
  const sharedCache = useContext(LocationCache);
  const privateCache = useMemo(() => new Map(), []);
  const cache = sharedCache || privateCache;
  const [state, setState] = useState({ loading: Boolean(enabled && documentId && location), result: null, error: null });
  useEffect(() => {
    if (!enabled || !documentId || !location) return undefined;
    let live = true;
    setState({ loading: true, result: null, error: null });
    fetchLocation(documentId, location, scheduleId, cache)
      .then((result) => live && setState({ loading: false, result, error: null }))
      .catch((error) => live && setState({
        loading: false, result: null, error: error.friendlyMessage || "The plans could not be searched.",
      }));
    return () => {
      live = false;
    };
  }, [documentId, location, scheduleId, enabled, cache]);
  return state;
}

// Result states in plain words. "Not detected" is never "absent".
export const LOCATE_STATE = {
  column_symbol: "Possible column symbol drawn here",
  column_symbol_at_offset: "Possible column symbol drawn at the printed offset",
  intersection_only: "Grid intersection identified; column not confirmed",
  offset_candidate: "Possible column symbol near the offset; scale only printed, not validated",
  offset_unresolved: "Offset direction or scale unresolved",
};
const STATUS_TEXT = {
  column_symbol: "Possible column symbol drawn on the plan",
  intersection_only: "Grid intersection identified; no column symbol confirmed",
  offset_unresolved: "Offset direction or scale unresolved",
  plan_not_found: "Relevant plan not found",
  not_a_grid_location: "Not a grid location",
};

const viewLabel = (view) => [view.sheet || `p. ${view.page}`, view.view_title && view.view_title.toLowerCase()]
  .filter(Boolean).join(" · ");

/** The plan views of a result as sources the viewer can switch between. */
export function locateSources(result, location) {
  return (result?.views || []).map((view, i, all) => ({
    page: view.page,
    sheet: view.sheet,
    bbox: view.target_bbox,
    mark: `${location} on ${view.sheet || `p. ${view.page}`}`,
    tab: `Plan ${view.sheet || `p. ${view.page}`}${all.filter((v) => v.page === view.page).length > 1 ? ` (${i + 1})` : ""}`,
  }));
}

/** Grid intersections a summary is about to look up, one button per location. */
export function LocateButton({ location, onLocate, compact = false }) {
  if (!onLocate || !location) return null;
  return (
    <Button size="small" startIcon={compact ? null : <PlaceOutlined fontSize="small" />} onClick={() => onLocate(location)}
      aria-label={`Locate ${location} on plan`} sx={{ whiteSpace: "nowrap", minWidth: 0, px: compact ? 0.5 : undefined }}>
      {compact ? location : "Locate"}
    </Button>
  );
}

function ViewFacts({ view }) {
  const offset = view.offset;
  const support = (view.nearby_text || []).filter((n) => /^(?:P|F|M|WF|RW|S\.?O\.?G)\.?\d|\{|\[/.test(n.text)).slice(0, 6);
  return (
    <Stack spacing={0.5} sx={{ px: 2, py: 1 }}>
      <Typography variant="body2" fontWeight={600}>{LOCATE_STATE[view.state] || view.state}</Typography>
      {view.scope?.note && (
        <Typography variant="caption" color={view.scope.status === "unresolved" ? "warning.main" : "text.secondary"}>
          Building / area: {view.scope.note}
        </Typography>
      )}
      {offset?.note && <Typography variant="caption" color="text.secondary">Offset: {offset.note}</Typography>}
      {offset && view.scale?.note && (
        <Typography variant="caption" color="text.secondary">Scale: {view.scale.note}</Typography>
      )}
      {support.length > 0 && (
        <Typography variant="caption" color="text.secondary">
          Printed at the location: {support.map((n) => n.text).join(" · ")} — shown as printed, not linked.
        </Typography>
      )}
    </Stack>
  );
}

/** Dialog: the default plan with the location highlighted, other plans one tab away. */
export function LocateDialog({ documentId, request, onClose }) {
  const fullScreen = useMediaQuery(useTheme().breakpoints.down("md"));
  const { loading, result, error } = useLocation(documentId, request?.location, request?.scheduleId, Boolean(request));
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(result?.default ?? 0), [result]);
  if (!request) return null;
  const views = result?.views || [];
  const view = views[index];
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="lg" fullScreen={fullScreen} aria-labelledby="summary-locate-title">
      <DialogTitle id="summary-locate-title" sx={{ pr: 6 }}>
        <Box component="span" sx={{ fontFamily: "monospace" }}>{request.location}</Box> on the plans
        {result && (
          <Typography component="span" variant="body2" color="text.secondary" sx={{ display: "block" }}>
            {STATUS_TEXT[result.status] || result.status}
            {result.note ? ` — ${result.note}` : ""}
          </Typography>
        )}
      </DialogTitle>
      <IconButton aria-label="Close plan view" onClick={onClose} sx={{ position: "absolute", right: 8, top: 8 }}>
        <CloseOutlined />
      </IconButton>
      {loading && (
        <Box sx={{ display: "grid", placeItems: "center", p: 4 }}><CircularProgress size={28} /></Box>
      )}
      {error && <Alert severity="warning" variant="outlined" sx={{ m: 2 }}>{error}</Alert>}
      {views.length > 1 && (
        <Tabs value={index} onChange={(_event, value) => setIndex(value)} variant="scrollable" allowScrollButtonsMobile
          aria-label="Plans showing this location" sx={{ px: 1, borderBottom: 1, borderColor: "divider" }}>
          {views.map((v, i) => (
            <Tab key={`${v.page}-${i}`} value={i} label={viewLabel(v)} id={`summary-locate-tab-${i}`}
              aria-controls="summary-locate-panel" />
          ))}
        </Tabs>
      )}
      {view && <ViewFacts view={view} />}
      {result?.other_scope_views?.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ px: 2, pb: 1 }}>
          Also printed on views of another building / area, not used:{" "}
          {[...new Set(result.other_scope_views.map(viewLabel))].join("; ")}
        </Typography>
      )}
      {view && (
        <DialogContent dividers id="summary-locate-panel" role={views.length > 1 ? "tabpanel" : undefined}
          sx={{ p: 0, height: fullScreen ? "100%" : "64vh" }}>
          <SourcePdf documentId={documentId} source={{ page: view.page, bbox: view.target_bbox }}
            selectionKey={`locate-${request.location}-${view.page}-${index}`} />
        </DialogContent>
      )}
    </Dialog>
  );
}

const PREVIEW_MARGIN = 90;

function CropPreview({ documentId, view, location }) {
  const [preview, setPreview] = useState(null);
  const [failed, setFailed] = useState(false);
  const [x0, y0, x1, y1] = view.target_bbox;
  useEffect(() => {
    let live = true;
    let url;
    setPreview(null);
    setFailed(false);
    fetchPageCrop(documentId, view.page,
      [x0 - PREVIEW_MARGIN, y0 - PREVIEW_MARGIN, x1 + PREVIEW_MARGIN, y1 + PREVIEW_MARGIN], 360)
      .then((blob) => {
        if (live) { url = URL.createObjectURL(blob); setPreview(url); }
      })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [documentId, view.page, x0, y0, x1, y1]);
  if (failed) return <Typography variant="caption">Preview unavailable. Open the plan to inspect the source.</Typography>;
  if (!preview) return <CircularProgress size={16} aria-label="Loading plan preview" />;
  return <Box component="img" alt={`Plan ${view.sheet || view.page} around ${location}`} src={preview}
    sx={{ width: 220, maxWidth: "100%", border: 1, borderColor: "divider", borderRadius: 1, bgcolor: "#fff" }} />;
}

/** A small crop of the default plan around the location, with its state. */
export function PlanPreview({ documentId, location, scheduleId, onOpen }) {
  const { loading, result, error } = useLocation(documentId, location, scheduleId);
  if (!documentId || !location) return null;
  const view = result?.views?.[result.default ?? 0];
  const box = view?.target_bbox;
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        On the plans{view ? ` — ${viewLabel(view)} (preview, not to scale)` : ""}
      </Typography>
      {loading && <CircularProgress size={16} />}
      {error && <Typography variant="body2" color="warning.main">{error}</Typography>}
      {result && !view && (
        <Typography variant="body2" color="text.secondary">
          {STATUS_TEXT[result.status] || result.status}{result.note ? ` — ${result.note}` : ""}
        </Typography>
      )}
      {view && box && (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
          <CropPreview documentId={documentId} view={view} location={location} />
          <Stack spacing={0.5} sx={{ alignItems: "flex-start" }}>
            <Typography variant="body2" fontWeight={600}>{LOCATE_STATE[view.state] || view.state}</Typography>
            <Typography variant="caption" color="text.secondary">
              {result.views.length} plan view{result.views.length === 1 ? "" : "s"} print this location
            </Typography>
            {onOpen && (
              <Button size="small" variant="outlined" startIcon={<PlaceOutlined fontSize="small" />}
                onClick={() => onOpen(location)} aria-label={`Open the plans at ${location}`}>
                Open plan
              </Button>
            )}
          </Stack>
        </Stack>
      )}
    </Box>
  );
}
