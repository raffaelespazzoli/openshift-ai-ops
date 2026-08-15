import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSSE, type SSEConnectionState, type SSEEvent } from '@hooks/use-sse';

interface UseIncidentSSEOptions {
  incidentId?: string;
  enabled?: boolean;
}

export function useIncidentSSE({ incidentId, enabled = true }: UseIncidentSSEOptions): {
  connectionState: SSEConnectionState;
} {
  const queryClient = useQueryClient();

  const handleEvent = useCallback(
    (event: SSEEvent) => {
      const { event: eventName, data } = event;

      switch (eventName) {
        case 'incident.state_changed':
        case 'incident.stage_changed':
          if (incidentId && data.incident_id === incidentId) {
            queryClient.invalidateQueries({ queryKey: ['incidents', incidentId] });
          }
          break;

        case 'incident.approval_decision':
          queryClient.invalidateQueries({ queryKey: ['incidents-awaiting'] });
          if (incidentId && data.incident_id === incidentId) {
            queryClient.invalidateQueries({ queryKey: ['incidents', incidentId] });
          }
          break;

        case 'incident.created':
        case 'incident.resolved':
          queryClient.invalidateQueries({ queryKey: ['incidents'] });
          if (incidentId && data.incident_id === incidentId) {
            queryClient.invalidateQueries({ queryKey: ['incidents', incidentId] });
          }
          break;
      }
    },
    [incidentId, queryClient],
  );

  const { connectionState } = useSSE({
    url: '/api/v1/events/stream',
    onEvent: handleEvent,
    enabled,
  });

  return { connectionState };
}
