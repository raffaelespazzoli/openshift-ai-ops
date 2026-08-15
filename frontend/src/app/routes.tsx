import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Skeleton } from '@patternfly/react-core';
import { ErrorBoundary } from './error-boundary';
import { OAuthCallback } from './oauth-callback';

const IncidentsPage = lazy(() => import('@features/incidents'));
const IncidentDetailPage = lazy(() => import('@features/incidents/pages/incident-detail'));
const StatisticsPage = lazy(() => import('@features/statistics'));

function PageLoader() {
  return (
    <div role="status" aria-label="Loading page" aria-busy="true" style={{ padding: '24px' }}>
      <Skeleton width="30%" height="28px" style={{ marginBottom: '16px' }} screenreaderText="Page heading loading" />
      <Skeleton width="100%" height="300px" screenreaderText="Page content loading" />
    </div>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route
          path="/incidents"
          element={
            <ErrorBoundary>
              <IncidentsPage />
            </ErrorBoundary>
          }
        />
        <Route
          path="/incidents/:id"
          element={
            <ErrorBoundary>
              <IncidentDetailPage />
            </ErrorBoundary>
          }
        />
        <Route
          path="/statistics"
          element={
            <ErrorBoundary>
              <StatisticsPage />
            </ErrorBoundary>
          }
        />
        <Route path="*" element={<Navigate to="/incidents" replace />} />
      </Routes>
    </Suspense>
  );
}
