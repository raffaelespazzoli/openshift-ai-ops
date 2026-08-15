import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe, toHaveNoViolations } from 'jest-axe';
import { http, HttpResponse } from 'msw';
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server } from '@mocks/server';
import IncidentsPage from './index';

expect.extend(toHaveNoViolations);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage(route = '/incidents') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <IncidentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IncidentsPage', () => {
  it('shows skeleton while loading', () => {
    renderPage();
    expect(screen.getByLabelText('Loading incidents')).toBeInTheDocument();
  });

  it('renders incident list after data loads', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('critical')).toBeInTheDocument();
    });
    expect(screen.getByText('warning')).toBeInTheDocument();
    expect(screen.getByText('info')).toBeInTheDocument();
  });

  it('shows the toolbar with Firing/Resolved toggle', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Firing' })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Resolved' })).toBeInTheDocument();
  });

  it('shows empty state when there are no incidents', async () => {
    server.use(
      http.get('/api/v1/incidents', () => {
        return HttpResponse.json({
          data: [],
          meta: {
            timestamp: new Date().toISOString(),
            request_id: 'mock-empty',
            page: 1,
            page_size: 50,
            total: 0,
          },
        });
      }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('No active alerts.')).toBeInTheDocument();
    });
  });

  it('shows error state when the API fails', async () => {
    server.use(
      http.get('/api/v1/incidents', () => {
        return HttpResponse.error();
      }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Unable to reach the API.')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('has no accessibility violations with data', async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(screen.getByText('critical')).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has no accessibility violations in empty state', async () => {
    server.use(
      http.get('/api/v1/incidents', () => {
        return HttpResponse.json({
          data: [],
          meta: {
            timestamp: new Date().toISOString(),
            request_id: 'mock-empty',
            page: 1,
            page_size: 50,
            total: 0,
          },
        });
      }),
    );
    const { container } = renderPage();
    await waitFor(() => {
      expect(screen.getByText('No active alerts.')).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
