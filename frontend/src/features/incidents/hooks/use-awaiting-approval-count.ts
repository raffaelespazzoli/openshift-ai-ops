import { useQuery } from '@tanstack/react-query';
import { getStoredToken } from '@utils/auth';

interface AwaitingApprovalResponse {
  data: Array<{ id: string; state: string; severity: string }>;
  meta: { total: number; timestamp: string; request_id: string };
}

export function useAwaitingApprovalCount() {
  return useQuery({
    queryKey: ['incidents-awaiting'],
    queryFn: async (): Promise<number> => {
      const token = getStoredToken();
      const response = await fetch('/api/v1/incidents/awaiting-approval', {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const envelope: AwaitingApprovalResponse = await response.json();
      return envelope.meta.total;
    },
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}
