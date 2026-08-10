import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Box, Grid, Skeleton } from "@mui/material";
import { AnalysisProvider } from "./context/AnalysisContext";
import AppLayout from "./layout/AppLayout";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const UploadPage = lazy(() => import("./pages/UploadPage"));
const ExtractPage = lazy(() => import("./pages/ExtractPage"));
const AnalyzePage = lazy(() => import("./pages/AnalyzePage"));
const ResultsPage = lazy(() => import("./pages/ResultsPage"));
const DrawingReviewPage = lazy(() => import("./pages/DrawingReviewPage"));
const TakeoffPage = lazy(() => import("./pages/TakeoffPage"));
const ValidationPage = lazy(() => import("./pages/ValidationPage"));
const UnknownReviewPage = lazy(() => import("./pages/UnknownReviewPage"));
const DatasetPage = lazy(() => import("./pages/DatasetPage"));
const TrainingPage = lazy(() => import("./pages/TrainingPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

// Kept for backward-compatible deep links (not in primary nav)
const ModelPage = lazy(() => import("./pages/ModelPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));

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
              <Route path="/" element={<DashboardPage />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/extract" element={<ExtractPage />} />
              <Route path="/analyze" element={<AnalyzePage />} />
              <Route path="/results" element={<ResultsPage />} />
              <Route path="/review-drawing" element={<DrawingReviewPage />} />
              <Route path="/takeoff" element={<TakeoffPage />} />
              <Route path="/prediction" element={<Navigate to="/results" replace />} />
              <Route path="/tokens" element={<Navigate to="/results" replace />} />
              <Route path="/validation" element={<ValidationPage />} />
              <Route path="/review" element={<UnknownReviewPage />} />
              <Route path="/dataset" element={<DatasetPage />} />
              <Route path="/training" element={<TrainingPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/settings" element={<SettingsPage />} />

              {/* Compatibility routes (hidden from primary nav) */}
              <Route path="/model" element={<ModelPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/approved" element={<Navigate to="/review?status=approved" replace />} />
              <Route path="/rejected" element={<Navigate to="/review?status=rejected" replace />} />
              <Route path="/regex" element={<Navigate to="/analytics" replace />} />
              <Route path="/engineering" element={<Navigate to="/validation" replace />} />
              <Route path="/unknown" element={<Navigate to="/review" replace />} />
              <Route path="/retrain" element={<Navigate to="/training" replace />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AnalysisProvider>
    </BrowserRouter>
  );
}
