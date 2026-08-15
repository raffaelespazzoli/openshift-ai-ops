import { http, HttpResponse } from 'msw';

export const mockSummaryData = {
  total_incidents: 142,
  auto_resolved_pct: 67.5,
  success_failure_ratio: '4.2:1',
  mttr_seconds: 312,
  fast_path_hit_rate_pct: 23.8,
  trends: {
    total_incidents: 'up' as const,
    auto_resolved_pct: 'flat' as const,
    success_failure_ratio: 'up' as const,
    mttr_seconds: 'down' as const,
    fast_path_hit_rate_pct: 'up' as const,
  },
};

export const mockTimeseriesData = {
  buckets: [
    '2026-08-14T00:00:00Z',
    '2026-08-14T01:00:00Z',
    '2026-08-14T02:00:00Z',
  ],
  alerts: [5, 3, 8],
  diagnoses: [4, 3, 7],
  resolutions: [3, 2, 6],
  mttr_seconds: [180, 240, 300],
};

export const mockEmptySummaryData = {
  total_incidents: 0,
  auto_resolved_pct: 0,
  success_failure_ratio: '0.0:1',
  mttr_seconds: 0,
  fast_path_hit_rate_pct: 0,
  trends: {
    total_incidents: 'flat' as const,
    auto_resolved_pct: 'flat' as const,
    success_failure_ratio: 'flat' as const,
    mttr_seconds: 'flat' as const,
    fast_path_hit_rate_pct: 'flat' as const,
  },
};

export const mockEmptyTimeseriesData = {
  buckets: [],
  alerts: [],
  diagnoses: [],
  resolutions: [],
  mttr_seconds: [],
};

export const handlers = [
  http.get('/api/v1/incidents', () => {
    return HttpResponse.json({
      data: [],
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-001',
        page: 1,
        page_size: 20,
        total: 0,
      },
    });
  }),

  http.get('/api/v1/incidents/:id', ({ params }) => {
    return HttpResponse.json({
      data: {
        id: params['id'],
        title: 'Mock incident',
        status: 'diagnosing',
        severity: 'warning',
        root_cause_code: 'node/memory-pressure',
        alerts: [],
        created_at: '2026-08-15T10:00:00Z',
        updated_at: '2026-08-15T10:05:00Z',
      },
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-002',
      },
    });
  }),

  http.get('/api/v1/statistics/summary', () => {
    return HttpResponse.json({
      data: mockSummaryData,
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-stats-summary',
      },
    });
  }),

  http.get('/api/v1/statistics/timeseries', () => {
    return HttpResponse.json({
      data: mockTimeseriesData,
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-stats-ts',
      },
    });
  }),

  http.get('/healthz', () => {
    return HttpResponse.json({ status: 'ok' });
  }),
];
