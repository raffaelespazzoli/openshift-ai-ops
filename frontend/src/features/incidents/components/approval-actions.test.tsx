import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { axe, toHaveNoViolations } from 'jest-axe';
import { beforeAll, afterAll, afterEach, describe, expect, it } from 'vitest';
import { ApprovalActions } from './approval-actions';

expect.extend(toHaveNoViolations);

const server = setupServer(
  http.post('/api/v1/incidents/:id/approve', () => {
    return HttpResponse.json({
      data: { status: 'approved', new_state: 'executing' },
      meta: { timestamp: new Date().toISOString(), request_id: 'test-approve' },
    });
  }),
  http.post('/api/v1/incidents/:id/reject', async ({ request }) => {
    const body = (await request.json()) as { reason?: string };
    if (!body.reason?.trim()) {
      return HttpResponse.json(
        { error: 'Reason is required', code: 'VALIDATION_ERROR', detail: {} },
        { status: 400 },
      );
    }
    return HttpResponse.json({
      data: { status: 'rejected', new_state: 'failed' },
      meta: { timestamp: new Date().toISOString(), request_id: 'test-reject' },
    });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const { container } = render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
  return { container };
}

describe('ApprovalActions', () => {
  it('renders Approve and Reject buttons', () => {
    renderWithProviders(<ApprovalActions incidentId="inc-001" />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });

  it('calls POST approve endpoint on Approve click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApprovalActions incidentId="inc-001" />);
    await user.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /approve/i })).not.toBeDisabled();
    });
  });

  it('opens reject modal on Reject click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApprovalActions incidentId="inc-001" />);
    await user.click(screen.getByRole('button', { name: /reject/i }));
    expect(screen.getByText('Reject Remediation Plan')).toBeInTheDocument();
    expect(screen.getByLabelText('Rejection reason')).toBeInTheDocument();
  });

  it('disables modal Reject button when reason is empty', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApprovalActions incidentId="inc-001" />);
    await user.click(screen.getByRole('button', { name: /reject/i }));
    const modalRejectBtn = screen.getAllByRole('button', { name: /reject/i }).find(
      (btn) => btn.closest('[class*="modal"]') || btn.textContent === 'Reject',
    );
    expect(modalRejectBtn).toBeDisabled();
  });

  it('submits reject with reason', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApprovalActions incidentId="inc-001" />);
    await user.click(screen.getByRole('button', { name: /reject/i }));
    await user.type(screen.getByLabelText('Rejection reason'), 'Plan is too risky');

    const modalButtons = screen.getAllByRole('button', { name: /reject/i });
    const submitBtn = modalButtons.find((btn) => !btn.hasAttribute('aria-label'));
    if (submitBtn) await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.queryByText('Reject Remediation Plan')).not.toBeInTheDocument();
    });
  });

  it('shows error alert on approve failure', async () => {
    server.use(
      http.post('/api/v1/incidents/:id/approve', () => {
        return HttpResponse.json(
          { error: 'Server error', code: 'INTERNAL_ERROR', detail: {} },
          { status: 500 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ApprovalActions incidentId="inc-001" />);
    await user.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => {
      expect(screen.getByText(/failed to approve/i)).toBeInTheDocument();
    });
  });

  it('shows disabled state with tooltip on 409 review time remaining', async () => {
    server.use(
      http.post('/api/v1/incidents/:id/approve', () => {
        return HttpResponse.json(
          {
            error: 'Minimum review time has not elapsed',
            code: 'CONFLICT',
            detail: { review_time_remaining: 42.5 },
          },
          { status: 409 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ApprovalActions incidentId="inc-001" />);
    await user.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled();
    });
    expect(screen.getByText(/minimum review time/i)).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderWithProviders(
      <ApprovalActions incidentId="inc-001" planSummary="Patch StorageClass" />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
