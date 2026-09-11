import { lazy, Suspense } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { Box, Grid, Skeleton } from "@mui/material";
import { AnalysisProvider } from "./context/AnalysisContext";
import AppLayout from "./layout/AppLayout";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const UploadExtractPage = lazy(() => import("./pages/UploadExtractPage"));
const DrawingSummaryPage = lazy(() => import("./pages/DrawingSummaryPage"));
const AnalysisResultsPage = lazy(() => import("./pages/AnalysisResultsPage"));
const DrawingReviewPage = lazy(() => import("./pages/DrawingReviewPage"));
const TakeoffPage = lazy(() => import("./pages/TakeoffPage"));
const ValidationPage = lazy(() => import("./pages/ValidationPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

// Kept for backward-compatible deep links (not in primary nav)
const UnknownReviewPage = lazy(() => import("./pages/UnknownReviewPage"));
const DatasetPage = lazy(() => import("./pages/DatasetPage"));
const TrainingPage = lazy(() => import("./pages/TrainingPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const ModelPage = lazy(() => import("./pages/ModelPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));

// `<Navigate>` drops the current query string. Old deep links carry state we
// must keep — `/review-drawing?object=<id>` (locate on drawing),
// `/review?status=<x>` — so redirect while preserving `location.search`.
function RedirectWithSearch({ to }) {
  const { search } = useLocation();
  return <Navigate to={{ pathname: to, search }} replace />;
}

function Fallback() {
  return (
    <Box py={1}>
      <Skeleton width={220} height={44} />
      <Skeleton width={380} height={24} sx={{ mb: 3 }} />
      <Grid container spacing={2}>
        {[1, 2, 3, 4].map((item) => (
          <Grid size={{ xs: 6, lg: 3 }} key={item}>
            <Skeleton variant="rounded" height={116} />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AnalysisProvider>
        <Suspense fallback={<Fallback />}>
          <Routes>
            <Route element={<AppLayout />}>
              {/* Primary workflow */}
              <Route path="/" element={<DashboardPage />} />
              <Route path="/upload-extract" element={<UploadExtractPage />} />
              <Route path="/drawing-summary" element={<DrawingSummaryPage />} />
              <Route path="/analysis" element={<AnalysisResultsPage />} />
              <Route path="/review-drawing" element={<DrawingReviewPage />} />
              <Route path="/validation" element={<ValidationPage />} />
              <Route path="/takeoff" element={<TakeoffPage />} />
              <Route path="/settings" element={<SettingsPage />} />

              {/* Consolidated pages — old routes redirect (query string preserved) */}
              <Route path="/upload" element={<RedirectWithSearch to="/upload-extract" />} />
              <Route path="/extract" element={<RedirectWithSearch to="/upload-extract" />} />
              <Route path="/analyze" element={<RedirectWithSearch to="/analysis" />} />
              <Route path="/results" element={<RedirectWithSearch to="/analysis" />} />
              <Route path="/prediction" element={<RedirectWithSearch to="/analysis" />} />
              <Route path="/tokens" element={<RedirectWithSearch to="/analysis" />} />
              <Route path="/corrections" element={<RedirectWithSearch to="/review-drawing" />} />

              {/* Off-nav but URL-reachable (operations / compatibility) */}
              <Route path="/review" element={<UnknownReviewPage />} />
              <Route path="/dataset" element={<DatasetPage />} />
              <Route path="/training" element={<TrainingPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/model" element={<ModelPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/approved" element={<Navigate to="/review?status=approved" replace />} />
              <Route path="/rejected" element={<Navigate to="/review?status=rejected" replace />} />
              <Route path="/regex" element={<RedirectWithSearch to="/analytics" />} />
              <Route path="/engineering" element={<RedirectWithSearch to="/validation" />} />
              <Route path="/unknown" element={<RedirectWithSearch to="/review" />} />
              <Route path="/retrain" element={<RedirectWithSearch to="/training" />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AnalysisProvider>
    </BrowserRouter>
  );
}
