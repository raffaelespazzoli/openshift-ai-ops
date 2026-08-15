import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { useIncidentSSE } from './use-incident-sse';

vi.mock('@hooks/use-sse', () => ({
  useSSE: vi.fn(({ onEvent }) => {
    (useSSEMock as { onEvent?: (e: unknown) => void }).onEvent = onEvent;
    return { connectionState: useSSEMock.connectionState };
  }),
}));

const useSSEMock: { connectionState: string; onEvent?: (e: unknown) => void } = {
  connectionState: 'connected',
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useIncidentSSE', () => {
  beforeEach(() => {
    useSSEMock.connectionState = 'connected';
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('returns connection state from underlying SSE hook', () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useIncidentSSE({ incidentId: 'inc-1' }),
      { wrapper },
    );
    expect(result.current.connectionState).toBe('connected');
  });

  it('invalidates incident query on state_changed event', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    renderHook(() => useIncidentSSE({ incidentId: 'inc-1' }), { wrapper });

    useSSEMock.onEvent?.({
      id: '1',
      event: 'incident.state_changed',
      data: { incident_id: 'inc-1', state: 'executing', timestamp: '2026-08-15T00:00:00Z' },
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['incidents', 'inc-1'] }),
      );
    });
  });

  it('invalidates awaiting query on approval_decision event', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    renderHook(() => useIncidentSSE({ incidentId: 'inc-1' }), { wrapper });

    useSSEMock.onEvent?.({
      id: '2',
      event: 'incident.approval_decision',
      data: { incident_id: 'inc-1', timestamp: '2026-08-15T00:00:00Z' },
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['incidents-awaiting'] }),
      );
    });
  });

  it('invalidates incidents list on created/resolved events', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    renderHook(() => useIncidentSSE({ incidentId: 'inc-1' }), { wrapper });

    useSSEMock.onEvent?.({
      id: '3',
      event: 'incident.created',
      data: { incident_id: 'inc-2', timestamp: '2026-08-15T00:00:00Z' },
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['incidents'] }),
      );
    });
  });
});
