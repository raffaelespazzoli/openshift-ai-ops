import { type ReactNode, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Bullseye,
  EmptyState,
  EmptyStateBody,
  Spinner,
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
      <Bullseye>
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
      </Bullseye>
    );
  }

  if (checking) {
    return (
      <Bullseye>
        <Spinner aria-label="Authenticating" />
      </Bullseye>
    );
  }

  return <>{children}</>;
}
