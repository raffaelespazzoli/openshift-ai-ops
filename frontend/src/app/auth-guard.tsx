import { type ReactNode, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Bullseye, Spinner } from '@patternfly/react-core';
import { isAuthenticated, initiateOAuthFlow } from '@utils/auth';

const PUBLIC_PATHS = ['/oauth/callback'];

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { pathname } = useLocation();
  const [checking, setChecking] = useState(true);

  const isPublicPath = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  useEffect(() => {
    if (isPublicPath || isAuthenticated()) {
      setChecking(false);
      return;
    }
    initiateOAuthFlow();
  }, [isPublicPath]);

  if (checking) {
    return (
      <Bullseye>
        <Spinner aria-label="Authenticating" />
      </Bullseye>
    );
  }

  return <>{children}</>;
}
