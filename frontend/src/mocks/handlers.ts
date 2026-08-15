import { http, HttpResponse } from 'msw';
import type { IncidentListItem } from '@models/incident';

const MOCK_INCIDENTS: IncidentListItem[] = [
  {
    id: '11111111-1111-1111-1111-111111111111',
    state: 'diagnosing',
    severity: 'critical',
    created_at: new Date(Date.now() - 600_000).toISOString(),
    updated_at: new Date(Date.now() - 300_000).toISOString(),
    fast_path: false,
  },
  {
    id: '22222222-2222-2222-2222-222222222222',
    state: 'executing',
    severity: 'warning',
    created_at: new Date(Date.now() - 3_600_000).toISOString(),
    updated_at: new Date(Date.now() - 1_800_000).toISOString(),
    fast_path: true,
  },
  {
    id: '33333333-3333-3333-3333-333333333333',
    state: 'received',
    severity: 'info',
    created_at: new Date(Date.now() - 7_200_000).toISOString(),
    updated_at: new Date(Date.now() - 7_200_000).toISOString(),
    fast_path: false,
  },
];

export const handlers = [
  http.get('/api/v1/incidents', ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') ?? '1');
    const pageSize = Number(url.searchParams.get('page_size') ?? '50');

    return HttpResponse.json({
      data: MOCK_INCIDENTS,
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-001',
        page,
        page_size: pageSize,
        total: MOCK_INCIDENTS.length,
      },
    });
  }),

  http.get('/api/v1/incidents/:id', ({ params }) => {
    return HttpResponse.json({
      data: {
        id: params['id'],
        state: 'diagnosing',
        severity: 'critical',
        created_at: '2026-08-15T10:00:00Z',
        updated_at: '2026-08-15T10:05:00Z',
        alerts: [],
        correlation_evidence: {},
        fast_path: false,
        fast_path_similarity: null,
        fast_path_case_record_id: null,
      },
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-002',
      },
    });
  }),

  http.get('/healthz', () => {
    return HttpResponse.json({ status: 'ok' });
  }),
];
