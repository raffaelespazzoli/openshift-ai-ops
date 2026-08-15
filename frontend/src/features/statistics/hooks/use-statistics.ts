import { useQuery } from '@tanstack/react-query';
import { useApiClient } from '@hooks/use-api-client';

export type TimeRange = 'day' | 'week' | 'month';

export type TrendDirection = 'up' | 'down' | 'flat';

export interface SummaryData {
  total_incidents: number;
  auto_resolved_pct: number;
  success_failure_ratio: string;
  mttr_seconds: number;
  fast_path_hit_rate_pct: number;
  trends: {
    total_incidents: TrendDirection;
    auto_resolved_pct: TrendDirection;
    success_failure_ratio: TrendDirection;
    mttr_seconds: TrendDirection;
    fast_path_hit_rate_pct: TrendDirection;
  };
}

export interface TimeseriesData {
  buckets: string[];
  alerts: number[];
  diagnoses: number[];
  resolutions: number[];
  mttr_seconds: number[];
}

export function useStatisticsSummary(range: TimeRange) {
  const api = useApiClient();

  return useQuery({
    queryKey: ['statistics', 'summary', range],
    queryFn: () => api.get<SummaryData>('/api/v1/statistics/summary', { range }),
    staleTime: 60_000,
    select: (response) => response.data,
  });
}

export function useStatisticsTimeseries(range: TimeRange) {
  const api = useApiClient();

  return useQuery({
    queryKey: ['statistics', 'timeseries', range],
    queryFn: () => api.get<TimeseriesData>('/api/v1/statistics/timeseries', { range }),
    staleTime: 60_000,
    select: (response) => response.data,
  });
}
