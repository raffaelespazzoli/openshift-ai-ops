import { render, screen, act, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, beforeEach, beforeAll, afterAll, afterEach } from 'vitest';
import { App } from './app';

expect.extend(toHaveNoViolations);

const server = setupServer(
  http.get('/api/v1/incidents', () => {
    return HttpResponse.json({
      data: [],
      meta: { timestamp: new Date().toISOString(), request_id: 'test', page: 1, page_size: 50, total: 0 },
    });
  }),
  http.get('/api/v1/incidents/awaiting-approval', () => {
    return HttpResponse.json({
      data: [
        { id: 'inc-1', state: 'awaiting_approval', severity: 'warning' },
        { id: 'inc-2', state: 'awaiting_approval', severity: 'critical' },
      ],
      meta: { total: 2, timestamp: new Date().toISOString(), request_id: 'test-awaiting' },
    });
  }),
  http.get('/api/v1/events/stream', () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(': keepalive\n\n'));
      },
    });
    return new HttpResponse(stream, {
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

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

  it('displays NotificationBadge with awaiting count', async () => {
    await renderApp();
    await waitFor(() => {
      expect(screen.getByLabelText('2 incidents awaiting approval')).toBeInTheDocument();
    });
  });

  it('hides badge when awaiting count is 0', async () => {
    server.use(
      http.get('/api/v1/incidents/awaiting-approval', () => {
        return HttpResponse.json({
          data: [],
          meta: { total: 0, timestamp: new Date().toISOString(), request_id: 'test-zero' },
        });
      }),
    );
    await renderApp();
    await waitFor(() => {
      expect(screen.queryByLabelText(/incidents awaiting approval/)).not.toBeInTheDocument();
    });
  });

  it('has no accessibility violations', async () => {
    const { container } = await renderApp();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
