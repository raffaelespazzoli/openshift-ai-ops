import { useQuery } from '@tanstack/react-query';
import type { IncidentDetail } from '@models/incident';
import type { ApiResponse } from '@models/api';

export function useIncidentDetail(id: string) {
  return useQuery({
    queryKey: ['incidents', id],
    queryFn: async (): Promise<IncidentDetail> => {
      const response = await fetch(`/api/v1/incidents/${id}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(localStorage.getItem('oauth_token')
            ? { Authorization: `Bearer ${localStorage.getItem('oauth_token')}` }
            : {}),
        },
      });
      if (!response.ok) {
        const error = new Error(`HTTP ${response.status}`);
        (error as Error & { status: number }).status = response.status;
        throw error;
      }
      const envelope = (await response.json()) as ApiResponse<IncidentDetail>;
      return envelope.data;
    },
    staleTime: 30_000,
  });
}
