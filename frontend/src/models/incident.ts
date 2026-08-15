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
  | 'failed'
  | 'cancelled';

/** @deprecated Use IncidentState — kept for list-view backward compat */
export type IncidentStatus = IncidentState;

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
  resolved_at?: string | null;
  created_at: string;
}

export interface EvidenceArtifact {
  source: string;
  query: string;
  result: string;
  timestamp: string;
}

export interface EvidenceGap {
  query: string;
  reason: string;
  timeout_seconds?: number | null;
}

export interface DiagnosisData {
  root_cause_code: string;
  root_cause_component?: string;
  failure_mode?: string;
  causal_chain: string[];
  affected_resources: string[];
  evidence: EvidenceArtifact[];
  evidence_gaps: EvidenceGap[];
  confidence: number;
  agent_summary: string;
  coverage_gaps: string[];
  created_at?: string;
}

export interface SkepticData {
  challenge: string;
  response: string;
  verdict: 'pass' | 'fail';
  hash_stable: boolean;
}

export interface RemediationStep {
  order: number;
  description: string;
  command?: string | null;
  action: string;
  resource: string;
  expected_outcome: string;
  manifest_path?: string | null;
}

export interface Precondition {
  type: string;
  description: string;
  requirement: string;
  satisfied: boolean | null;
}

export type BlastRadius = 'workload' | 'namespace' | 'node' | 'cluster';

export interface RemediationData {
  steps: RemediationStep[];
  blast_radius: BlastRadius;
  rollback_plan: RemediationStep[];
  estimated_risk: string;
  preconditions: Precondition[];
  plan_summary: string;
  dry_run_confidence?: number;
}

export interface ExecutionStepLog {
  step_order: number;
  command: string;
  started_at: string;
  completed_at?: string | null;
  success: boolean;
  output: string;
  error?: string | null;
}

export interface ExecutionData {
  steps: ExecutionStepLog[];
  mcp_calls: Record<string, unknown>[];
  started_at: string;
  completed_at?: string | null;
  status: 'running' | 'completed' | 'failed';
}

export interface OutcomeData {
  alert_resolved: boolean;
  resolution_method?: string;
  resource_verification?: Record<string, unknown> | null;
  outcome_confidence?: number;
  refire_detected?: boolean;
  observation_started_at?: string;
  observation_completed_at?: string | null;
  case_record_id?: string;
}

export interface CorrelationEvidence {
  layers_matched?: string[];
  reasoning?: string;
  priority_score?: number;
  [key: string]: unknown;
}

export interface IncidentDetail {
  id: string;
  state: IncidentState;
  severity: IncidentSeverity | null;
  created_at: string;
  updated_at: string;
  alerts: Alert[];
  correlation_evidence: CorrelationEvidence;
  fast_path: boolean;
  fast_path_similarity: number | null;
  fast_path_case_record_id: string | null;
  diagnosis?: DiagnosisData | null;
  diagnosis_attempts?: DiagnosisData[];
  skeptic_verdict?: SkepticData | null;
  remediation_plan?: RemediationData | null;
  execution_log?: ExecutionData | null;
  outcome?: OutcomeData | null;
}

export type StageState = 'completed' | 'active' | 'awaiting' | 'failed' | 'skipped' | 'pending';

export interface PipelineStageConfig {
  id: string;
  label: string;
  state: StageState;
}
