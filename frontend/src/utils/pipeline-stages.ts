import type { IncidentDetail, IncidentState, PipelineStageConfig, StageState } from '@models/incident';

const STAGE_IDS = ['triage', 'diagnosis', 'skeptic', 'remediation', 'execution', 'outcome'] as const;
const STAGE_LABELS = ['Triage', 'Diagnosis', 'Skeptic', 'Remediation', 'Execution', 'Outcome'] as const;

type StageTuple = [StageState, StageState, StageState, StageState, StageState, StageState];

const STATE_MAP: Record<string, StageTuple> = {
  received:          ['active', 'pending', 'pending', 'pending', 'pending', 'pending'],
  correlating:       ['active', 'pending', 'pending', 'pending', 'pending', 'pending'],
  queued:            ['completed', 'pending', 'pending', 'pending', 'pending', 'pending'],
  diagnosing:        ['completed', 'active', 'pending', 'pending', 'pending', 'pending'],
  diagnosed:         ['completed', 'completed', 'completed', 'pending', 'pending', 'pending'],
  planning:          ['completed', 'completed', 'completed', 'active', 'pending', 'pending'],
  awaiting_approval: ['completed', 'completed', 'completed', 'awaiting', 'pending', 'pending'],
  executing:         ['completed', 'completed', 'completed', 'completed', 'active', 'pending'],
  observing:         ['completed', 'completed', 'completed', 'completed', 'completed', 'active'],
  resolved:          ['completed', 'completed', 'completed', 'completed', 'completed', 'completed'],
  cancelled:         ['completed', 'pending', 'pending', 'pending', 'pending', 'pending'],
};

function getFailedStageIndex(incident: IncidentDetail): number {
  if (incident.execution_log?.status === 'failed') return 4;
  if (incident.remediation_plan && !incident.execution_log) return 3;
  if (incident.skeptic_verdict?.verdict === 'fail' && !incident.remediation_plan) return 2;
  if (incident.diagnosis && !incident.skeptic_verdict) return 2;
  if (!incident.diagnosis) return 1;
  return 1;
}

function getFailedStages(incident: IncidentDetail): StageTuple {
  const failedIdx = getFailedStageIndex(incident);
  return STAGE_IDS.map((_, i) => {
    if (i < failedIdx) return 'completed';
    if (i === failedIdx) return 'failed';
    return 'pending';
  }) as StageTuple;
}

function getFastPathStages(incident: IncidentDetail): StageTuple {
  const baseState = incident.state;
  const base = STATE_MAP[baseState];
  if (!base) return ['completed', 'skipped', 'skipped', 'skipped', 'pending', 'pending'];

  const result: StageState[] = [...base];
  result[1] = 'skipped';
  result[2] = 'skipped';
  result[3] = 'skipped';
  return result as StageTuple;
}

export function getStageStates(incident: IncidentDetail): PipelineStageConfig[] {
  let states: StageTuple;

  if (incident.fast_path) {
    states = getFastPathStages(incident);
  } else if (incident.state === 'failed') {
    states = getFailedStages(incident);
  } else {
    states = STATE_MAP[incident.state as IncidentState] ?? STATE_MAP['received']!;
  }

  return STAGE_IDS.map((id, i) => ({
    id,
    label: STAGE_LABELS[i]!,
    state: states[i]!,
  }));
}
