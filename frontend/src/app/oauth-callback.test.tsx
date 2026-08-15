import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@utils/auth', () => ({
  handleOAuthCallback: vi.fn(),
  initiateOAuthFlow: vi.fn(),
}));

import { OAuthCallback } from './oauth-callback';
import { handleOAuthCallback } from '@utils/auth';

expect.extend(toHaveNoViolations);

beforeEach(() => {
  vi.clearAllMocks();
});

async function renderCallback(route = '/oauth/callback#access_token=tok123&state=s1') {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <MemoryRouter initialEntries={[route]}>
        <OAuthCallback />
      </MemoryRouter>,
    );
  });
  return result;
}

describe('OAuthCallback', () => {
  it('navigates to /incidents on successful token exchange', async () => {
    (handleOAuthCallback as Mock).mockReturnValue(true);
    await renderCallback();
    expect(handleOAuthCallback).toHaveBeenCalledOnce();
    expect(mockNavigate).toHaveBeenCalledWith('/incidents', { replace: true });
  });

  it('shows error state when token exchange fails', async () => {
    (handleOAuthCallback as Mock).mockReturnValue(false);
    await renderCallback('/oauth/callback');
    expect(handleOAuthCallback).toHaveBeenCalledOnce();
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(screen.getByText('Authentication failed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    (handleOAuthCallback as Mock).mockReturnValue(false);
    const { container } = await renderCallback('/oauth/callback');
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
