import { useQuery } from '@tanstack/react-query';
import { restProvider } from '@providers/rest-provider';
import type { IncidentFilters, IncidentListItem } from '@models/incident';

const ACTIVE_STATES = [
  'received',
  'correlating',
  'queued',
  'diagnosing',
  'diagnosed',
  'planning',
  'awaiting_approval',
  'executing',
  'observing',
];

function buildParams(filters: IncidentFilters): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};

  if (filters.mode === 'firing') {
    params['status'] = ACTIVE_STATES;
  } else {
    params['status'] = ['resolved', 'failed'];
    if (filters.timeRange) {
      const now = Date.now();
      const msMap: Record<string, number> = {
        '1h': 3_600_000,
        '6h': 21_600_000,
        '24h': 86_400_000,
        '7d': 604_800_000,
      };
      params['from_time'] = new Date(now - msMap[filters.timeRange]!).toISOString();
    }
  }

  if (filters.severities.length > 0 && filters.severities.length < 3) {
    params['severity'] = filters.severities;
  }

  params['page'] = String(filters.page);
  params['page_size'] = String(filters.pageSize);

  return params;
}

export interface IncidentsResult {
  items: IncidentListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export function useIncidents(filters: IncidentFilters) {
  return useQuery<IncidentsResult>({
    queryKey: ['incidents', filters],
    queryFn: async (): Promise<IncidentsResult> => {
      const params = buildParams(filters);
      const response = await restProvider.get<IncidentListItem[]>(
        '/api/v1/incidents',
        params,
      );
      return {
        items: response.data,
        total: response.meta.total ?? 0,
        page: response.meta.page ?? filters.page,
        pageSize: response.meta.page_size ?? filters.pageSize,
      };
    },
    staleTime: 30_000,
  });
}
