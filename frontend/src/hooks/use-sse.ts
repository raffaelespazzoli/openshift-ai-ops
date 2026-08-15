import { useCallback, useEffect, useRef, useState } from 'react';
import { getStoredToken } from '@utils/auth';

export type SSEConnectionState = 'connected' | 'reconnecting' | 'disconnected';

export interface SSEEvent {
  id: string;
  event: string;
  data: {
    incident_id: string;
    stage?: string;
    state?: string;
    timestamp: string;
    payload?: Record<string, unknown>;
  };
}

interface UseSSEOptions {
  url: string;
  onEvent?: (event: SSEEvent) => void;
  enabled?: boolean;
}

function parseSSEFrame(raw: string): { id?: string; event?: string; data?: string } {
  const result: { id?: string; event?: string; data?: string } = {};
  const lines = raw.split('\n');
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith('id:')) {
      result.id = line.slice(3).trim();
    } else if (line.startsWith('event:')) {
      result.event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (dataLines.length > 0) {
    result.data = dataLines.join('\n');
  }

  return result;
}

export function useSSE({ url, onEvent, enabled = true }: UseSSEOptions) {
  const [connectionState, setConnectionState] = useState<SSEConnectionState>('disconnected');
  const abortRef = useRef<AbortController | null>(null);
  const lastEventIdRef = useRef<string>('');
  const retryDelayRef = useRef(1000);
  const mountedRef = useRef(true);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(async () => {
    if (!mountedRef.current) return;

    const controller = new AbortController();
    abortRef.current = controller;

    const token = getStoredToken();
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (lastEventIdRef.current) headers['Last-Event-ID'] = lastEventIdRef.current;

    try {
      const response = await fetch(url, {
        headers,
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      setConnectionState('connected');
      retryDelayRef.current = 1000;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (mountedRef.current) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
          if (!frame.trim() || frame.trim().startsWith(':')) continue;

          const parsed = parseSSEFrame(frame);
          if (parsed.id) lastEventIdRef.current = parsed.id;
          if (parsed.event && parsed.data) {
            try {
              const sseEvent: SSEEvent = {
                id: parsed.id ?? '',
                event: parsed.event,
                data: JSON.parse(parsed.data),
              };
              onEventRef.current?.(sseEvent);
            } catch {
              // Skip malformed data
            }
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return;
    }

    if (!mountedRef.current) return;

    setConnectionState('reconnecting');
    const jitter = Math.random() * 500;
    const delay = retryDelayRef.current + jitter;
    retryDelayRef.current = Math.min(retryDelayRef.current * 2, 30000);

    await new Promise((resolve) => setTimeout(resolve, delay));
    if (mountedRef.current) connect();
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;

    if (!enabled) {
      setConnectionState('disconnected');
      return;
    }

    connect();

    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      setConnectionState('disconnected');
    };
  }, [connect, enabled]);

  const disconnect = useCallback(() => {
    abortRef.current?.abort();
    setConnectionState('disconnected');
  }, []);

  return { connectionState, disconnect };
}
