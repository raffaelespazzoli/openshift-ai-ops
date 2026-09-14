import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

vi.mock('@utils/auth', () => ({
  isAuthenticated: vi.fn(),
  initiateOAuthFlow: vi.fn(),
  shouldUseClientOAuth: vi.fn(),
}));

import { AuthGuard } from './auth-guard';
import { isAuthenticated, initiateOAuthFlow, shouldUseClientOAuth } from '@utils/auth';

expect.extend(toHaveNoViolations);

beforeEach(() => {
  vi.clearAllMocks();
});

async function renderGuard(route = '/incidents') {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <MemoryRouter initialEntries={[route]}>
        <AuthGuard>
          <div data-testid="protected">Protected content</div>
        </AuthGuard>
      </MemoryRouter>,
    );
  });
  return result;
}

describe('AuthGuard', () => {
  it('renders children when user is authenticated', async () => {
    (isAuthenticated as Mock).mockReturnValue(true);
    await renderGuard();
    expect(screen.getByTestId('protected')).toBeInTheDocument();
    expect(initiateOAuthFlow).not.toHaveBeenCalled();
  });

  it('redirects unauthenticated users via OAuth flow', async () => {
    (isAuthenticated as Mock).mockReturnValue(false);
    (shouldUseClientOAuth as Mock).mockReturnValue(true);
    await renderGuard();
    expect(initiateOAuthFlow).toHaveBeenCalledOnce();
    expect(screen.queryByTestId('protected')).not.toBeInTheDocument();
  });

  it('shows error state when OAuth is misconfigured', async () => {
    (isAuthenticated as Mock).mockReturnValue(false);
    (shouldUseClientOAuth as Mock).mockReturnValue(true);
    await renderGuard();
    expect(screen.getByText('Authentication configuration error')).toBeInTheDocument();
    expect(
      screen.getByText(/contact an administrator/i),
    ).toBeInTheDocument();
  });

  it('allows access when auth is handled by oauth-proxy', async () => {
    (isAuthenticated as Mock).mockReturnValue(false);
    (shouldUseClientOAuth as Mock).mockReturnValue(false);
    await renderGuard();
    expect(screen.getByTestId('protected')).toBeInTheDocument();
    expect(initiateOAuthFlow).not.toHaveBeenCalled();
  });

  it('allows /oauth/callback through without authentication', async () => {
    (isAuthenticated as Mock).mockReturnValue(false);
    await renderGuard('/oauth/callback#access_token=abc');
    expect(screen.getByTestId('protected')).toBeInTheDocument();
    expect(initiateOAuthFlow).not.toHaveBeenCalled();
  });

  it('has no accessibility violations', async () => {
    (isAuthenticated as Mock).mockReturnValue(true);
    const { container } = await renderGuard();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
