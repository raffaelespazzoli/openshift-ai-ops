const TOKEN_KEY = 'oauth_token';
const OAUTH_STATE_KEY = 'oauth_state';

function generateState(): string {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function shouldUseClientOAuth(): boolean {
  return Boolean(import.meta.env.VITE_OAUTH_URL);
}

export function isAuthenticated(): boolean {
  if (import.meta.env.DEV && import.meta.env.VITE_DEV_TOKEN) return true;
  if (getStoredToken() !== null) return true;
  // Cluster deploys sit behind oauth-proxy; the SPA has already passed OpenShift login.
  return !shouldUseClientOAuth();
}

export function initiateOAuthFlow(): void {
  const oauthUrl = import.meta.env.VITE_OAUTH_URL;
  if (!oauthUrl) {
    console.error('VITE_OAUTH_URL is not configured');
    return;
  }

  const state = generateState();
  localStorage.setItem(OAUTH_STATE_KEY, state);

  const redirectUri = `${window.location.origin}/oauth/callback`;
  const params = new URLSearchParams({
    response_type: 'token',
    client_id: 'openshift-ai-ops',
    redirect_uri: redirectUri,
    state,
  });

  window.location.href = `${oauthUrl}?${params.toString()}`;
}

export function handleOAuthCallback(): boolean {
  const hash = window.location.hash.substring(1);
  if (!hash) return false;

  const params = new URLSearchParams(hash);
  const token = params.get('access_token');
  const state = params.get('state');
  const storedState = localStorage.getItem(OAUTH_STATE_KEY);

  if (!token || !state || state !== storedState) {
    localStorage.removeItem(OAUTH_STATE_KEY);
    return false;
  }

  storeToken(token);
  localStorage.removeItem(OAUTH_STATE_KEY);
  window.history.replaceState(null, '', window.location.pathname);
  return true;
}
