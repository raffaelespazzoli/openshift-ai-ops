import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bullseye,
  Spinner,
  EmptyState,
  EmptyStateBody,
  EmptyStateActions,
  EmptyStateFooter,
  Button,
} from '@patternfly/react-core';
import { handleOAuthCallback, initiateOAuthFlow } from '@utils/auth';

export function OAuthCallback() {
  const navigate = useNavigate();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const success = handleOAuthCallback();
    if (success) {
      navigate('/incidents', { replace: true });
    } else {
      setFailed(true);
    }
  }, [navigate]);

  if (failed) {
    return (
      <Bullseye>
        <EmptyState headingLevel="h2" titleText="Authentication failed">
          <EmptyStateBody>
            Unable to complete sign-in. The token may be missing or the session expired.
          </EmptyStateBody>
          <EmptyStateFooter>
            <EmptyStateActions>
              <Button variant="primary" onClick={() => initiateOAuthFlow()}>
                Try again
              </Button>
            </EmptyStateActions>
          </EmptyStateFooter>
        </EmptyState>
      </Bullseye>
    );
  }

  return (
    <Bullseye>
      <Spinner aria-label="Completing authentication" />
    </Bullseye>
  );
}
