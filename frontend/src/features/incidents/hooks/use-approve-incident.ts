import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getStoredToken } from '@utils/auth';

interface ApproveResponse {
  data: { status: string; new_state: string };
  meta: { timestamp: string; request_id: string };
}

interface ApproveError {
  error: string;
  code: string;
  detail?: { review_time_remaining?: number };
}

export function useApproveIncident(incidentId: string) {
  const queryClient = useQueryClient();

  return useMutation<ApproveResponse, ApproveError>({
    mutationFn: async () => {
      const token = getStoredToken();
      const response = await fetch(`/api/v1/incidents/${incidentId}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!response.ok) {
        const error: ApproveError = await response.json();
        throw error;
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents', incidentId] });
      queryClient.invalidateQueries({ queryKey: ['incidents-awaiting'] });
    },
  });
}
