export interface ApiMeta {
  timestamp: string;
  request_id: string;
  page?: number;
  page_size?: number;
  total?: number;
}

export interface ApiResponse<T> {
  data: T;
  meta: ApiMeta;
}

export interface ApiError {
  error: string;
  code: string;
  detail: Record<string, unknown>;
}

export function isApiError(value: unknown): value is ApiError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    'code' in value &&
    'detail' in value
  );
}
