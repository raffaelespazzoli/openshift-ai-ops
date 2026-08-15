import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bullseye, Spinner } from '@patternfly/react-core';
import { handleOAuthCallback } from '@utils/auth';

export function OAuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    const success = handleOAuthCallback();
    navigate(success ? '/incidents' : '/incidents', { replace: true });
  }, [navigate]);

  return (
    <Bullseye>
      <Spinner aria-label="Completing authentication" />
    </Bullseye>
  );
}
