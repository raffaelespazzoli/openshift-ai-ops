import { http, HttpResponse } from 'msw';
import type { IncidentDetail } from '@models/incident';

export const mockIncidentDetail: IncidentDetail = {
  id: 'inc-uuid-001',
  state: 'awaiting_approval',
  severity: 'warning',
  created_at: '2026-08-15T02:07:00Z',
  updated_at: '2026-08-15T02:10:42Z',
  alerts: [
    {
      id: 'alert-uuid-1',
      fingerprint: 'abc123',
      labels: {
        alertname: 'KubePersistentVolumeStuckPending',
        namespace: 'prod',
        severity: 'warning',
      },
      annotations: { summary: 'PVC stuck in Pending state for >5min' },
      status: 'firing',
      fired_at: '2026-08-15T02:07:00Z',
      resolved_at: null,
      created_at: '2026-08-15T02:07:00Z',
    },
  ],
  correlation_evidence: {
    layers_matched: ['namespace_temporal'],
    reasoning: 'Single alert — no correlation needed',
    priority_score: 0.75,
  },
  fast_path: false,
  fast_path_similarity: null,
  fast_path_case_record_id: null,
  diagnosis: {
    root_cause_code: 'storage/pvc-stuck-pending',
    root_cause_component: 'storage',
    failure_mode: 'pvc-stuck-pending',
    causal_chain: [
      'StorageClass volumeBindingMode: Immediate',
      'No available PV in zone',
      'PVC stuck Pending',
    ],
    affected_resources: ['pvc/data-vol-0 (namespace: prod)'],
    evidence: [
      {
        source: 'mcp_cluster',
        query: 'get pvc data-vol-0',
        result: 'status: Pending, reason: no suitable PV',
        timestamp: '2026-08-15T02:08:12Z',
      },
    ],
    evidence_gaps: [],
    confidence: 0.92,
    agent_summary:
      'StorageClass default-sc uses Immediate binding but the target zone has no available PVs. Changing to WaitForFirstConsumer will allow the scheduler to select a zone with capacity.',
    coverage_gaps: [],
  },
  skeptic_verdict: {
    challenge:
      'Could the issue be quota-related rather than binding mode?',
    response:
      'Quota check shows available capacity. The binding mode mismatch is confirmed.',
    verdict: 'pass',
    hash_stable: true,
  },
  remediation_plan: {
    steps: [
      {
        order: 1,
        description: 'Patch StorageClass volumeBindingMode',
        action: 'apply',
        resource: 'StorageClass/default-sc',
        expected_outcome: 'WaitForFirstConsumer',
      },
    ],
    blast_radius: 'namespace',
    rollback_plan: [
      {
        order: 1,
        description: 'Revert StorageClass patch',
        action: 'apply',
        resource: 'StorageClass/default-sc',
        expected_outcome: 'Immediate',
      },
    ],
    estimated_risk: 'low',
    preconditions: [
      {
        type: 'rbac',
        description: 'cluster-admin on StorageClass',
        requirement: 'patch storageclasses',
        satisfied: true,
      },
    ],
    plan_summary:
      'Patch StorageClass default-sc to set volumeBindingMode: WaitForFirstConsumer',
    dry_run_confidence: 0.95,
  },
  execution_log: null,
  outcome: null,
};

export const mockFastPathIncident: IncidentDetail = {
  ...mockIncidentDetail,
  id: 'inc-uuid-fp',
  state: 'executing',
  fast_path: true,
  fast_path_similarity: 0.97,
  fast_path_case_record_id: 'case-record-001',
  diagnosis: null,
  skeptic_verdict: null,
  remediation_plan: null,
  execution_log: {
    steps: [
      {
        step_order: 1,
        command: 'kubectl patch sc default-sc',
        started_at: '2026-08-15T02:11:00Z',
        completed_at: undefined,
        success: true,
        output: 'storageclass.storage.k8s.io/default-sc patched',
      },
    ],
    mcp_calls: [{ tool: 'mcp_readwrite:patch_resource', args: {} }],
    started_at: '2026-08-15T02:11:00Z',
    status: 'running',
  },
};

export const mockFailedIncident: IncidentDetail = {
  ...mockIncidentDetail,
  id: 'inc-uuid-fail',
  state: 'failed',
  execution_log: {
    steps: [
      {
        step_order: 1,
        command: 'kubectl patch sc default-sc',
        started_at: '2026-08-15T02:11:00Z',
        completed_at: '2026-08-15T02:11:05Z',
        success: false,
        output: 'Error: forbidden',
      },
    ],
    mcp_calls: [{ tool: 'mcp_readwrite:patch_resource', args: {} }],
    started_at: '2026-08-15T02:11:00Z',
    completed_at: '2026-08-15T02:11:05Z',
    status: 'failed',
  },
  outcome: {
    alert_resolved: false,
    resolution_method: 'remediation_failed',
    case_record_id: 'case-record-002',
  },
};

