import { restProvider } from '@providers/rest-provider';
import type { DataProvider } from '@providers/data-provider';

export function useApiClient(): DataProvider {
  return restProvider;
}
