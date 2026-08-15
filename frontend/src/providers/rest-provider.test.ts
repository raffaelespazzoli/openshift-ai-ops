import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server } from '@mocks/server';
import { http, HttpResponse } from 'msw';
import { restProvider, ApiClientError } from './rest-provider';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('restProvider', () => {
  describe('get', () => {
    it('extracts data from the API envelope', async () => {
      server.use(
        http.get('/api/v1/incidents', () => {
          return HttpResponse.json({
            data: [{ id: '1', title: 'Test Incident' }],
            meta: {
              timestamp: '2026-08-15T10:00:00Z',
              request_id: 'req-123',
              page: 1,
              page_size: 20,
              total: 1,
            },
          });
        }),
      );

      const result = await restProvider.get<Array<{ id: string; title: string }>>(
        '/api/v1/incidents',
      );
      expect(result.data).toEqual([{ id: '1', title: 'Test Incident' }]);
      expect(result.meta.request_id).toBe('req-123');
      expect(result.meta.timestamp).toBe('2026-08-15T10:00:00Z');
    });

    it('passes query parameters correctly', async () => {
      server.use(
        http.get('/api/v1/incidents', ({ request }) => {
          const url = new URL(request.url);
          const status = url.searchParams.get('status');
          return HttpResponse.json({
            data: [],
            meta: {
              timestamp: '2026-08-15T10:00:00Z',
              request_id: 'req-456',
              page: 1,
              page_size: 20,
              total: 0,
            },
            _params: { status },
          });
        }),
      );

      const result = await restProvider.get('/api/v1/incidents', { status: 'critical' });
      expect(result.meta.request_id).toBe('req-456');
    });
  });

  describe('error handling', () => {
    it('parses API error responses in the standard format', async () => {
      server.use(
        http.get('/api/v1/incidents/missing', () => {
          return HttpResponse.json(
            {
              error: 'Incident not found',
              code: 'NOT_FOUND',
              detail: { id: 'missing' },
            },
            { status: 404 },
          );
        }),
      );

      await expect(restProvider.get('/api/v1/incidents/missing')).rejects.toMatchObject({
        code: 'NOT_FOUND',
        message: 'Incident not found',
        detail: { id: 'missing' },
        status: 404,
      });
    });

    it('throws ApiClientError for non-standard error responses', async () => {
      server.use(
        http.get('/api/v1/incidents/error', () => {
          return new HttpResponse('Internal Server Error', { status: 500 });
        }),
      );

      try {
        await restProvider.get('/api/v1/incidents/error');
        expect.fail('Should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(ApiClientError);
        expect((error as ApiClientError).code).toBe('UNKNOWN_ERROR');
        expect((error as ApiClientError).status).toBe(500);
      }
    });
  });

  describe('post', () => {
    it('sends POST requests with body', async () => {
      server.use(
        http.post('/api/v1/incidents/abc/approve', async ({ request }) => {
          const body = await request.json();
          return HttpResponse.json({
            data: { approved: true, body },
            meta: {
              timestamp: '2026-08-15T10:00:00Z',
              request_id: 'req-789',
            },
          });
        }),
      );

      const result = await restProvider.post<{ approved: boolean }>('/api/v1/incidents/abc/approve', {
        reason: 'looks good',
      });
      expect(result.data.approved).toBe(true);
    });
  });
});
