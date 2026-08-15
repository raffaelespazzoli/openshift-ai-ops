import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { useSSE, type SSEConnectionState } from './use-sse';

function createMockStream(events: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < events.length) {
        controller.enqueue(encoder.encode(events[index]!));
        index++;
      } else {
        controller.close();
      }
    },
  });
}

describe('useSSE', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('connects and parses SSE events', async () => {
    const eventPayload = 'id: 1\nevent: incident.state_changed\ndata: {"incident_id":"inc-1","state":"executing","timestamp":"2026-08-15T00:00:00Z"}\n\n';
    const stream = createMockStream([eventPayload]);

    fetchSpy.mockResolvedValueOnce(
      new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    );

    const onEvent = vi.fn();
    const { result } = renderHook(() =>
      useSSE({ url: '/api/v1/events/stream', onEvent }),
    );

    await waitFor(() => {
      expect(onEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          id: '1',
          event: 'incident.state_changed',
          data: expect.objectContaining({ incident_id: 'inc-1' }),
        }),
      );
    });
  });

  it('transitions to disconnected state when disabled', () => {
    fetchSpy.mockResolvedValue(
      new Response(createMockStream([]), { status: 200 }),
    );

    const { result } = renderHook(() =>
      useSSE({ url: '/api/v1/events/stream', enabled: false }),
    );

    expect(result.current.connectionState).toBe('disconnected');
  });

  it('reconnects with backoff on connection drop', async () => {
    vi.useFakeTimers();

    let callCount = 0;
    fetchSpy.mockImplementation(async () => {
      callCount++;
      if (callCount === 1) {
        throw new Error('Network error');
      }
      return new Response(createMockStream([': keepalive\n\n']), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    });

    const { result } = renderHook(() =>
      useSSE({ url: '/api/v1/events/stream' }),
    );

    await vi.advanceTimersByTimeAsync(2000);

    expect(callCount).toBeGreaterThanOrEqual(2);

    vi.useRealTimers();
  });

  it('cleans up on unmount', async () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort');
    const stream = createMockStream([': keepalive\n\n']);

    fetchSpy.mockResolvedValueOnce(
      new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    );

    const { unmount } = renderHook(() =>
      useSSE({ url: '/api/v1/events/stream' }),
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    unmount();
    expect(abortSpy).toHaveBeenCalled();
  });

  it('exposes connection state', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(': keepalive\n\n'));
        // Keep stream open - don't close controller
      },
    });

    fetchSpy.mockResolvedValueOnce(
      new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    );

    const { result } = renderHook(() =>
      useSSE({ url: '/api/v1/events/stream' }),
    );

    await waitFor(() => {
      expect(result.current.connectionState).toBe('connected');
    });
  });

  it('includes Last-Event-ID header on reconnection', async () => {
    vi.useFakeTimers();

    const firstEvent = 'id: 42\nevent: incident.created\ndata: {"incident_id":"inc-1","timestamp":"2026-08-15T00:00:00Z"}\n\n';
    let callCount = 0;

    fetchSpy.mockImplementation(async (_url, options) => {
      callCount++;
      if (callCount === 1) {
        return new Response(createMockStream([firstEvent]), {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }
      const headers = (options as RequestInit)?.headers as Record<string, string>;
      expect(headers?.['Last-Event-ID']).toBe('42');
      return new Response(createMockStream([': keepalive\n\n']), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    });

    renderHook(() => useSSE({ url: '/api/v1/events/stream' }));

    await vi.advanceTimersByTimeAsync(3000);
    expect(callCount).toBeGreaterThanOrEqual(2);

    vi.useRealTimers();
  });
});
