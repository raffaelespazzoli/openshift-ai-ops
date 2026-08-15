import { type ReactNode, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  EmptyState,
  EmptyStateBody,
  Skeleton,
} from '@patternfly/react-core';
import { ExclamationCircleIcon } from '@patternfly/react-icons';
import { isAuthenticated, initiateOAuthFlow } from '@utils/auth';

const PUBLIC_PATHS = ['/oauth/callback'];

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { pathname } = useLocation();
  const [checking, setChecking] = useState(true);
  const [authError, setAuthError] = useState(false);

  const isPublicPath = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  useEffect(() => {
    if (isPublicPath || isAuthenticated()) {
      setChecking(false);
      return;
    }
    initiateOAuthFlow();

    // If we're still here after initiateOAuthFlow, OAuth is misconfigured
    if (!isAuthenticated()) {
      setAuthError(true);
      setChecking(false);
    }
  }, [isPublicPath]);

  if (authError) {
    return (
      <EmptyState
        headingLevel="h2"
        icon={ExclamationCircleIcon}
        titleText="Authentication configuration error"
        status="danger"
      >
        <EmptyStateBody>
          Unable to initiate authentication. Please contact an administrator
          to verify the OAuth configuration.
        </EmptyStateBody>
      </EmptyState>
    );
  }

  if (checking) {
    return (
      <div aria-label="Authenticating" aria-busy="true">
        <Skeleton height="60px" aria-label="Masthead loading" />
        <div style={{ display: 'flex', height: 'calc(100vh - 60px)' }}>
          <Skeleton width="250px" height="100%" aria-label="Sidebar loading" />
          <div style={{ flex: 1, padding: '24px' }}>
            <Skeleton width="40%" height="28px" style={{ marginBottom: '16px' }} aria-label="Content heading loading" />
            <Skeleton width="100%" height="200px" aria-label="Content loading" />
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
