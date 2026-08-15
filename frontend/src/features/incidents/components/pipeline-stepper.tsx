import { useCallback, useEffect, useRef, useState } from 'react';
import CheckCircleIcon from '@patternfly/react-icons/dist/esm/icons/check-circle-icon';
import InProgressIcon from '@patternfly/react-icons/dist/esm/icons/in-progress-icon';
import PendingIcon from '@patternfly/react-icons/dist/esm/icons/pending-icon';
import ExclamationCircleIcon from '@patternfly/react-icons/dist/esm/icons/exclamation-circle-icon';
import MinusCircleIcon from '@patternfly/react-icons/dist/esm/icons/minus-circle-icon';
import { ProgressStepper, ProgressStep } from '@patternfly/react-core';
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
  const [focusedStageIndex, setFocusedStageIndex] = useState(0);
  const stepRefs = useRef<(HTMLElement | null)[]>([]);
  const prevStagesRef = useRef<PipelineStageConfig[]>(stages);
  const hasInteracted = useRef(false);
  const [announcement, setAnnouncement] = useState('');

  useEffect(() => {
    const prev = prevStagesRef.current;
    if (prev.length === stages.length) {
      const changed = stages.find((s, i) => s.state !== prev[i]?.state);
      if (changed) {
        setAnnouncement(
          `Pipeline stage updated. ${changed.label} is now ${ARIA_STATE_MAP[changed.state]}.`,
        );
      }
    }
    prevStagesRef.current = stages;
  }, [stages]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      switch (event.key) {
        case 'ArrowRight':
          event.preventDefault();
          hasInteracted.current = true;
          setFocusedStageIndex((prev) => Math.min(prev + 1, stages.length - 1));
          break;
        case 'ArrowLeft':
          event.preventDefault();
          hasInteracted.current = true;
          setFocusedStageIndex((prev) => Math.max(prev - 1, 0));
          break;
        case 'Home':
          event.preventDefault();
          hasInteracted.current = true;
          setFocusedStageIndex(0);
          break;
        case 'End':
          event.preventDefault();
          hasInteracted.current = true;
          setFocusedStageIndex(stages.length - 1);
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          onStageClick(focusedStageIndex);
          break;
      }
    },
    [stages.length, focusedStageIndex, onStageClick],
  );

  useEffect(() => {
    if (hasInteracted.current) {
      stepRefs.current[focusedStageIndex]?.focus();
    }
  }, [focusedStageIndex]);

  return (
    <>
      <div className="pf-v6-u-screen-reader" aria-live="polite" aria-atomic="true" role="status">
        {announcement}
      </div>
      <div onKeyDown={handleKeyDown}>
        <ProgressStepper isCenterAligned aria-label="Pipeline stages" role="tablist">
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
              ref={(el: HTMLElement | null) => {
                stepRefs.current[index] = el;
              }}
              tabIndex={index === focusedStageIndex ? 0 : -1}
              role="tab"
              aria-selected={expandedStage === index}
            >
              {stage.label}
            </ProgressStep>
          ))}
        </ProgressStepper>
      </div>
    </>
  );
}
