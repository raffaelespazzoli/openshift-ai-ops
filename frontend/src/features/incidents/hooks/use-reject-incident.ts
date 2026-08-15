import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getStoredToken } from '@utils/auth';

interface RejectResponse {
  data: { status: string; new_state: string };
  meta: { timestamp: string; request_id: string };
}

interface RejectError {
  error: string;
  code: string;
  detail?: Record<string, unknown>;
}

export function useRejectIncident(incidentId: string) {
  const queryClient = useQueryClient();

  return useMutation<RejectResponse, RejectError, { reason: string }>({
    mutationFn: async ({ reason }) => {
      const token = getStoredToken();
      const response = await fetch(`/api/v1/incidents/${incidentId}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ reason }),
      });
      if (!response.ok) {
        let errorBody: RejectError = { error: `Request failed with status ${response.status}`, code: 'UNKNOWN' };
        try {
          errorBody = await response.json();
        } catch {
          // Non-JSON response (e.g., proxy error)
        }
        throw errorBody;
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents', incidentId] });
      queryClient.invalidateQueries({ queryKey: ['incidents-awaiting'] });
    },
  });
}
