import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, beforeEach } from 'vitest';
import { App } from './app';

expect.extend(toHaveNoViolations);

async function renderApp(route = '/incidents') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });

  return result;
}

describe('App Shell', () => {
  beforeEach(() => {
    document.documentElement.classList.add('pf-v6-theme-dark');
  });

  it('renders the masthead with brand text', async () => {
    await renderApp();
    expect(screen.getByText('OpenShift AI Ops')).toBeInTheDocument();
  });

  it('renders both navigation items', async () => {
    await renderApp();
    const nav = screen.getByLabelText('Main navigation');
    expect(nav).toHaveTextContent('Incidents');
    expect(nav).toHaveTextContent('Statistics');
  });

  it('defaults to dark mode', async () => {
    await renderApp();
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(true);
  });

  it('renders the theme toggle button', async () => {
    await renderApp();
    expect(screen.getByLabelText('Switch to light mode')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = await renderApp();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
