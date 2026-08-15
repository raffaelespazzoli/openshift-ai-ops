import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/v1/incidents', () => {
    return HttpResponse.json({
      data: [],
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-001',
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

  http.get('/healthz', () => {
    return HttpResponse.json({ status: 'ok' });
  }),
];
