import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Bullseye, Spinner } from '@patternfly/react-core';
import { ErrorBoundary } from './error-boundary';
import { OAuthCallback } from './oauth-callback';

const IncidentsPage = lazy(() => import('@features/incidents'));
const StatisticsPage = lazy(() => import('@features/statistics'));

function PageLoader() {
  return (
    <Bullseye>
      <Spinner aria-label="Loading page" />
    </Bullseye>
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
