import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { IncidentFilters, IncidentSeverity } from '@models/incident';

const ALL_SEVERITIES: IncidentSeverity[] = ['critical', 'warning', 'info'];
const VALID_MODES = new Set(['firing', 'resolved']);
const VALID_TIME_RANGES = new Set(['1h', '6h', '24h', '7d']);

function parseFilters(params: URLSearchParams): IncidentFilters {
  const rawMode = params.get('mode');
  const mode: IncidentFilters['mode'] =
    rawMode && VALID_MODES.has(rawMode) ? (rawMode as IncidentFilters['mode']) : 'firing';

  const rawSeverities = params.getAll('severity');
  const severities: IncidentSeverity[] =
    rawSeverities.length > 0
      ? (rawSeverities.filter((s) => ALL_SEVERITIES.includes(s as IncidentSeverity)) as IncidentSeverity[])
      : [...ALL_SEVERITIES];

  const rawTimeRange = params.get('timeRange');
  const timeRange: IncidentFilters['timeRange'] =
    rawTimeRange && VALID_TIME_RANGES.has(rawTimeRange)
      ? (rawTimeRange as IncidentFilters['timeRange'])
      : undefined;

  const page = Math.max(1, Number(params.get('page')) || 1);
  const pageSize = Math.min(200, Math.max(1, Number(params.get('pageSize')) || 50));

  return { mode, severities, timeRange, page, pageSize };
}

export function useIncidentFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);

  const setFilters = useCallback(
    (updates: Partial<IncidentFilters>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (updates.mode !== undefined) next.set('mode', updates.mode);
          if (updates.severities !== undefined) {
            next.delete('severity');
            updates.severities.forEach((s) => next.append('severity', s));
          }
          if ('timeRange' in updates) {
            if (updates.timeRange) next.set('timeRange', updates.timeRange);
            else next.delete('timeRange');
          }
          if (updates.page !== undefined) next.set('page', String(updates.page));
          else next.set('page', '1');
          if (updates.pageSize !== undefined) next.set('pageSize', String(updates.pageSize));
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  return { filters, setFilters } as const;
}
