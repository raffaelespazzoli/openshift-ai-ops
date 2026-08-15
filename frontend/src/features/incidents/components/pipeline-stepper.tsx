import { ProgressStepper, ProgressStep } from '@patternfly/react-core';
import CheckCircleIcon from '@patternfly/react-icons/dist/esm/icons/check-circle-icon';
import InProgressIcon from '@patternfly/react-icons/dist/esm/icons/in-progress-icon';
import PendingIcon from '@patternfly/react-icons/dist/esm/icons/pending-icon';
import ExclamationCircleIcon from '@patternfly/react-icons/dist/esm/icons/exclamation-circle-icon';
import MinusCircleIcon from '@patternfly/react-icons/dist/esm/icons/minus-circle-icon';
import type { PipelineStageConfig, StageState } from '@models/incident';

interface PipelineStepperProps {
  stages: PipelineStageConfig[];
  expandedStage: number | null;
  onStageClick: (index: number) => void;
}

const ARIA_STATE_MAP: Record<StageState, string> = {
  completed: 'completed',
  active: 'in progress',
  awaiting: 'awaiting approval',
  failed: 'failed',
  skipped: 'skipped',
  pending: 'pending',
};

function getVariant(state: StageState): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  switch (state) {
    case 'completed': return 'success';
    case 'active': return 'info';
    case 'awaiting': return 'warning';
    case 'failed': return 'danger';
    case 'skipped':
    case 'pending':
    default: return 'default';
  }
}

function getIcon(state: StageState) {
  switch (state) {
    case 'completed': return <CheckCircleIcon />;
    case 'active': return <InProgressIcon />;
    case 'awaiting': return <PendingIcon />;
    case 'failed': return <ExclamationCircleIcon />;
    case 'skipped': return <MinusCircleIcon />;
    case 'pending':
    default: return undefined;
  }
}

export function PipelineStepper({ stages, expandedStage, onStageClick }: PipelineStepperProps) {
  return (
    <ProgressStepper isCenterAligned aria-label="Incident pipeline stages">
      {stages.map((stage, index) => (
        <ProgressStep
          key={stage.id}
          variant={getVariant(stage.state)}
          icon={getIcon(stage.state)}
          isCurrent={stage.state === 'active' || stage.state === 'awaiting'}
          id={`stage-${stage.id}`}
          titleId={`stage-${stage.id}-title`}
          aria-label={`${stage.label}: ${ARIA_STATE_MAP[stage.state]}`}
          className={stage.state === 'skipped' ? 'pf-m-disabled' : undefined}
          onClick={() => onStageClick(index)}
          aria-expanded={expandedStage === index}
        >
          {stage.label}
        </ProgressStep>
      ))}
    </ProgressStepper>
  );
}
