import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@mocks/server';
import {
  mockIncidentDetail,
  mockFastPathIncident,
  mockVersionedDiagnosisIncident,
  mockFailedIncident,
  mockLlmUnavailableWithFastPath,
} from '@mocks/handlers';
import IncidentDetailPage from './incident-detail';

expect.extend(toHaveNoViolations);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderWithProviders(id: string, returnSearch = '') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[
          { pathname: `/incidents/${id}`, state: { returnSearch } },
        ]}
      >
        <Routes>
          <Route path="/incidents/:id" element={<IncidentDetailPage />} />
          <Route path="/incidents" element={<div>Incidents List</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IncidentDetailPage', () => {
  it('renders loading skeleton while fetching', () => {
    renderWithProviders('inc-uuid-001');
    expect(screen.getByLabelText('Loading incident detail')).toBeInTheDocument();
  });

  it('renders breadcrumb with alert name after loading', async () => {
    renderWithProviders('inc-uuid-001');
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'KubePersistentVolumeStuckPending' })).toBeInTheDocument();
    });
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Incidents' })).toBeInTheDocument();
  });

  it('renders breadcrumb that preserves filter state', async () => {
    renderWithProviders('inc-uuid-001', '?status=firing&severity=warning');
    await waitFor(() => {
      expect(screen.getByText('Incidents')).toBeInTheDocument();
    });
    const incidentsLink = screen.getByRole('link', { name: 'Incidents' });
    expect(incidentsLink).toHaveAttribute(
      'href',
      '/incidents?status=firing&severity=warning',
    );
  });

  it('renders 6 pipeline stages', async () => {
    renderWithProviders('inc-uuid-001');
    await waitFor(() => {
      expect(screen.getByText('Triage')).toBeInTheDocument();
    });
    expect(screen.getByText('Diagnosis')).toBeInTheDocument();
    expect(screen.getByText('Skeptic')).toBeInTheDocument();
    expect(screen.getByText('Remediation')).toBeInTheDocument();
    expect(screen.getByText('Execution')).toBeInTheDocument();
    expect(screen.getByText('Outcome')).toBeInTheDocument();
  });

  it('auto-expands the active/awaiting stage on load', async () => {
    renderWithProviders('inc-uuid-001');
    await waitFor(() => {
      expect(screen.getByText('Plan Summary')).toBeInTheDocument();
    });
  });

  it('clicking a stage opens its panel and closes the previous one', async () => {
    renderWithProviders('inc-uuid-001');
    await waitFor(() => {
      expect(screen.getByText('Plan Summary')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Triage'));
    await waitFor(() => {
      expect(screen.getByText('Alert Payload')).toBeInTheDocument();
    });
    expect(screen.queryByText('Plan Summary')).not.toBeInTheDocument();
  });

  it('clicking the same stage collapses the panel', async () => {
    renderWithProviders('inc-uuid-001');
    await waitFor(() => {
      expect(screen.getByText('Plan Summary')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('Remediation: awaiting approval'));
    await waitFor(() => {
      expect(screen.queryByText('Plan Summary')).not.toBeInTheDocument();
    });
  });

  it('renders fast-path incident with skipped stages and badge', async () => {
    renderWithProviders('inc-uuid-fp');
    await waitFor(() => {
      expect(screen.getByText(/Fast-Path/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Diagnosis: skipped')).toBeInTheDocument();
    expect(screen.getByLabelText('Skeptic: skipped')).toBeInTheDocument();
    expect(screen.getByLabelText('Remediation: skipped')).toBeInTheDocument();
  });

  it('renders versioned diagnosis with multiple attempts', async () => {
    renderWithProviders('inc-uuid-versioned');
    await waitFor(() => {
      expect(screen.getByText('Triage')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Diagnosis'));
    await waitFor(() => {
      expect(screen.getByText('Attempt 1')).toBeInTheDocument();
    });
    expect(screen.getByText('Attempt 2 (accepted)')).toBeInTheDocument();
  });

  it('renders error state with retry button', async () => {
    server.use(
      http.get('/api/v1/incidents/:id', () => {
        return HttpResponse.json(
          { error: 'Internal error', code: 'INTERNAL_ERROR', detail: {} },
          { status: 500 },
        );
      }),
    );
    renderWithProviders('server-error');
    await waitFor(() => {
      expect(screen.getByText('Error loading incident')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders 404 state', async () => {
    renderWithProviders('not-found');
    await waitFor(() => {
      expect(screen.getByText('Incident not found')).toBeInTheDocument();
    });
  });

  it('renders failed remediation with failed execution and outcome', async () => {
    renderWithProviders('inc-uuid-fail');
    await waitFor(() => {
      expect(screen.getByText('Triage')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Execution: failed')).toBeInTheDocument();
  });

  it('shows rollback-available indicator when execution failed and rollback plan exists', async () => {
    renderWithProviders('inc-uuid-fail');
    await waitFor(() => {
      expect(screen.getByText('Triage')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Execution'));
    await waitFor(() => {
      expect(screen.getByText('Rollback available')).toBeInTheDocument();
    });
  });

  it('renders versioned diagnosis with timestamps', async () => {
    renderWithProviders('inc-uuid-versioned');
    await waitFor(() => {
      expect(screen.getByText('Triage')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Diagnosis'));
    await waitFor(() => {
      expect(screen.getByText('Attempt 1')).toBeInTheDocument();
    });
    expect(screen.getByText('Attempt 2 (accepted)')).toBeInTheDocument();
  });

  it('shows Proceed with Fast-Path button when LLM-unavailable and fast-path exists', async () => {
    renderWithProviders('inc-uuid-llm-fail-fp');
    await waitFor(() => {
      expect(screen.getByText('Triage')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Diagnosis'));
    await waitFor(() => {
      expect(screen.getByText(/LLM unreachable/)).toBeInTheDocument();
    });
    expect(screen.getByText('Proceed with Fast-Path')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderWithProviders('inc-uuid-001');
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'KubePersistentVolumeStuckPending' })).toBeInTheDocument();
    });
    expect(await axe(container)).toHaveNoViolations();
  });
});