export const mockVersionedDiagnosisIncident: IncidentDetail = {
  ...mockIncidentDetail,
  id: 'inc-uuid-versioned',
  diagnosis_attempts: [
    {
      root_cause_code: 'storage/capacity-exceeded',
      causal_chain: ['ResourceQuota limit reached'],
      affected_resources: ['pvc/data-vol-0'],
      evidence: [],
      evidence_gaps: [{ query: 'get pv availability', reason: 'Unable to confirm PV availability' }],
      confidence: 0.45,
      agent_summary: 'Initial diagnosis suggested quota issues.',
      coverage_gaps: [],
      created_at: '2026-08-15T02:08:00Z',
    },
    {
      ...mockIncidentDetail.diagnosis!,
      created_at: '2026-08-15T02:09:30Z',
    },
  ],
};

export const mockLlmUnavailableWithFastPath: IncidentDetail = {
  ...mockIncidentDetail,
  id: 'inc-uuid-llm-fail-fp',
  state: 'failed',
  diagnosis: null,
  fast_path_similarity: 0.94,
  fast_path_case_record_id: 'case-record-fp-001',
  execution_log: null,
  outcome: null,
};

export const mockSummaryData = {
  total_incidents: 142,
  auto_resolved_pct: 67.5,
  success_failure_ratio: '4.2:1',
  mttr_seconds: 312,
  fast_path_hit_rate_pct: 23.8,
  trends: {
    total_incidents: 'up' as const,
    auto_resolved_pct: 'flat' as const,
    success_failure_ratio: 'up' as const,
    mttr_seconds: 'down' as const,
    fast_path_hit_rate_pct: 'up' as const,
  },
};

export const mockTimeseriesData = {
  buckets: [
    '2026-08-14T00:00:00Z',
    '2026-08-14T01:00:00Z',
    '2026-08-14T02:00:00Z',
  ],
  alerts: [5, 3, 8],
  diagnoses: [4, 3, 7],
  resolutions: [3, 2, 6],
  mttr_seconds: [180, 240, 300],
};

export const mockEmptySummaryData = {
  total_incidents: 0,
  auto_resolved_pct: 0,
  success_failure_ratio: '0.0:1',
  mttr_seconds: 0,
  fast_path_hit_rate_pct: 0,
  trends: {
    total_incidents: 'flat' as const,
    auto_resolved_pct: 'flat' as const,
    success_failure_ratio: 'flat' as const,
    mttr_seconds: 'flat' as const,
    fast_path_hit_rate_pct: 'flat' as const,
  },
};

export const mockEmptyTimeseriesData = {
  buckets: [],
  alerts: [],
  diagnoses: [],
  resolutions: [],
  mttr_seconds: [],
};

export const handlers = [
  http.get('/api/v1/incidents', () => {
    return HttpResponse.json({
      data: [],
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-001',
        page: 1,
        page_size: 20,
        total: 0,
      },
    });
  }),

  http.get('/api/v1/incidents/:id', ({ params }) => {
    const id = params['id'] as string;

    if (id === 'not-found') {
      return HttpResponse.json(
        {
          error: 'Not found',
          code: 'NOT_FOUND',
          detail: { id },
        },
        { status: 404 },
      );
    }

    if (id === 'server-error') {
      return HttpResponse.json(
        {
          error: 'Internal server error',
          code: 'INTERNAL_ERROR',
          detail: {},
        },
        { status: 500 },
      );
    }

    if (id === 'inc-uuid-fp') {
      return HttpResponse.json({
        data: { ...mockFastPathIncident, id },
        meta: {
          timestamp: new Date().toISOString(),
          request_id: 'mock-request-id-fp',
        },
      });
    }

    if (id === 'inc-uuid-fail') {
      return HttpResponse.json({
        data: { ...mockFailedIncident, id },
        meta: {
          timestamp: new Date().toISOString(),
          request_id: 'mock-request-id-fail',
        },
      });
    }

    if (id === 'inc-uuid-versioned') {
      return HttpResponse.json({
        data: { ...mockVersionedDiagnosisIncident, id },
        meta: {
          timestamp: new Date().toISOString(),
          request_id: 'mock-request-id-versioned',
        },
      });
    }

    if (id === 'inc-uuid-llm-fail-fp') {
      return HttpResponse.json({
        data: { ...mockLlmUnavailableWithFastPath, id },
        meta: {
          timestamp: new Date().toISOString(),
          request_id: 'mock-request-id-llm-fp',
        },
      });
    }

    return HttpResponse.json({
      data: { ...mockIncidentDetail, id },
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-002',
      },
    });
  }),

  http.get('/api/v1/statistics/summary', () => {
    return HttpResponse.json({
      data: mockSummaryData,
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-stats-summary',
      },
    });
  }),

  http.get('/api/v1/statistics/timeseries', () => {
    return HttpResponse.json({
      data: mockTimeseriesData,
      meta: {
        timestamp: new Date().toISOString(),
        request_id: 'mock-request-id-stats-ts',
      },
    });
  }),

  http.get('/healthz', () => {
    return HttpResponse.json({ status: 'ok' });
  }),
];
