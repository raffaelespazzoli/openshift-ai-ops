import { type ReactNode, useEffect, useState } from 'react';
import { Bullseye, Spinner } from '@patternfly/react-core';
import { isAuthenticated, initiateOAuthFlow } from '@utils/auth';

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (isAuthenticated()) {
      setChecking(false);
      return;
    }
    initiateOAuthFlow();
  }, []);

  if (checking) {
    return (
      <Bullseye>
        <Spinner aria-label="Authenticating" />
      </Bullseye>
    );
  }

  return <>{children}</>;
}
