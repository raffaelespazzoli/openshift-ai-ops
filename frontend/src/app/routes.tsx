import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Skeleton } from '@patternfly/react-core';
import { ErrorBoundary } from './error-boundary';
import { OAuthCallback } from './oauth-callback';

const IncidentsPage = lazy(() => import('@features/incidents'));
const StatisticsPage = lazy(() => import('@features/statistics'));

function PageLoader() {
  return (
    <div aria-label="Loading page" aria-busy="true" style={{ padding: '24px' }}>
      <Skeleton width="30%" height="28px" style={{ marginBottom: '16px' }} aria-label="Page heading loading" />
      <Skeleton width="100%" height="300px" aria-label="Page content loading" />
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
