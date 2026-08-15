export type IncidentStatus =
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

export interface Alert {
  fingerprint: string;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  starts_at: string;
  ends_at?: string;
  status: string;
}

export interface Incident {
  id: string;
  title: string;
  status: IncidentStatus;
  severity: IncidentSeverity;
  root_cause_code?: string;
  alerts: Alert[];
  created_at: string;
  updated_at: string;
}
