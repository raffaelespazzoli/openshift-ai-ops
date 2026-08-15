import type { ApiResponse } from '@models/api';

export interface DataProvider {
  get<T>(endpoint: string, params?: Record<string, string | string[]>): Promise<ApiResponse<T>>;
  post<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>>;
  subscribe(endpoint: string, onMessage: (event: MessageEvent) => void): () => void;
}
