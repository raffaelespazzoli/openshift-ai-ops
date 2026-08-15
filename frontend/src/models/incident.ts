export type IncidentState =
  | 'received'
  | 'correlating'
  | 'queued'
  | 'diagnosing'
  | 'diagnosed'
  | 'planning'
  | 'awaiting_approval'
  | 'executing'
  | 'observing'
  | 'resolved'
  | 'failed';

export type IncidentSeverity = 'critical' | 'warning' | 'info';

export interface IncidentListItem {
  id: string;
  state: IncidentState;
  severity: IncidentSeverity;
  created_at: string;
  updated_at: string;
  fast_path: boolean;
}

export interface IncidentFilters {
  mode: 'firing' | 'resolved';
  severities: IncidentSeverity[];
  timeRange?: '1h' | '6h' | '24h' | '7d';
  page: number;
  pageSize: number;
}

export interface Alert {
  id: string;
  fingerprint: string;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  status: string;
  fired_at: string;
  resolved_at?: string;
  created_at: string;
}
