import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe, toHaveNoViolations } from 'jest-axe';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { RemediationPanel } from './remediation-panel';
import type { RemediationData } from '@models/incident';

expect.extend(toHaveNoViolations);

const server = setupServer(
  http.post('/api/v1/incidents/:id/approve', () => {
    return HttpResponse.json({
      data: { status: 'approved', new_state: 'executing' },
      meta: { timestamp: new Date().toISOString(), request_id: 'test' },
    });
  }),
  http.post('/api/v1/incidents/:id/reject', () => {
    return HttpResponse.json({
      data: { status: 'rejected', new_state: 'failed' },
      meta: { timestamp: new Date().toISOString(), request_id: 'test' },
    });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const mockData: RemediationData = {
  steps: [{ order: 1, description: 'Patch SC', action: 'apply', resource: 'SC/default', expected_outcome: 'WaitForFirstConsumer' }],
  blast_radius: 'namespace',
  rollback_plan: [{ order: 1, description: 'Revert SC', action: 'apply', resource: 'SC/default', expected_outcome: 'Immediate' }],
  estimated_risk: 'low',
  preconditions: [{ type: 'rbac', description: 'cluster-admin', requirement: 'patch sc', satisfied: true }],
  plan_summary: 'Patch StorageClass',
  dry_run_confidence: 0.95,
};

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const { container } = render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
  return { container };
}

describe('RemediationPanel', () => {
  it('shows approve/reject buttons when state is awaiting_approval', () => {
    renderWithProviders(
      <RemediationPanel data={mockData} incidentId="inc-1" incidentState="awaiting_approval" />,
    );
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });

  it('does NOT show approve/reject buttons when state is executing', () => {
    renderWithProviders(
      <RemediationPanel data={mockData} incidentId="inc-1" incidentState="executing" />,
    );
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
  });

  it('does NOT show approve/reject buttons when incidentId is missing', () => {
    renderWithProviders(
      <RemediationPanel data={mockData} incidentState="awaiting_approval" />,
    );
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });

  it('renders plan summary', () => {
    renderWithProviders(<RemediationPanel data={mockData} />);
    expect(screen.getByText('Patch StorageClass')).toBeInTheDocument();
  });

  it('shows message when no data', () => {
    renderWithProviders(<RemediationPanel data={null} />);
    expect(screen.getByText(/not yet available/i)).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderWithProviders(
      <RemediationPanel data={mockData} incidentId="inc-1" incidentState="awaiting_approval" />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
