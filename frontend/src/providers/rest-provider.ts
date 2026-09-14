import type { ApiResponse } from '@models/api';
import { isApiError } from '@models/api';
import { clearToken, initiateOAuthFlow, shouldUseClientOAuth } from '@utils/auth';
import type { DataProvider } from './data-provider';

export class ApiClientError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly detail: Record<string, unknown>,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

function getToken(): string | null {
  if (import.meta.env.DEV && import.meta.env.VITE_DEV_TOKEN) {
    return import.meta.env.VITE_DEV_TOKEN;
  }
  return localStorage.getItem('oauth_token');
}

function getHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(response: Response): Promise<ApiResponse<T>> {
  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      if (shouldUseClientOAuth()) {
        initiateOAuthFlow();
      }
    }

    const body: unknown = await response.json().catch(() => null);
    if (isApiError(body)) {
      throw new ApiClientError(body.code, body.error, body.detail, response.status);
    }
    throw new ApiClientError(
      'UNKNOWN_ERROR',
      `HTTP ${response.status}: ${response.statusText}`,
      {},
      response.status,
    );
  }
  return (await response.json()) as ApiResponse<T>;
}

const baseUrl = import.meta.env.VITE_API_BASE_URL || '';

export const restProvider: DataProvider = {
  async get<T>(endpoint: string, params?: Record<string, string | string[]>): Promise<ApiResponse<T>> {
    const url = new URL(`${baseUrl}${endpoint}`, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (Array.isArray(value)) {
          value.forEach((v) => url.searchParams.append(key, v));
        } else {
          url.searchParams.set(key, value);
        }
      });
    }
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: getHeaders(),
    });
    return handleResponse<T>(response);
  },

  async post<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    const response = await fetch(`${baseUrl}${endpoint}`, {
      method: 'POST',
      headers: getHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(response);
  },

  subscribe(_endpoint: string, _onMessage: (event: MessageEvent) => void): () => void {
    // SSE with proper auth headers will be implemented in story 5.4
    throw new Error('subscribe() is not implemented yet — see story 5.4');
  },
};
